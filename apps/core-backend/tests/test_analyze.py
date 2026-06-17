from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from backend.auth import JWTPayload
from backend.dependencies import get_current_user
from backend.main import create_app

# --- Helpers ---

VALID_FORM_DATA = {
    "sender": "alice@example.com",
    "subject": "Facture Janvier",
    "body_text": "Veuillez trouver ci-joint la facture.",
}

SMALL_FILE = ("file", ("facture.pdf", b"fake pdf content", "application/pdf"))

MOCK_USER = JWTPayload(sub="user-123", tenant_id="tenant-abc")


def _create_test_app(authenticated: bool = True):
    """Create a test app with mocked dependencies."""
    with (
        patch("backend.main.KafkaPublisher") as mock_pub_cls,
        patch("backend.main.create_s3_client") as mock_s3_factory,
    ):
        mock_publisher = AsyncMock()
        mock_pub_cls.return_value = mock_publisher
        mock_s3_factory.return_value = MagicMock()
        app = create_app()

    app.state.publisher = mock_publisher
    app.state.s3_client = MagicMock()

    if authenticated:
        app.dependency_overrides[get_current_user] = lambda: MOCK_USER

    return app, mock_publisher


class TestAnalyzeRoute:
    """Tests for POST /api/v1/analyze."""

    async def test_success_returns_202(self) -> None:
        """Valid request must return 202 with a job_id."""
        app, mock_publisher = _create_test_app()

        with patch("backend.routes.analyze.upload_file", new_callable=AsyncMock) as mock_upload:
            mock_upload.return_value = "s3://zero-trust-files/some-id/facture.pdf"

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/api/v1/analyze",
                    data=VALID_FORM_DATA,
                    files=[SMALL_FILE],
                    headers={"Authorization": "Bearer fake-token"},
                )

        assert response.status_code == 202
        body = response.json()
        assert "job_id" in body
        assert "message" in body
        mock_publisher.publish.assert_awaited_once()

    async def test_file_too_large_returns_400(self) -> None:
        """A file exceeding 35 MB must be rejected with 400."""
        app, _ = _create_test_app()

        big_file = ("file", ("big.exe", b"x" * (35 * 1024 * 1024 + 1), "application/octet-stream"))

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/analyze",
                data=VALID_FORM_DATA,
                files=[big_file],
                headers={"Authorization": "Bearer fake-token"},
            )

        assert response.status_code == 400
        assert response.json()["detail"]["error"] == "FILE_TOO_LARGE"

    async def test_missing_fields_returns_400(self) -> None:
        """Missing form fields must return 400."""
        app, _ = _create_test_app()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/analyze",
                data={"sender": "alice@example.com"},
                files=[SMALL_FILE],
                headers={"Authorization": "Bearer fake-token"},
            )

        assert response.status_code == 400
        assert response.json()["detail"]["error"] == "MISSING_FIELDS"

    async def test_missing_auth_returns_401(self) -> None:
        """A request without Authorization header must return 401."""
        app, _ = _create_test_app(authenticated=False)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/analyze",
                data=VALID_FORM_DATA,
                files=[SMALL_FILE],
            )

        assert response.status_code == 401

    async def test_invalid_jwt_returns_401(self) -> None:
        """An invalid JWT must return 401."""
        app, _ = _create_test_app(authenticated=False)

        async def _raise_401():
            raise HTTPException(
                status_code=401,
                detail={"error": "INVALID_TOKEN", "message": "Invalid token"},
            )

        app.dependency_overrides[get_current_user] = _raise_401

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/analyze",
                data=VALID_FORM_DATA,
                files=[SMALL_FILE],
                headers={"Authorization": "Bearer bad-token"},
            )

        assert response.status_code == 401

    async def test_s3_failure_returns_500(self) -> None:
        """If S3 upload fails, the route must return 500."""
        app, _ = _create_test_app()

        with patch("backend.routes.analyze.upload_file", new_callable=AsyncMock) as mock_upload:
            mock_upload.side_effect = Exception("S3 is down")

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/api/v1/analyze",
                    data=VALID_FORM_DATA,
                    files=[SMALL_FILE],
                    headers={"Authorization": "Bearer fake-token"},
                )

        assert response.status_code == 500
        assert response.json()["error"] == "UPLOAD_FAILED"

    async def test_kafka_failure_returns_500(self) -> None:
        """If Kafka publish fails, the route must return 500."""
        app, mock_publisher = _create_test_app()
        mock_publisher.publish.side_effect = Exception("Kafka is down")

        with patch("backend.routes.analyze.upload_file", new_callable=AsyncMock) as mock_upload:
            mock_upload.return_value = "s3://zero-trust-files/some-id/facture.pdf"

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/api/v1/analyze",
                    data=VALID_FORM_DATA,
                    files=[SMALL_FILE],
                    headers={"Authorization": "Bearer fake-token"},
                )

        assert response.status_code == 500
        assert response.json()["error"] == "KAFKA_PUBLISH_FAILED"
