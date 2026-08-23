"""Tests for the SIGALRM-guarded feature extraction shared by training and production."""

from __future__ import annotations

import io
import signal

import pikepdf
import pytest

from ml_layer.features.extraction import (
    FeatureExtractionTimeout,
    _raise_extraction_timeout,
    extract_within_timeout,
)
from ml_layer.features.pdf import FEATURE_ORDER

_TIMEOUT_S = 5


def _minimal_pdf() -> bytes:
    pdf = pikepdf.Pdf.new()
    pdf.add_blank_page(page_size=(612, 792))
    buf = io.BytesIO()
    pdf.save(buf)
    return buf.getvalue()


def test_extracts_the_full_feature_vector() -> None:
    features = extract_within_timeout(_minimal_pdf(), _TIMEOUT_S)

    assert set(features) == set(FEATURE_ORDER)


def test_alarm_handler_raises_the_extraction_timeout() -> None:
    with pytest.raises(FeatureExtractionTimeout):
        _raise_extraction_timeout(signal.SIGALRM, None)


def test_alarm_is_disarmed_after_a_failed_extraction(monkeypatch: pytest.MonkeyPatch) -> None:
    def _explode(self: object, data: bytes) -> dict[str, float]:
        raise RuntimeError("parser blew up")

    monkeypatch.setattr(
        "ml_layer.features.extraction.PDFFeatureExtractor.extract", _explode
    )

    with pytest.raises(RuntimeError):
        extract_within_timeout(b"%PDF-1.7", _TIMEOUT_S)

    assert signal.alarm(0) == 0


def test_a_slow_extraction_is_interrupted(monkeypatch: pytest.MonkeyPatch) -> None:
    def _hang(self: object, data: bytes) -> dict[str, float]:
        while True:
            pass

    monkeypatch.setattr("ml_layer.features.extraction.PDFFeatureExtractor.extract", _hang)

    with pytest.raises(FeatureExtractionTimeout):
        extract_within_timeout(b"%PDF-1.7", 1)
