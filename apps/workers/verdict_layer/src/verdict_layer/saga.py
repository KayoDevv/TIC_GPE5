"""Saga orchestrator: aggregates layer results into a single verdict per job."""

import logging
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from verdict_layer.decision_matrix import VerdictDecision, decide
from verdict_layer.state_store import StateStore

logger = logging.getLogger(__name__)

EmitFn = Callable[[str, dict[str, Any]], Awaitable[None]]


class VerdictSaga:
    def __init__(
        self,
        store: StateStore,
        emit_verdict: EmitFn,
        ml_block_threshold: int,
        timeout_default: str,
        sandbox_timeout_seconds: int,
    ) -> None:
        self._store = store
        self._emit = emit_verdict
        self._ml_threshold = ml_block_threshold
        self._timeout_default = timeout_default
        self._timeout_seconds = sandbox_timeout_seconds

    async def on_ml_result(self, job_id: str, score: int) -> None:
        await self._store.update_ml(job_id, score=score)
        await self._resolve_if_complete(job_id)

    async def on_sandbox_result(
        self,
        job_id: str,
        iocs: list[dict[str, Any]],
        timeout: bool,
        verdict: str | None = None,
    ) -> None:
        await self._store.update_sandbox(job_id, iocs=iocs, timeout=timeout, verdict=verdict)
        await self._resolve_if_complete(job_id)

    async def on_llm_result(self, job_id: str, is_malicious: bool, explanation: str) -> None:
        await self._store.update_llm(job_id, is_malicious=is_malicious, explanation=explanation)
        await self._resolve_if_complete(job_id)

    async def reap_expired(self) -> None:
        for job_id in await self._store.scan_expired(self._timeout_seconds):
            logger.warning("Sandbox timeout reached for job %s", job_id)
            await self._store.mark_sandbox_timeout(job_id)
            await self._resolve(job_id)

    async def _resolve_if_complete(self, job_id: str) -> None:
        if await self._store.is_complete(job_id):
            await self._resolve(job_id)

    def _build_verdict(self, job_id: str, decision: VerdictDecision) -> dict[str, Any]:
        return {
            "job_id": job_id,
            "final_decision": decision.final_decision,
            "user_explanation": decision.user_explanation,
            "technical_summary": decision.technical_summary,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def _resolve(self, job_id: str) -> None:
        if not await self._store.try_acquire_verdict_lock(job_id):
            return

        state = await self._store.get_state(job_id)
        decision = decide(
            state,
            ml_block_threshold=self._ml_threshold,
            timeout_default=self._timeout_default,
        )
        verdict = self._build_verdict(job_id, decision)

        try:
            await self._emit(job_id, verdict)
        except Exception:
            await self._store.release_verdict_lock(job_id)
            logger.exception("Emit failed for job %s, lock released for retry", job_id)
            raise

        await self._store.clear(job_id)
        logger.info("Verdict emitted for job %s: %s", job_id, decision.final_decision)
