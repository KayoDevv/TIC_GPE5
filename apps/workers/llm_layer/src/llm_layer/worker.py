"""Imperative shell: wires the shared Kafka helpers to the analysis pipeline.

Consumes ``sandbox_layer.result`` (validated into :class:`SandboxResultIn` so the
optional ``_meta`` is captured) and publishes ``llm_layer.result``
(:class:`LlmLayerResultEvent`). The worker is I/O-bound (Kafka + network on the
LLM), so a single asyncio worker handles many concurrent analyses.
"""

from __future__ import annotations

import asyncio
import logging
import signal

from zt_shared.kafka import KafkaPublisher, KafkaSubscriber

from llm_layer.circuit_breaker import CircuitBreaker
from llm_layer.config import Settings, load_settings
from llm_layer.decision import degraded_result
from llm_layer.guard import SandboxInputRegression
from llm_layer.llm_client import LLMClient
from llm_layer.models import SandboxResultIn
from llm_layer.pipeline import analyse

log = logging.getLogger("llm_layer.worker")


class LlmLayerWorker:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = LLMClient(
            inference=settings.inference,
            timeout_s=settings.request_timeout_s,
            guided_decoding=settings.guided_decoding,
        )
        self.breaker = CircuitBreaker(self.client, settings.primary, settings.fallback)
        self.publisher = KafkaPublisher(
            bootstrap_servers=settings.kafka_bootstrap, client_id="llm-layer"
        )
        self.subscriber = KafkaSubscriber(
            bootstrap_servers=settings.kafka_bootstrap,
            group_id=settings.consumer_group,
            topic=settings.topic_in,
            model=SandboxResultIn,
            handler=self._handle,
        )

    async def _handle(self, event: SandboxResultIn) -> None:
        try:
            result = await analyse(event, self.breaker)
        except SandboxInputRegression as exc:
            # Contract violation by the sandbox layer: surface loudly, then
            # publish a cautious degraded result so the Saga still completes.
            log.error("SANDBOX REGRESSION job_id=%s: %s", event.job_id, exc)
            result = degraded_result(event, reason="sandbox input regression")

        await self.publisher.publish(self.settings.topic_out, result)
        log.info(
            "published job_id=%s is_malicious=%s confidence=%s",
            result.job_id, result.is_malicious, result.confidence_score,
        )

    async def run(self) -> None:
        await self.publisher.start()
        log.info(
            "LLM Layer started profile=%s in=%s out=%s guided=%s",
            self.settings.profile.value, self.settings.topic_in,
            self.settings.topic_out, self.settings.guided_decoding,
        )
        try:
            await self.subscriber.start()  # blocks in the consume loop
        finally:
            await self.stop()

    async def stop(self) -> None:
        await self.subscriber.stop()
        await self.publisher.stop()
        await self.client.aclose()
        log.info("LLM Layer stopped")


async def main() -> None:  # pragma: no cover
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    worker = LlmLayerWorker(load_settings())
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(worker.stop()))
    await worker.run()


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(main())
