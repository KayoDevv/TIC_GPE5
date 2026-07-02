import time
from unittest.mock import AsyncMock

import fakeredis.aioredis
import pytest

from verdict_layer.decision_matrix import JobState
from verdict_layer.state_store import StateStore


@pytest.fixture
async def redis_client():
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield client
    await client.flushall()
    await client.aclose()


@pytest.fixture
def store(redis_client):
    return StateStore(redis_client, ttl_seconds=300, lock_ttl_seconds=3600)


class TestUpdateAndGet:
    async def test_update_ml_then_get(self, store) -> None:
        await store.update_ml("job-1", score=42)
        state = await store.get_state("job-1")
        assert state.ml_score == 42

    async def test_update_sandbox_then_get(self, store) -> None:
        iocs = [{"type": "domain", "value": "evil.com"}]
        await store.update_sandbox("job-2", iocs=iocs, timeout=False)
        state = await store.get_state("job-2")
        assert state.sandbox_received is True
        assert state.sandbox_timeout is False
        assert state.sandbox_iocs == iocs

    async def test_update_sandbox_stores_verdict(self, store) -> None:
        await store.update_sandbox("job-v", iocs=[], timeout=False, verdict="malicious")
        state = await store.get_state("job-v")
        assert state.sandbox_verdict == "malicious"

    async def test_update_sandbox_without_verdict_is_none(self, store) -> None:
        await store.update_sandbox("job-nv", iocs=[], timeout=False)
        state = await store.get_state("job-nv")
        assert state.sandbox_verdict is None

    async def test_update_llm_then_get(self, store) -> None:
        await store.update_llm("job-3", is_malicious=True, explanation="bad stuff")
        state = await store.get_state("job-3")
        assert state.llm_is_malicious is True
        assert state.llm_explanation == "bad stuff"

    async def test_partial_merge(self, store) -> None:
        await store.update_ml("job-4", score=10)
        await store.update_sandbox("job-4", iocs=[], timeout=False)
        await store.update_llm("job-4", is_malicious=False, explanation="clean")
        state = await store.get_state("job-4")
        assert state.ml_score == 10
        assert state.sandbox_received is True
        assert state.llm_is_malicious is False

    async def test_get_unknown_job_returns_empty_state(self, store) -> None:
        state = await store.get_state("does-not-exist")
        assert isinstance(state, JobState)
        assert state.ml_score is None
        assert state.sandbox_received is False
        assert state.llm_is_malicious is None


class TestTimeout:
    async def test_mark_sandbox_timeout(self, store) -> None:
        await store.update_ml("job-timeout", score=20)
        await store.mark_sandbox_timeout("job-timeout")
        state = await store.get_state("job-timeout")
        assert state.sandbox_timeout is True


class TestCompletion:
    async def test_is_complete_false_when_partial(self, store) -> None:
        await store.update_ml("job-partial", score=10)
        assert await store.is_complete("job-partial") is False

    async def test_is_complete_true_when_all_received(self, store) -> None:
        await store.update_ml("job-full", score=10)
        await store.update_sandbox("job-full", iocs=[], timeout=False)
        await store.update_llm("job-full", is_malicious=False, explanation="clean")
        assert await store.is_complete("job-full") is True

    async def test_is_complete_true_when_sandbox_timed_out(self, store) -> None:
        await store.update_ml("job-timeout-complete", score=10)
        await store.mark_sandbox_timeout("job-timeout-complete")
        await store.update_llm("job-timeout-complete", is_malicious=False, explanation="clean")
        assert await store.is_complete("job-timeout-complete") is True

    async def test_is_complete_true_on_terminal_verdict_without_llm(self, store) -> None:
        # F-A: a terminal sandbox verdict means no LLM result is coming.
        await store.update_ml("job-term", score=10)
        await store.update_sandbox("job-term", iocs=[], timeout=False, verdict="benign")
        assert await store.is_complete("job-term") is True

    async def test_is_complete_true_on_sandbox_timeout_without_llm(self, store) -> None:
        await store.update_ml("job-to", score=10)
        await store.update_sandbox("job-to", iocs=[], timeout=True, verdict=None)
        assert await store.is_complete("job-to") is True

    async def test_is_complete_false_on_grey_verdict_without_llm(self, store) -> None:
        # needs_more_context still escalates to the LLM -> not complete yet.
        await store.update_ml("job-grey", score=10)
        await store.update_sandbox(
            "job-grey", iocs=[], timeout=False, verdict="needs_more_context"
        )
        assert await store.is_complete("job-grey") is False

    async def test_is_complete_false_on_unknown_verdict_without_llm(self, store) -> None:
        # None verdict is unknown -> the LLM runs (silence is not benign).
        await store.update_ml("job-unk", score=10)
        await store.update_sandbox("job-unk", iocs=[], timeout=False, verdict=None)
        assert await store.is_complete("job-unk") is False


class TestArrivalTimestamp:
    async def test_first_update_sets_arrival(self, store, redis_client) -> None:
        await store.update_ml("job-arr", score=10)
        arrival = await redis_client.get("verdict:arrival:job-arr")
        assert arrival is not None

    async def test_arrival_not_overwritten(self, store, redis_client) -> None:
        await store.update_ml("job-arr2", score=10)
        first = await redis_client.get("verdict:arrival:job-arr2")
        await store.update_llm("job-arr2", is_malicious=False, explanation="x")
        second = await redis_client.get("verdict:arrival:job-arr2")
        assert first == second


class TestScanExpired:
    async def test_scan_returns_old_job_without_sandbox(self, store) -> None:
        await store.update_ml("job-old", score=10)
        await store._redis.set("verdict:arrival:job-old", str(time.time() - 200))
        expired = await store.scan_expired(timeout_seconds=125)
        assert "job-old" in expired

    async def test_scan_ignores_recent_job(self, store) -> None:
        await store.update_ml("job-recent", score=10)
        expired = await store.scan_expired(timeout_seconds=125)
        assert "job-recent" not in expired

    async def test_scan_ignores_job_with_sandbox(self, store) -> None:
        await store.update_ml("job-has-sandbox", score=10)
        await store.update_sandbox("job-has-sandbox", iocs=[], timeout=False)
        await store._redis.set("verdict:arrival:job-has-sandbox", str(time.time() - 200))
        expired = await store.scan_expired(timeout_seconds=125)
        assert "job-has-sandbox" not in expired


class TestVerdictLock:
    async def test_first_acquire_succeeds(self, store) -> None:
        assert await store.try_acquire_verdict_lock("job-lock-1") is True

    async def test_second_acquire_fails(self, store) -> None:
        await store.try_acquire_verdict_lock("job-lock-2")
        assert await store.try_acquire_verdict_lock("job-lock-2") is False

    async def test_release_allows_reacquire(self, store) -> None:
        await store.try_acquire_verdict_lock("job-lock-3")
        await store.release_verdict_lock("job-lock-3")
        assert await store.try_acquire_verdict_lock("job-lock-3") is True

    async def test_lock_has_ttl(self, store, redis_client) -> None:
        await store.try_acquire_verdict_lock("job-lock-ttl")
        ttl = await redis_client.ttl("verdict:lock:job-lock-ttl")
        assert ttl > 0

    async def test_lock_uses_dedicated_ttl(self, store, redis_client) -> None:
        await store.try_acquire_verdict_lock("job-lock-long")
        ttl = await redis_client.ttl("verdict:lock:job-lock-long")
        # Lock TTL (3600) must exceed the state TTL (300)
        assert ttl > 300


class TestCleanup:
    async def test_clear_removes_state_and_arrival(self, store, redis_client) -> None:
        await store.update_ml("job-clear", score=10)
        await store.clear("job-clear")
        state = await store.get_state("job-clear")
        assert state.ml_score is None
        assert await redis_client.get("verdict:arrival:job-clear") is None


class TestScanExpiredEdgeCases:
    async def test_skips_keys_whose_arrival_vanished(self) -> None:
        redis = AsyncMock()

        async def fake_scan_iter(match: str):
            yield "verdict:arrival:ghost"

        redis.scan_iter = fake_scan_iter
        redis.get = AsyncMock(return_value=None)
        store = StateStore(redis, ttl_seconds=300)

        assert await store.scan_expired(125) == []
