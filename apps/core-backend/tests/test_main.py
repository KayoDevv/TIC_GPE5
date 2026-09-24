from unittest.mock import AsyncMock, MagicMock, patch

from httpx import ASGITransport, AsyncClient

from backend.main import create_app, lifespan


class TestApp:
    """Tests for the FastAPI application."""

    async def test_app_starts_and_health_responds(self) -> None:
        """The app must start and /api/v1/health must return 200."""
        with (
            patch("backend.main.KafkaPublisher") as mock_publisher_cls,
            patch("backend.main.KafkaSubscriber") as mock_subscriber_cls,
            patch("backend.main.create_s3_client") as mock_s3_factory,
        ):
            mock_publisher = AsyncMock()
            mock_publisher_cls.return_value = mock_publisher
            mock_subscriber_cls.return_value = AsyncMock()
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
            patch("backend.main.KafkaSubscriber") as mock_subscriber_cls,
            patch("backend.main.create_s3_client") as mock_s3_factory,
            patch("backend.main.Redis") as mock_redis_cls,
        ):
            mock_publisher = AsyncMock()
            mock_publisher_cls.return_value = mock_publisher
            mock_subscriber_cls.return_value = AsyncMock()
            mock_s3_factory.return_value = MagicMock()

            app = create_app()

            mock_redis = AsyncMock()
            mock_redis_cls.from_url.return_value = mock_redis

            async with lifespan(app):
                assert app.state.verdict_mailbox is not None

            mock_publisher.start.assert_awaited_once()
            mock_publisher.stop.assert_awaited_once()
            mock_redis.aclose.assert_awaited_once()

    async def test_lifespan_starts_and_stops_verdict_consumer(self) -> None:
        """The lifespan must run the verdict.result consumer and stop it on exit."""
        with (
            patch("backend.main.KafkaPublisher") as mock_publisher_cls,
            patch("backend.main.KafkaSubscriber") as mock_subscriber_cls,
            patch("backend.main.create_s3_client") as mock_s3_factory,
            patch("backend.main.Redis") as mock_redis_cls,
        ):
            mock_publisher_cls.return_value = AsyncMock()
            mock_subscriber = AsyncMock()
            mock_subscriber_cls.return_value = mock_subscriber
            mock_s3_factory.return_value = MagicMock()
            mock_redis_cls.from_url.return_value = AsyncMock()

            app = create_app()

            async with lifespan(app):
                assert app.state.verdict_subscriber is mock_subscriber

            mock_subscriber.start.assert_called_once()
            mock_subscriber.stop.assert_awaited_once()
