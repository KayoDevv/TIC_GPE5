import fakeredis.aioredis
import pytest

from verdict_layer.saga import VerdictSaga
from verdict_layer.state_store import StateStore


@pytest.fixture
async def redis_client():
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield client
    await client.flushall()
    await client.aclose()


@pytest.fixture
def store(redis_client):
    return StateStore(redis_client, ttl_seconds=300)


class _EmitRecorder:
    def __init__(self, fail: bool = False) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.fail = fail

    async def emit(self, job_id: str, verdict: dict) -> None:
        if self.fail:
            raise RuntimeError("kafka down")
        self.calls.append((job_id, verdict))


def _make_saga(store, emitter, timeout_seconds=125) -> VerdictSaga:
    return VerdictSaga(
        store=store,
        emit_verdict=emitter.emit,
        ml_block_threshold=90,
        ml_solo_block_threshold=98,
        timeout_default="warning",
        sandbox_timeout_seconds=timeout_seconds,
        ml_abstain_verdict="warning",
    )


class TestMlCritical:
    async def test_high_ml_alone_does_not_emit(self, store) -> None:
        emitter = _EmitRecorder()
        saga = _make_saga(store, emitter)
        await saga.on_ml_result("job-1", score=95, status="completed")
        assert emitter.calls == []

    async def test_high_ml_with_malicious_sandbox_blocks(self, store) -> None:
        emitter = _EmitRecorder()
        saga = _make_saga(store, emitter)
        await saga.on_ml_result("job-1", score=95, status="completed")
        await saga.on_sandbox_result("job-1", iocs=[], timeout=False, verdict="malicious")
        assert len(emitter.calls) == 1
        assert emitter.calls[0][1]["final_decision"] == "blocked"

    async def test_high_ml_cleared_by_benign_sandbox_warns(self, store) -> None:
        emitter = _EmitRecorder()
        saga = _make_saga(store, emitter)
        await saga.on_ml_result("job-1", score=99, status="completed")
        await saga.on_sandbox_result("job-1", iocs=[], timeout=False, verdict="benign")
        assert len(emitter.calls) == 1
        assert emitter.calls[0][1]["final_decision"] == "warning"


class TestCompletion:
    async def test_all_clean_emits_allowed(self, store) -> None:
        emitter = _EmitRecorder()
        saga = _make_saga(store, emitter)
        await saga.on_ml_result("job-3", score=10, status="completed")
        await saga.on_sandbox_result("job-3", iocs=[], timeout=False)
        await saga.on_llm_result("job-3", is_malicious=False, explanation="clean")
        assert len(emitter.calls) == 1
        assert emitter.calls[0][1]["final_decision"] == "allowed"

    async def test_llm_malicious_emits_blocked(self, store) -> None:
        emitter = _EmitRecorder()
        saga = _make_saga(store, emitter)
        await saga.on_ml_result("job-4", score=10, status="completed")
        await saga.on_sandbox_result("job-4", iocs=[], timeout=False)
        await saga.on_llm_result("job-4", is_malicious=True, explanation="malicious")
        assert len(emitter.calls) == 1
        assert emitter.calls[0][1]["final_decision"] == "blocked"

    async def test_no_emission_while_incomplete(self, store) -> None:
        emitter = _EmitRecorder()
        saga = _make_saga(store, emitter)
        await saga.on_ml_result("job-5", score=10, status="completed")
        await saga.on_sandbox_result("job-5", iocs=[], timeout=False)
        assert len(emitter.calls) == 0

    async def test_terminal_benign_verdict_emits_allowed_without_llm(self, store) -> None:
        # F-A: a terminal sandbox verdict must resolve without waiting for the LLM.
        emitter = _EmitRecorder()
        saga = _make_saga(store, emitter)
        await saga.on_ml_result("job-10", score=10, status="completed")
        await saga.on_sandbox_result("job-10", iocs=[], timeout=False, verdict="benign")
        assert len(emitter.calls) == 1
        assert emitter.calls[0][1]["final_decision"] == "allowed"

    async def test_terminal_malicious_verdict_emits_blocked_without_llm(self, store) -> None:
        emitter = _EmitRecorder()
        saga = _make_saga(store, emitter)
        await saga.on_ml_result("job-11", score=10, status="completed")
        await saga.on_sandbox_result("job-11", iocs=[], timeout=False, verdict="malicious")
        assert len(emitter.calls) == 1
        assert emitter.calls[0][1]["final_decision"] == "blocked"


class TestReaper:
    async def test_reap_emits_warning_for_expired_job(self, store) -> None:
        import time

        emitter = _EmitRecorder()
        saga = _make_saga(store, emitter, timeout_seconds=125)
        await saga.on_ml_result("job-6", score=10, status="completed")
        # Force the arrival into the past so the job is considered expired
        await store._redis.set("verdict:arrival:job-6", str(time.time() - 200))

        await saga.reap_expired()

        assert len(emitter.calls) == 1
        assert emitter.calls[0][1]["final_decision"] == "warning"

    async def test_reap_ignores_recent_job(self, store) -> None:
        emitter = _EmitRecorder()
        saga = _make_saga(store, emitter)
        await saga.on_ml_result("job-7", score=10, status="completed")
        await saga.reap_expired()
        assert len(emitter.calls) == 0


class TestNoDoubleEmission:
    async def test_events_after_resolution_are_ignored(self, store) -> None:
        emitter = _EmitRecorder()
        saga = _make_saga(store, emitter)
        await saga.on_ml_result("job-8", score=99, status="completed")
        await saga.on_sandbox_result("job-8", iocs=[], timeout=False)
        await saga.on_llm_result("job-8", is_malicious=True, explanation="late")
        assert len(emitter.calls) == 1


class TestEmitFailure:
    async def test_lock_released_when_emit_fails(self, store) -> None:
        emitter = _EmitRecorder(fail=True)
        saga = _make_saga(store, emitter)

        await saga.on_ml_result("job-9", score=95, status="completed")
        with pytest.raises(RuntimeError):
            await saga.on_sandbox_result("job-9", iocs=[], timeout=False, verdict="malicious")

        # Lock must be free again so a retry can re-resolve
        assert await store.try_acquire_verdict_lock("job-9") is True

    async def test_retry_succeeds_after_emit_failure(self, store) -> None:
        failing = _EmitRecorder(fail=True)
        saga_fail = _make_saga(store, failing)
        await saga_fail.on_ml_result("job-10", score=95, status="completed")
        with pytest.raises(RuntimeError):
            await saga_fail.on_sandbox_result("job-10", iocs=[], timeout=False, verdict="malicious")

        working = _EmitRecorder()
        saga_ok = _make_saga(store, working)
        await saga_ok.on_sandbox_result("job-10", iocs=[], timeout=False, verdict="malicious")
        assert len(working.calls) == 1

    async def test_resolve_skips_when_lock_already_held(self, store) -> None:
        emitter = _EmitRecorder()
        saga = _make_saga(store, emitter)
        assert await store.try_acquire_verdict_lock("job-11") is True

        await saga.on_ml_result("job-11", score=99, status="completed")
        await saga.on_sandbox_result("job-11", iocs=[], timeout=False, verdict="malicious")

        assert emitter.calls == []
