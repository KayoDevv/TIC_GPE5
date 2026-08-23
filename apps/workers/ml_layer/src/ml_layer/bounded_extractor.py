"""Runs feature extraction off the event loop, under a hard time budget.

Extraction is attacker-controlled work: it runs in a separate process so a
pathological PDF cannot pin a worker thread, and the child arms its own alarm so
the budget is enforced where the parsing happens. The parent keeps a slightly
longer backstop for the case where the child is stuck inside a C call and never
reaches a point where its alarm can be delivered; that child is abandoned rather
than awaited, so a repeated backstop is a signal to look at the pool size.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import Executor

from ml_layer.features.extraction import FeatureExtractionTimeout, extract_within_timeout

_BACKSTOP_MESSAGE = "PDF feature extraction did not return within its time budget"


def _discard_late_result(future: asyncio.Future[dict[str, float]]) -> None:
    if not future.cancelled():
        future.exception()


class BoundedFeatureExtractor:
    def __init__(self, executor: Executor, timeout_s: int, result_margin_s: int) -> None:
        self._executor = executor
        self._timeout_s = timeout_s
        self._result_margin_s = result_margin_s

    async def extract(self, data: bytes) -> dict[str, float]:
        loop = asyncio.get_running_loop()
        pending = loop.run_in_executor(
            self._executor, extract_within_timeout, data, self._timeout_s
        )
        try:
            return await asyncio.wait_for(
                asyncio.shield(pending), timeout=self._timeout_s + self._result_margin_s
            )
        except FeatureExtractionTimeout:
            raise
        except TimeoutError as exc:
            pending.add_done_callback(_discard_late_result)
            raise FeatureExtractionTimeout(_BACKSTOP_MESSAGE) from exc
