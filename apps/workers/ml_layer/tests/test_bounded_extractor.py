"""Tests for the off-loop extraction wrapper and its parent-side backstop."""

from __future__ import annotations

import io
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from typing import Iterator

import pikepdf
import pytest

from ml_layer.bounded_extractor import BoundedFeatureExtractor, _discard_late_result
from ml_layer.features.extraction import FeatureExtractionTimeout

_TIMEOUT_S = 1
_MARGIN_S = 1


@pytest.fixture()
def executor() -> Iterator[ThreadPoolExecutor]:
    pool = ThreadPoolExecutor(max_workers=2)
    yield pool
    pool.shutdown(wait=False)


def _extractor(executor: ThreadPoolExecutor) -> BoundedFeatureExtractor:
    return BoundedFeatureExtractor(
        executor=executor, timeout_s=_TIMEOUT_S, result_margin_s=_MARGIN_S
    )


async def test_returns_the_extracted_features(
    executor: ThreadPoolExecutor, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "ml_layer.bounded_extractor.extract_within_timeout",
        lambda data, timeout_s: {"entropy": 1.0},
    )

    features = await _extractor(executor).extract(b"%PDF-1.7")

    assert features == {"entropy": 1.0}


async def test_child_timeout_propagates_unwrapped(
    executor: ThreadPoolExecutor, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _timed_out(data: bytes, timeout_s: int) -> dict[str, float]:
        raise FeatureExtractionTimeout("child alarm fired")

    monkeypatch.setattr("ml_layer.bounded_extractor.extract_within_timeout", _timed_out)

    with pytest.raises(FeatureExtractionTimeout, match="child alarm fired"):
        await _extractor(executor).extract(b"%PDF-1.7")


async def test_backstop_fires_when_the_child_never_returns(
    executor: ThreadPoolExecutor, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _sleep_past_the_backstop(data: bytes, timeout_s: int) -> dict[str, float]:
        time.sleep(_TIMEOUT_S + _MARGIN_S + 1)
        return {}

    monkeypatch.setattr(
        "ml_layer.bounded_extractor.extract_within_timeout", _sleep_past_the_backstop
    )

    with pytest.raises(FeatureExtractionTimeout, match="did not return"):
        await _extractor(executor).extract(b"%PDF-1.7")


class _StubFuture:
    def __init__(self, cancelled: bool) -> None:
        self._cancelled = cancelled
        self.exception_retrieved = False

    def cancelled(self) -> bool:
        return self._cancelled

    def exception(self) -> None:
        self.exception_retrieved = True


def test_late_result_of_an_abandoned_child_is_retrieved() -> None:
    future = _StubFuture(cancelled=False)

    _discard_late_result(future)  # type: ignore[arg-type]

    assert future.exception_retrieved is True


def test_late_result_of_a_cancelled_child_is_left_alone() -> None:
    future = _StubFuture(cancelled=True)

    _discard_late_result(future)  # type: ignore[arg-type]

    assert future.exception_retrieved is False


async def test_extracts_through_a_real_process_pool() -> None:
    pdf = pikepdf.Pdf.new()
    pdf.add_blank_page(page_size=(612, 792))
    buf = io.BytesIO()
    pdf.save(buf)

    pool = ProcessPoolExecutor(max_workers=1)
    try:
        extractor = BoundedFeatureExtractor(
            executor=pool, timeout_s=10, result_margin_s=5
        )
        features = await extractor.extract(buf.getvalue())
    finally:
        pool.shutdown(wait=False)

    assert features["pdf_page_count"] == 1.0
