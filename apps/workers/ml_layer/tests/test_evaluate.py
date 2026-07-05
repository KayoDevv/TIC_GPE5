"""Tests for training.evaluate — false-positive-focused model evaluation."""

from __future__ import annotations

import io
from pathlib import Path

import pandas as pd
import pikepdf

from training.evaluate import _hard_negative_mask, evaluate
from training.export import export_to_onnx
from training.ingest import load_dataset
from training.train import train


def _write_pdf(path: Path, pages: int = 1, javascript: bool = False) -> None:
    pdf = pikepdf.Pdf.new()
    for _ in range(pages):
        pdf.add_blank_page(page_size=(612, 792))
    if javascript:
        action = pikepdf.Dictionary(
            S=pikepdf.Name("/JavaScript"), JS=pikepdf.String("app.alert(1)")
        )
        names = pikepdf.Array([pikepdf.String("x"), action])
        pdf.Root["/Names"] = pikepdf.Dictionary(JavaScript=pikepdf.Dictionary(Names=names))
    buf = io.BytesIO()
    pdf.save(buf)
    path.write_bytes(buf.getvalue())


def _build_dataset(tmp_path: Path) -> Path:
    mal = tmp_path / "malicious"
    ben = tmp_path / "benign"
    mal.mkdir()
    ben.mkdir()
    for i in range(8):
        _write_pdf(mal / f"m{i}.pdf", pages=i + 1, javascript=True)
        _write_pdf(ben / f"b{i}.pdf", pages=i + 11, javascript=False)
    _write_pdf(ben / "hard_negative.pdf", pages=30, javascript=True)
    return tmp_path


class TestHardNegativeMask:
    def test_flags_rows_with_suspicious_structure(self) -> None:
        df = pd.DataFrame(
            {
                "pdf_has_javascript": [1.0, 0.0, 0.0],
                "pdf_has_openaction": [0.0, 1.0, 0.0],
                "pdf_has_launch": [0.0, 0.0, 0.0],
            }
        )
        assert _hard_negative_mask(df).tolist() == [True, True, False]


class TestEvaluate:
    def test_reports_false_positive_metrics(self, tmp_path: Path) -> None:
        dataset = _build_dataset(tmp_path)

        model, threshold = train(load_dataset(str(dataset)))
        model_path = tmp_path / "model.onnx"
        export_to_onnx(model, str(model_path), threshold=threshold)

        metrics = evaluate(str(dataset), str(model_path), output_csv=str(tmp_path / "fp.csv"))

        assert metrics["n_total"] > 0
        assert metrics["n_hard_negative_benign"] >= 1  # the JS-carrying benign file
        for key in ("fpr", "fpr_hard_negatives", "recall"):
            assert 0.0 <= metrics[key] <= 1.0
        assert (tmp_path / "fp.csv").exists()
