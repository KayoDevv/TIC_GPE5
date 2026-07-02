import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from zt_shared.models.events import (
    EmailContext,
    Ioc,
    LlmLayerResultEvent,
    MlLayerResultEvent,
    SandboxLayerResultEvent,
)

from verdict_layer import main
from verdict_layer.main import (
    build_emit_verdict,
    handle_llm_event,
    handle_ml_event,
    handle_sandbox_event,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class TestHandleMlEvent:
    """Tests for the ML event adapter."""

    async def test_calls_saga_with_score(self) -> None:
        saga = AsyncMock()
        job_id = uuid4()
        event = MlLayerResultEvent(
            job_id=job_id,
            risk_score=42,
            static_tags=["high_entropy"],
            timestamp=_now(),
        )

        await handle_ml_event(saga, event)

        saga.on_ml_result.assert_awaited_once_with(str(job_id), score=42)


class TestHandleSandboxEvent:
    """Tests for the Sandbox event adapter."""

    async def test_calls_saga_with_iocs_and_timeout(self) -> None:
        saga = AsyncMock()
        job_id = uuid4()
        event = SandboxLayerResultEvent(
            job_id=job_id,
            iocs=[Ioc(type="domain", value="evil.com")],
            behavior_summary="opened powershell",
            email_context=EmailContext(sender="a@b.com", subject="s", body_text="b"),
            timeout_triggered=False,
            timestamp=_now(),
        )

        await handle_sandbox_event(saga, event)

        saga.on_sandbox_result.assert_awaited_once()
        call = saga.on_sandbox_result.await_args
        assert call.args[0] == str(job_id)
        assert call.kwargs["timeout"] is False
        assert len(call.kwargs["iocs"]) == 1

    async def test_forwards_sandbox_verdict(self) -> None:
        saga = AsyncMock()
        event = SandboxLayerResultEvent(
            job_id=uuid4(),
            verdict="malicious",
            iocs=[],
            behavior_summary="dropper behaviour",
            email_context=EmailContext(sender="a@b.com", subject="s", body_text="b"),
            timeout_triggered=False,
            timestamp=_now(),
        )

        await handle_sandbox_event(saga, event)

        call = saga.on_sandbox_result.await_args
        assert call.kwargs["verdict"] == "malicious"


class TestSandboxTimedOut:
    """Reads timeout across the v2 (top-level) and v3 (analysis_trust) contracts."""

    def test_reads_analysis_trust_when_present(self) -> None:
        v3 = SimpleNamespace(analysis_trust=SimpleNamespace(timeout_triggered=True))
        assert main._sandbox_timed_out(v3) is True

    def test_falls_back_to_top_level_field(self) -> None:
        v2 = SimpleNamespace(analysis_trust=None, timeout_triggered=True)
        assert main._sandbox_timed_out(v2) is True

    def test_defaults_false_when_neither_present(self) -> None:
        assert main._sandbox_timed_out(SimpleNamespace(analysis_trust=None)) is False


class TestHandleLlmEvent:
    """Tests for the LLM event adapter."""

    async def test_calls_saga_with_decision(self) -> None:
        saga = AsyncMock()
        job_id = uuid4()
        event = LlmLayerResultEvent(
            job_id=job_id,
            is_malicious=True,
            explanation_text="malicious intent detected",
            timestamp=_now(),
        )

        await handle_llm_event(saga, event)

        saga.on_llm_result.assert_awaited_once_with(
            str(job_id),
            is_malicious=True,
            explanation="malicious intent detected",
        )


class TestBuildEmitVerdict:
    """Tests for the verdict emission function builder."""

    async def test_emit_publishes_to_kafka(self) -> None:
        publisher = AsyncMock()
        emit = build_emit_verdict(publisher, topic="verdict.result")

        verdict = {
            "job_id": str(uuid4()),
            "final_decision": "allowed",
            "user_explanation": None,
            "technical_summary": None,
            "timestamp": _now().isoformat(),
        }

        await emit(verdict["job_id"], verdict)

        publisher.publish.assert_awaited_once()
        call = publisher.publish.await_args
        assert call.args[0] == "verdict.result"


class TestRunReaper:
    """Tests for the periodic reaper loop."""

    async def test_reaps_then_logs_and_propagates_cancel(self, monkeypatch) -> None:
        saga = AsyncMock()
        saga.reap_expired = AsyncMock(
            side_effect=[None, RuntimeError("boom"), asyncio.CancelledError()]
        )
        monkeypatch.setattr(main.asyncio, "sleep", AsyncMock())

        with pytest.raises(asyncio.CancelledError):
            await main.run_reaper(saga, interval_seconds=0)

        # Ran three iterations: success, swallowed error, then cancellation.
        assert saga.reap_expired.await_count == 3


class TestBuildSubscribers:
    """Tests for the Kafka subscriber wiring."""

    async def test_one_subscriber_per_result_topic(self) -> None:
        settings = main.Settings()
        saga = AsyncMock()

        subscribers = main._build_subscribers(settings, saga)

        assert len(subscribers) == 3


class TestRun:
    """Tests for the run() lifecycle (wiring + teardown)."""

    async def test_wires_components_and_cleans_up(self, monkeypatch) -> None:
        publisher = AsyncMock()
        redis = AsyncMock()
        subscribers = [AsyncMock(), AsyncMock(), AsyncMock()]

        class FakeRedis:
            @staticmethod
            def from_url(*_args, **_kwargs) -> AsyncMock:
                return redis

        def fake_ensure_future(coro):
            coro.close()  # avoid scheduling the infinite reaper / unawaited warnings
            return AsyncMock()

        monkeypatch.setattr(main, "KafkaPublisher", lambda **_kw: publisher)
        monkeypatch.setattr(main, "_build_subscribers", lambda _s, _saga: subscribers)
        monkeypatch.setattr(main, "Redis", FakeRedis)
        monkeypatch.setattr(main.asyncio, "ensure_future", fake_ensure_future)
        monkeypatch.setattr(main.asyncio, "gather", AsyncMock())

        await main.run()

        publisher.start.assert_awaited_once()
        publisher.stop.assert_awaited_once()
        redis.aclose.assert_awaited_once()
        for sub in subscribers:
            sub.stop.assert_awaited_once()


class TestMainEntrypoint:
    """Tests for the synchronous CLI entry point."""

    def test_invokes_asyncio_run(self, monkeypatch) -> None:
        ran = {}

        def fake_run(coro) -> None:
            coro.close()
            ran["called"] = True

        monkeypatch.setattr(main.asyncio, "run", fake_run)

        main.main()

        assert ran["called"] is True
