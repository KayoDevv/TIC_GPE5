from unittest.mock import AsyncMock, MagicMock, patch

from httpx import ASGITransport, AsyncClient

from backend.main import create_app


class TestHealthRoute:
    """Tests for GET /api/v1/health."""

    async def test_returns_200(self) -> None:
        """Health check must return 200."""
        with (
            patch("backend.main.KafkaPublisher") as mock_pub_cls,
            patch("backend.main.create_s3_client") as mock_s3_factory,
        ):
            mock_pub_cls.return_value = AsyncMock()
            mock_s3_factory.return_value = MagicMock()
            app = create_app()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/health")

        assert response.status_code == 200

    async def test_returns_ok_status(self) -> None:
        """Health check must return {"status": "ok"}."""
        with (
            patch("backend.main.KafkaPublisher") as mock_pub_cls,
            patch("backend.main.create_s3_client") as mock_s3_factory,
        ):
            mock_pub_cls.return_value = AsyncMock()
            mock_s3_factory.return_value = MagicMock()
            app = create_app()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/health")

        assert response.json() == {"status": "ok"}

    async def test_no_auth_required(self) -> None:
        """Health check must work without Authorization header."""
        with (
            patch("backend.main.KafkaPublisher") as mock_pub_cls,
            patch("backend.main.create_s3_client") as mock_s3_factory,
        ):
            mock_pub_cls.return_value = AsyncMock()
            mock_s3_factory.return_value = MagicMock()
            app = create_app()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/health")

        assert response.status_code == 200
