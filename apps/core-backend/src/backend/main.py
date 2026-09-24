import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from typing import AsyncIterator, cast

from fastapi import FastAPI, Request
from redis.asyncio import Redis
from zt_shared.kafka import KafkaPublisher, KafkaSubscriber
from zt_shared.models.events import VerdictResultEvent

from backend.dependencies import get_s3_client, get_settings
from backend.routes.analyze import router as analyze_router
from backend.routes.health import router as health_router
from backend.routes.ws import router as ws_router
from backend.services.storage import create_s3_client
from backend.services.verdict_consumer import build_verdict_handler
from backend.services.verdict_mailbox import VerdictMailbox

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    Manage startup and shutdown of shared resources.

    - KafkaPublisher: started on boot, stopped on shutdown
    - S3 client: created on boot, stored in app state
    - Redis: job ownership and the verdict mailbox, shared by every replica
    - Verdict consumer: subscribes to verdict.result and hands each verdict to the
      mailbox, where the WebSocket waiting on that job_id picks it up (without it,
      verdicts never reach the client).
    """
    settings = get_settings()

    # --- Startup ---
    publisher = KafkaPublisher(
        bootstrap_servers=settings.kafka_bootstrap_servers,
        client_id=settings.kafka_client_id,
    )
    await publisher.start()

    s3_client = create_s3_client(settings)

    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    mailbox = VerdictMailbox(
        redis, settings.job_owner_ttl_seconds, settings.verdict_ttl_seconds
    )
    verdict_subscriber = KafkaSubscriber(
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id=settings.kafka_consumer_group_id,
        topic=settings.kafka_topic_verdict_result,
        model=VerdictResultEvent,
        handler=build_verdict_handler(mailbox),
    )
    # start() runs the consume loop, so it must live in its own task.
    verdict_task = asyncio.create_task(verdict_subscriber.start())

    app.state.publisher = publisher
    app.state.s3_client = s3_client
    app.state.verdict_mailbox = mailbox
    app.state.verdict_subscriber = verdict_subscriber

    logger.info("Core Backend started.")

    yield

    # --- Shutdown ---
    await verdict_subscriber.stop()
    verdict_task.cancel()
    with suppress(asyncio.CancelledError):
        await verdict_task
    await publisher.stop()
    await redis.aclose()
    logger.info("Core Backend stopped.")


def _get_publisher_from_state(request: Request) -> KafkaPublisher:
    """Extract KafkaPublisher from app state for dependency injection."""
    return cast(KafkaPublisher, request.app.state.publisher)


def _get_s3_client_from_state(request: Request) -> object:
    """Extract S3 client from app state for dependency injection."""
    return get_s3_client(request.app.state.s3_client)


def create_app() -> FastAPI:
    """Build and return the FastAPI application."""
    app = FastAPI(
        title="Zero-Trust Core Backend",
        description="API Gateway for the GPE-ETNA Zero-Trust platform",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.include_router(health_router, prefix="/api/v1")
    app.include_router(analyze_router, prefix="/api/v1")
    app.include_router(ws_router, prefix="/api/v1")

    return app
