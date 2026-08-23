"""Entry point: wires Redis, Kafka consumers/producer, the reaper, and the saga."""

import asyncio
import logging
from typing import Any

from redis.asyncio import Redis
from zt_shared.kafka import KafkaPublisher, KafkaSubscriber
from zt_shared.models.events import (
    LlmLayerResultEvent,
    MlLayerResultEvent,
    SandboxLayerResultEvent,
    VerdictResultEvent,
)

from verdict_layer.config import Settings
from verdict_layer.saga import EmitFn, VerdictSaga
from verdict_layer.state_store import StateStore

logger = logging.getLogger(__name__)


async def handle_ml_event(saga: VerdictSaga, event: MlLayerResultEvent) -> None:
    await saga.on_ml_result(
        str(event.job_id), score=event.risk_score, status=event.analysis_status
    )


def _sandbox_timed_out(event: SandboxLayerResultEvent) -> bool:
    # Contract v3 moved the flag into analysis_trust; fall back to the legacy
    # top-level field so this consumer works across the v2 -> v3 migration.
    trust = getattr(event, "analysis_trust", None)
    if trust is not None:
        return bool(trust.timeout_triggered)
    return bool(getattr(event, "timeout_triggered", False))


async def handle_sandbox_event(saga: VerdictSaga, event: SandboxLayerResultEvent) -> None:
    iocs = [ioc.model_dump() for ioc in event.iocs]
    await saga.on_sandbox_result(
        str(event.job_id),
        iocs=iocs,
        timeout=_sandbox_timed_out(event),
        verdict=event.verdict,
    )


async def handle_llm_event(saga: VerdictSaga, event: LlmLayerResultEvent) -> None:
    await saga.on_llm_result(
        str(event.job_id),
        is_malicious=event.is_malicious,
        explanation=event.explanation_text,
    )


def build_emit_verdict(publisher: KafkaPublisher, topic: str) -> EmitFn:
    async def emit(job_id: str, verdict: dict[str, Any]) -> None:
        event = VerdictResultEvent.model_validate(verdict)
        await publisher.publish(topic, event)

    return emit


async def run_reaper(saga: VerdictSaga, interval_seconds: int) -> None:
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            await saga.reap_expired()
        except Exception:
            logger.exception("Reaper iteration failed")


def _build_subscribers(settings: Settings, saga: VerdictSaga) -> list[KafkaSubscriber]:
    prefix = settings.kafka_consumer_group_prefix
    return [
        KafkaSubscriber(
            bootstrap_servers=settings.kafka_bootstrap_servers,
            group_id=f"{prefix}-ml",
            topic=settings.kafka_topic_ml_result,
            model=MlLayerResultEvent,
            handler=lambda e: handle_ml_event(saga, e),
        ),
        KafkaSubscriber(
            bootstrap_servers=settings.kafka_bootstrap_servers,
            group_id=f"{prefix}-sandbox",
            topic=settings.kafka_topic_sandbox_result,
            model=SandboxLayerResultEvent,
            handler=lambda e: handle_sandbox_event(saga, e),
        ),
        KafkaSubscriber(
            bootstrap_servers=settings.kafka_bootstrap_servers,
            group_id=f"{prefix}-llm",
            topic=settings.kafka_topic_llm_result,
            model=LlmLayerResultEvent,
            handler=lambda e: handle_llm_event(saga, e),
        ),
    ]


async def run() -> None:
    settings = Settings()
    logging.basicConfig(level=logging.INFO)

    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    store = StateStore(
        redis,
        ttl_seconds=settings.redis_state_ttl_seconds,
        lock_ttl_seconds=settings.redis_lock_ttl_seconds,
    )

    publisher = KafkaPublisher(
        bootstrap_servers=settings.kafka_bootstrap_servers,
        client_id=settings.kafka_consumer_group_prefix,
    )
    await publisher.start()

    saga = VerdictSaga(
        store=store,
        emit_verdict=build_emit_verdict(publisher, settings.kafka_topic_verdict_result),
        ml_block_threshold=settings.ml_block_threshold,
        timeout_default=settings.default_timeout_verdict,
        sandbox_timeout_seconds=settings.sandbox_timeout_seconds,
        ml_abstain_verdict=settings.ml_abstain_verdict,
    )

    subscribers = _build_subscribers(settings, saga)

    logger.info("Verdict Layer started.")
    tasks = [asyncio.ensure_future(sub.start()) for sub in subscribers]
    tasks.append(asyncio.ensure_future(run_reaper(saga, settings.reaper_interval_seconds)))

    try:
        await asyncio.gather(*tasks)
    finally:
        for sub in subscribers:
            await sub.stop()
        await publisher.stop()
        await redis.aclose()
        logger.info("Verdict Layer stopped.")


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":  # pragma: no cover
    main()
