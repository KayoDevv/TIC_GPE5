import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import boto3
import httpx
from zt_shared.kafka.consumer import KafkaSubscriber
from zt_shared.kafka.producer import KafkaPublisher
from zt_shared.models.events import FileRequestedEvent, MlLayerResultEvent

from ml_layer.analyzer import StaticAnalyzer
from ml_layer.config import get_config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("ml_layer.worker")

# Hard SLA for the ML Layer (see CLAUDE.md). Breaches are logged as warnings so
# the latency budget can be monitored without changing the verdict contract.
ML_SLA_MS = 500


class MlWorker:
    def __init__(self) -> None:
        self.config = get_config()
        self.publisher = KafkaPublisher(bootstrap_servers=self.config.kafka.bootstrap_servers)
        self.subscriber = KafkaSubscriber(
            bootstrap_servers=self.config.kafka.bootstrap_servers,
            group_id=self.config.kafka.group_id,
            topic=self.config.kafka.topic_in,
            model=FileRequestedEvent,
            handler=self.handle_event,
        )
        if not os.path.exists(self.config.model_path):
            raise FileNotFoundError(
                f"Model file not found at {self.config.model_path}. Aborting worker..."
            )

        self.analyzer = StaticAnalyzer(self.config.model_path)
        self._s3_client: Any = None

    def _get_s3_client(self) -> Any:
        if self._s3_client is None:
            self._s3_client = boto3.client(
                "s3",
                endpoint_url=self.config.minio_endpoint,
                aws_access_key_id=self.config.aws_access_key,
                aws_secret_access_key=self.config.aws_secret_key,
            )
        return self._s3_client

    async def _download_file(self, url: str) -> bytes:
        if url.startswith(("http://", "https://")):
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, timeout=30.0)
                resp.raise_for_status()
                return resp.content
        elif url.startswith("s3://"):
            parsed = urlparse(url)
            bucket = parsed.netloc
            key = parsed.path.lstrip("/")
            s3 = self._get_s3_client()

            def _get() -> bytes:
                body: bytes = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
                return body

            return await asyncio.to_thread(_get)
        else:
            raise ValueError(f"Unsupported URL scheme: {url}")

    async def start(self) -> None:
        await self.publisher.start()
        await self.subscriber.start()

    async def stop(self) -> None:
        await self.subscriber.stop()
        await self.publisher.stop()

    async def _publish_result(
        self, job_id: Any, risk_score: int, tags: list[str], start_time: float
    ) -> None:
        processing_time_ms = int((time.perf_counter() - start_time) * 1000)
        if processing_time_ms > ML_SLA_MS:
            logger.warning(
                "SLA breach for job_id %s: %dms > %dms",
                job_id,
                processing_time_ms,
                ML_SLA_MS,
            )

        result_event = MlLayerResultEvent(
            job_id=job_id,
            risk_score=risk_score,
            static_tags=tags,
            processing_time_ms=processing_time_ms,
            timestamp=datetime.now(timezone.utc),
        )
        await self.publisher.publish(self.config.kafka.topic_out, result_event)
        logger.info(
            "Published results for job_id: %s (Score: %d, Time: %dms)",
            job_id,
            risk_score,
            processing_time_ms,
        )

    async def handle_event(self, event: FileRequestedEvent) -> None:
        start_time = time.perf_counter()
        job_id = event.job_id
        logger.info(f"Received analysis request for job_id: {job_id}")

        try:
            data = await self._download_file(event.s3_url)
            logger.info(f"Downloaded {len(data)} bytes for job_id: {job_id}")

            risk_score, static_tags = await self.analyzer.analyze(data)
            await self._publish_result(job_id, risk_score, static_tags, start_time)
        except Exception as e:
            logger.exception(f"Error processing job_id {job_id}: {e}")
            try:
                await self._publish_result(job_id, 0, ["analysis_error"], start_time)
            except Exception:
                logger.exception(f"Failed to publish error result for job_id {job_id}")


async def main() -> None:
    worker = MlWorker()
    logger.info("Starting ML Layer Worker...")
    try:
        await worker.start()
    except KeyboardInterrupt:
        logger.info("Shutting down ML Layer Worker...")
    finally:
        await worker.stop()


if __name__ == "__main__":
    asyncio.run(main())
