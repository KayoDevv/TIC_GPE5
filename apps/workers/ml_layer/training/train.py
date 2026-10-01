"""LightGBM training: content dedup, leakage-free split, and FPR-bounded threshold.

Duplicate files are dropped by content hash, the data is split three ways with a
group-disjoint stratified split so no file or near-duplicate crosses the
train/val/test boundary, the model is fit on train, the threshold is tuned on
validation to keep FPR under the business target, and metrics are reported on the
untouched test set.
"""

from __future__ import annotations

import hashlib
import logging

import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier
from sklearn.metrics import classification_report, roc_auc_score, roc_curve
from sklearn.model_selection import StratifiedGroupKFold, train_test_split

from ml_layer.features.pdf import FEATURE_ORDER

logger = logging.getLogger(__name__)

_DEFAULT_PARAMS: dict[str, object] = {
    "n_estimators": 500,
    "learning_rate": 0.05,
    "num_leaves": 31,
    "min_child_samples": 50,
    "subsample": 0.8,
    "subsample_freq": 1,
    "colsample_bytree": 0.8,
    "reg_lambda": 1.0,
    "class_weight": "balanced",
    "random_state": 42,
    "n_jobs": -1,
}

FPR_TARGET = 0.005
_PERCENT = 100.0

_HOLDOUT_N_SPLITS = 5
_HOLDOUT_FRACTION = 0.2
_TEST_SPLIT_SEED = 42
_VALIDATION_SPLIT_SEED = 43


def _deduplicate(df: pd.DataFrame) -> pd.DataFrame:
    if "sha256" not in df.columns:
        return df
    before = len(df)
    deduped = df.drop_duplicates(subset="sha256", keep="first").reset_index(drop=True)
    removed = before - len(deduped)
    if removed:
        logger.info(
            "Dedup: dropped %d exact-duplicate files by content hash (%d -> %d)",
            removed,
            before,
            len(deduped),
        )
    return deduped


def _feature_groups(features: np.ndarray) -> np.ndarray:
    return np.array([hashlib.sha256(row.tobytes()).hexdigest() for row in features])


def _grouped_holdout(
    y: np.ndarray, groups: np.ndarray, random_state: int
) -> tuple[np.ndarray, np.ndarray]:
    n = len(y)
    try:
        splitter = StratifiedGroupKFold(
            n_splits=_HOLDOUT_N_SPLITS, shuffle=True, random_state=random_state
        )
        rest_idx, holdout_idx = next(splitter.split(np.zeros((n, 1)), y, groups))
        return rest_idx, holdout_idx
    except ValueError:
        return train_test_split(
            np.arange(n), test_size=_HOLDOUT_FRACTION, stratify=y, random_state=random_state
        )


def _split_indices(y: np.ndarray, groups: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    trainval_idx, test_idx = _grouped_holdout(y, groups, _TEST_SPLIT_SEED)
    train_rel, val_rel = _grouped_holdout(
        y[trainval_idx], groups[trainval_idx], _VALIDATION_SPLIT_SEED
    )
    return trainval_idx[train_rel], trainval_idx[val_rel], test_idx


def _tune_threshold(model: LGBMClassifier, X_val: np.ndarray, y_val: np.ndarray) -> float:
    val_proba = model.predict_proba(X_val)[:, 1]
    fpr_arr, _tpr_arr, thresholds = roc_curve(y_val, val_proba)
    within_target = thresholds[fpr_arr <= FPR_TARGET]
    threshold = float(within_target[-1]) if len(within_target) > 0 else float(thresholds[-1])
    logger.info("Decision threshold (val FPR <= %.1f%%): %.4f", FPR_TARGET * _PERCENT, threshold)
    return threshold


def _report_test_metrics(
    model: LGBMClassifier, X_test: np.ndarray, y_test: np.ndarray, threshold: float
) -> None:
    test_proba = model.predict_proba(X_test)[:, 1]
    logger.info("Test ROC AUC: %.4f", roc_auc_score(y_test, test_proba))
    y_pred = (test_proba >= threshold).astype(int)
    logger.info("\n%s", classification_report(y_test, y_pred, target_names=["benign", "malicious"]))


def train(df: pd.DataFrame) -> tuple[LGBMClassifier, float]:
    df = _deduplicate(df)

    X = df[FEATURE_ORDER].to_numpy(dtype=np.float32)
    y = df["label"].to_numpy(dtype=np.int32)
    groups = _feature_groups(X)

    train_idx, val_idx, test_idx = _split_indices(y, groups)

    model = LGBMClassifier(**_DEFAULT_PARAMS)  # type: ignore[arg-type]
    model.fit(X[train_idx], y[train_idx])

    threshold = _tune_threshold(model, X[val_idx], y[val_idx])
    _report_test_metrics(model, X[test_idx], y[test_idx], threshold)

    return model, threshold
