"""Tests for training.train and training.export."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from ml_layer.features.pdf import FEATURE_ORDER
from training.train import FPR_TARGET, _deduplicate, train


def _make_synthetic_df(n_malicious: int = 60, n_benign: int = 140) -> pd.DataFrame:
    """Create a minimal synthetic feature dataset for unit-testing the trainer."""
    rng = np.random.default_rng(0)

    mal_features = rng.uniform(0.5, 1.0, size=(n_malicious, len(FEATURE_ORDER))).astype(np.float32)
    ben_features = rng.uniform(0.0, 0.4, size=(n_benign, len(FEATURE_ORDER))).astype(np.float32)

    features = np.vstack([mal_features, ben_features])
    labels = np.array([1] * n_malicious + [0] * n_benign, dtype=np.int32)

    df = pd.DataFrame(features, columns=FEATURE_ORDER)
    df["label"] = labels
    return df


class TestTrain:
    def test_returns_model_and_threshold(self) -> None:
        df = _make_synthetic_df()
        model, threshold = train(df)
        assert model is not None
        assert isinstance(threshold, float)

    def test_threshold_is_between_zero_and_one(self) -> None:
        df = _make_synthetic_df()
        _, threshold = train(df)
        assert 0.0 <= threshold <= 1.0

    def test_model_can_predict_proba(self) -> None:
        df = _make_synthetic_df()
        model, _ = train(df)
        dummy = np.zeros((1, len(FEATURE_ORDER)), dtype=np.float32)
        proba = model.predict_proba(dummy)
        assert proba.shape == (1, 2)
        assert abs(proba[0].sum() - 1.0) < 1e-5

    def test_fpr_target_constant(self) -> None:
        assert FPR_TARGET == 0.005

    def test_fallback_threshold_when_no_valid_fpr(self) -> None:
        """When no threshold achieves FPR ≤ target, use the last threshold."""
        df = _make_synthetic_df(n_malicious=5, n_benign=5)
        # With only 10 samples, it's unlikely any threshold has FPR ≤ 0.005
        # but the function should not crash.
        model, threshold = train(df)
        assert isinstance(threshold, float)

    def test_trains_with_sha256_column(self) -> None:
        df = _make_synthetic_df()
        df["sha256"] = [f"hash_{i}" for i in range(len(df))]
        df.loc[:19, "sha256"] = "dup"
        model, threshold = train(df)
        assert model is not None
        assert isinstance(threshold, float)


class TestDeduplicate:
    def test_drops_exact_duplicates(self) -> None:
        df = _make_synthetic_df(n_malicious=10, n_benign=10)
        df["sha256"] = ["dup"] * 5 + [f"u{i}" for i in range(len(df) - 5)]
        deduped = _deduplicate(df)
        assert len(deduped) == 16
        assert deduped["sha256"].is_unique

    def test_noop_without_sha256(self) -> None:
        df = _make_synthetic_df(n_malicious=10, n_benign=10)
        assert len(_deduplicate(df)) == len(df)


class TestExportToOnnx:
    def test_export_creates_onnx_file(self) -> None:
        from training.export import export_to_onnx

        df = _make_synthetic_df()
        model, _ = train(df)

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "test_model.onnx")
            export_to_onnx(model, output_path)
            assert Path(output_path).exists()
            assert Path(output_path).stat().st_size > 0

    def test_export_creates_parent_dirs(self) -> None:
        from training.export import export_to_onnx

        df = _make_synthetic_df()
        model, _ = train(df)

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "subdir", "nested", "model.onnx")
            export_to_onnx(model, output_path)
            assert Path(output_path).exists()

    def test_exported_model_runs_inference(self) -> None:
        import onnxruntime as ort

        from training.export import export_to_onnx

        df = _make_synthetic_df()
        model, _ = train(df)

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "model.onnx")
            export_to_onnx(model, output_path)

            session = ort.InferenceSession(output_path)
            dummy = np.zeros((1, len(FEATURE_ORDER)), dtype=np.float32)
            input_name = session.get_inputs()[0].name
            outputs = session.run(None, {input_name: dummy})
            assert len(outputs) >= 2

    def test_export_writes_metadata_sidecar_consumed_by_analyzer(self) -> None:
        import json

        from ml_layer.analyzer import StaticAnalyzer
        from training.export import export_to_onnx

        df = _make_synthetic_df()
        model, threshold = train(df)

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "model.onnx")
            export_to_onnx(model, output_path, threshold=threshold)

            meta_path = Path(tmpdir) / "model.metadata.json"
            assert meta_path.exists()
            metadata = json.loads(meta_path.read_text())
            assert metadata["threshold"] == threshold
            assert metadata["feature_order"] == FEATURE_ORDER

            analyzer = StaticAnalyzer(output_path)
            assert analyzer.threshold == threshold
            assert analyzer.n_features == len(FEATURE_ORDER)

    def test_export_raises_on_bad_onnx_output(self) -> None:
        """Simulate a model whose ONNX export produces fewer than 2 outputs."""
        from training.export import export_to_onnx

        df = _make_synthetic_df()
        model, _ = train(df)

        bad_session = MagicMock()
        bad_session.get_inputs.return_value = [MagicMock(name="float_input")]
        bad_session.run.return_value = [np.array([0])]  # only 1 output

        with (
            patch("training.export.ort.InferenceSession", return_value=bad_session),
            tempfile.TemporaryDirectory() as tmpdir,
        ):
            output_path = os.path.join(tmpdir, "model.onnx")
            with pytest.raises(RuntimeError, match="expected >= 2 outputs"):
                export_to_onnx(model, output_path)

    def test_export_raises_on_wrong_proba_shape(self) -> None:
        """Simulate ONNX output with wrong probability vector shape."""
        from training.export import export_to_onnx

        df = _make_synthetic_df()
        model, _ = train(df)

        bad_proba: dict[str, float] = {"a": 0.5, "b": 0.3, "c": 0.2}  # 3 classes, not 2

        bad_session = MagicMock()
        bad_session.get_inputs.return_value = [MagicMock(name="float_input")]
        bad_session.run.return_value = [np.array([0]), [bad_proba]]

        with (
            patch("training.export.ort.InferenceSession", return_value=bad_session),
            tempfile.TemporaryDirectory() as tmpdir,
        ):
            output_path = os.path.join(tmpdir, "model.onnx")
            with pytest.raises(RuntimeError, match="expected 2 class probabilities"):
                export_to_onnx(model, output_path)


class TestPipeline:
    def test_pipeline_run_end_to_end(self, tmp_path: Path) -> None:
        """Integration test: full pipeline from synthetic data to .onnx file."""
        import io

        import pikepdf

        from training.pipeline import run

        # Build a small dataset directory.
        mal_dir = tmp_path / "malicious"
        ben_dir = tmp_path / "benign"
        mal_dir.mkdir()
        ben_dir.mkdir()

        def _make_pdf(path: Path, pages: int) -> None:
            pdf = pikepdf.Pdf.new()
            for _ in range(pages):
                pdf.add_blank_page(page_size=(612, 792))
            buf = io.BytesIO()
            pdf.save(buf)
            path.write_bytes(buf.getvalue())

        for i in range(10):
            _make_pdf(mal_dir / f"mal_{i}.pdf", pages=i + 1)
            _make_pdf(ben_dir / f"ben_{i}.pdf", pages=i + 11)

        output_path = str(tmp_path / "model.onnx")
        run(str(tmp_path), output_path, max_workers=1)
        assert Path(output_path).exists()

    def test_pipeline_exits_on_empty_dataset(self, tmp_path: Path) -> None:
        from training.pipeline import run

        (tmp_path / "malicious").mkdir()
        (tmp_path / "benign").mkdir()

        with pytest.raises(SystemExit):
            run(str(tmp_path), str(tmp_path / "out.onnx"), max_workers=1)

    def test_main_parses_args_and_calls_run(self, tmp_path: Path) -> None:
        """main() parses CLI args and delegates to run()."""
        import sys
        from unittest.mock import patch

        from training.pipeline import main

        output = str(tmp_path / "out.onnx")
        dataset = str(tmp_path)

        argv = ["pipeline", "--dataset", dataset, "--output", output, "--workers", "2"]
        with patch("training.pipeline.run") as mock_run, patch.object(sys, "argv", argv):
            main()

        mock_run.assert_called_once_with(dataset, output, max_workers=2, cache_path=None)
