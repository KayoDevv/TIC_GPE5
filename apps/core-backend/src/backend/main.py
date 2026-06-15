import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from zt_shared.kafka import KafkaPublisher

from backend.dependencies import get_publisher, get_s3_client, get_settings
from backend.routes.analyze import router as analyze_router
from backend.routes.health import router as health_router
from backend.routes.ws import router as ws_router
from backend.services.storage import create_s3_client
from backend.services.verdict_consumer import VerdictDispatcher

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    Manage startup and shutdown of shared resources.

    - KafkaPublisher: started on boot, stopped on shutdown
    - S3 client: created on boot, stored in app state
    """
    settings = get_settings()

    # --- Startup ---
    publisher = KafkaPublisher(
        bootstrap_servers=settings.kafka_bootstrap_servers,
        client_id=settings.kafka_client_id,
    )
    await publisher.start()

    s3_client = create_s3_client(settings)

    app.state.publisher = publisher
    app.state.s3_client = s3_client
    app.state.verdict_dispatcher = VerdictDispatcher()

    logger.info("Core Backend started.")

    yield

    # --- Shutdown ---
    await publisher.stop()
    logger.info("Core Backend stopped.")


def _get_publisher_from_state(request: Request) -> KafkaPublisher:
    """Extract KafkaPublisher from app state for dependency injection."""
    return get_publisher(request.app.state.publisher)


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
