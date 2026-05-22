"""LightGBM training with threshold tuning to enforce FPR < 0.5%."""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier
from sklearn.metrics import classification_report, roc_auc_score, roc_curve
from sklearn.model_selection import train_test_split

from ml_layer.features.pdf import FEATURE_ORDER

logger = logging.getLogger(__name__)

# Default hyperparameters — good starting point for malware classification.
_DEFAULT_PARAMS: dict[str, object] = {
    "n_estimators": 500,
    "learning_rate": 0.05,
    "num_leaves": 63,
    "class_weight": "balanced",
    "random_state": 42,
    "n_jobs": -1,
}

# Maximum allowed false-positive rate (business constraint: < 0.5%).
FPR_TARGET = 0.005


def train(df: pd.DataFrame) -> tuple[LGBMClassifier, float]:
    """Fit a LightGBM classifier and tune the decision threshold.

    Parameters
    ----------
    df:
        DataFrame produced by ``ingest.load_dataset``.
        Must contain all ``FEATURE_ORDER`` columns plus ``"label"``.

    Returns
    -------
    model:
        Fitted ``LGBMClassifier``.
    threshold:
        Decision threshold (applied to ``predict_proba[:, 1]``) that keeps
        FPR ≤ ``FPR_TARGET``.  Map ``proba >= threshold → malicious``.
    """
    X = df[FEATURE_ORDER].to_numpy(dtype=np.float32)
    y = df["label"].to_numpy(dtype=np.int32)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, stratify=y, random_state=42
    )

    model = LGBMClassifier(**_DEFAULT_PARAMS)  # type: ignore[arg-type]
    model.fit(X_train, y_train)

    proba = model.predict_proba(X_test)[:, 1]
    auc = roc_auc_score(y_test, proba)
    logger.info("ROC AUC: %.4f", auc)

    fpr_arr, _tpr_arr, thresholds = roc_curve(y_test, proba)

    # Pick the highest threshold that keeps FPR ≤ FPR_TARGET.
    valid = thresholds[fpr_arr <= FPR_TARGET]
    threshold = float(valid[-1]) if len(valid) > 0 else float(thresholds[-1])
    logger.info("Decision threshold (FPR ≤ %.1f%%): %.4f", FPR_TARGET * 100, threshold)

    y_pred = (proba >= threshold).astype(int)
    logger.info("\n%s", classification_report(y_test, y_pred, target_names=["benign", "malicious"]))

    return model, threshold
