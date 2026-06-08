from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from backend.main import create_app, lifespan


class TestApp:
    """Tests for the FastAPI application."""

    async def test_app_starts_and_health_responds(self) -> None:
        """The app must start and /api/v1/health must return 200."""
        with (
            patch("backend.main.KafkaPublisher") as mock_publisher_cls,
            patch("backend.main.create_s3_client") as mock_s3_factory,
        ):
            mock_publisher = AsyncMock()
            mock_publisher_cls.return_value = mock_publisher
            mock_s3_factory.return_value = MagicMock()

            app = create_app()

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/api/v1/health")

            assert response.status_code == 200
            assert response.json() == {"status": "ok"}

    async def test_lifespan_starts_and_stops_publisher(self) -> None:
        """The lifespan must call start() and stop() on the KafkaPublisher."""
        with (
            patch("backend.main.KafkaPublisher") as mock_publisher_cls,
            patch("backend.main.create_s3_client") as mock_s3_factory,
        ):
            mock_publisher = AsyncMock()
            mock_publisher_cls.return_value = mock_publisher
            mock_s3_factory.return_value = MagicMock()

            app = create_app()

            async with lifespan(app):
                pass

            mock_publisher.start.assert_awaited_once()
            mock_publisher.stop.assert_awaited_once()