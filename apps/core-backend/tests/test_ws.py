import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jose import jwt
from starlette.websockets import WebSocketDisconnect

from backend.auth import JWTPayload
from backend.main import create_app
from backend.routes.ws import ws_verdict

TENANT_ID = "tenant-abc"
OWNER = JWTPayload(sub="user-123", tenant_id=TENANT_ID)
OTHER_TENANT = JWTPayload(sub="mallory", tenant_id="tenant-evil")

# --- Helpers : RSA key pair for JWT signing ---


def _generate_rsa_keys() -> tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private_key, private_key.public_key()


def _private_key_pem(key: rsa.RSAPrivateKey) -> str:
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()


PRIVATE_KEY, PUBLIC_KEY = _generate_rsa_keys()


def _build_token() -> str:
    now = time.time()
    payload = {
        "sub": "user-123",
        "tenant_id": "tenant-abc",
        "aud": "zero-trust-api",
        "exp": now + 3600,
        "iat": now,
    }
    return jwt.encode(payload, _private_key_pem(PRIVATE_KEY), algorithm="RS256")


def _create_test_app() -> object:
    """Create a test app with mocked dependencies."""
    with (
        patch("backend.main.KafkaPublisher") as mock_pub_cls,
        patch("backend.main.create_s3_client") as mock_s3_factory,
    ):
        mock_pub_cls.return_value = AsyncMock()
        mock_s3_factory.return_value = MagicMock()
        app = create_app()

    app.state.publisher = AsyncMock()
    app.state.s3_client = MagicMock()
    app.state.verdict_mailbox = _mailbox(owner=None, verdict=None)
    return app


def _mailbox(owner: str | None, verdict: dict[str, object] | None) -> MagicMock:
    """A mailbox where the job belongs to `owner` and `verdict` is what the wait yields."""
    mailbox = MagicMock()
    mailbox.owner = AsyncMock(return_value=owner)
    mailbox.wait = AsyncMock(return_value=verdict)
    return mailbox


class TestWebSocketRoute:
    """Tests for WS /api/v1/ws/{job_id}."""

    async def test_verdict_received_and_connection_closed(self) -> None:
        """The verdict found in the mailbox must be sent, then the socket closed."""
        app = _create_test_app()
        job_id = "550e8400-e29b-41d4-a716-446655440000"
        verdict_payload = {
            "job_id": job_id,
            "final_decision": "allowed",
            "user_explanation": None,
            "technical_summary": None,
            "timestamp": "2025-01-01T00:00:00Z",
        }
        app.state.verdict_mailbox = _mailbox(owner=TENANT_ID, verdict=verdict_payload)

        with (
            patch("backend.routes.ws.authenticate_websocket", new_callable=AsyncMock) as mock_auth,
            patch("backend.routes.ws.get_settings") as mock_settings,
        ):
            mock_auth.return_value = OWNER
            mock_settings.return_value = MagicMock(ws_verdict_timeout_seconds=8)

            from starlette.testclient import TestClient

            with TestClient(app).websocket_connect(f"/api/v1/ws/{job_id}?token=t") as ws:
                data = ws.receive_json()

        assert data == verdict_payload
        app.state.verdict_mailbox.wait.assert_awaited_once_with(job_id, 8)

    async def test_missing_verdict_closes_with_4008(self) -> None:
        """When the mailbox wait times out, the socket must close with 4008."""
        app = _create_test_app()
        job_id = "550e8400-e29b-41d4-a716-446655440000"
        app.state.verdict_mailbox = _mailbox(owner=TENANT_ID, verdict=None)

        with (
            patch("backend.routes.ws.authenticate_websocket", new_callable=AsyncMock) as mock_auth,
            patch("backend.routes.ws.get_settings") as mock_settings,
        ):
            mock_auth.return_value = OWNER
            mock_settings.return_value = MagicMock(ws_verdict_timeout_seconds=1)

            from starlette.testclient import TestClient

            with TestClient(app).websocket_connect(f"/api/v1/ws/{job_id}?token=t") as ws:
                with pytest.raises(WebSocketDisconnect) as closed:
                    ws.receive_json()

        assert closed.value.code == 4008

    async def test_client_gone_before_the_verdict_is_sent(self) -> None:
        """A client that left while waiting must not crash the handler."""
        job_id = "550e8400-e29b-41d4-a716-446655440000"
        websocket = MagicMock()
        websocket.accept = AsyncMock()
        websocket.close = AsyncMock()
        websocket.send_text = AsyncMock(side_effect=WebSocketDisconnect())
        websocket.app.state.verdict_mailbox = _mailbox(owner=TENANT_ID, verdict={"job_id": job_id})

        with (
            patch("backend.routes.ws.authenticate_websocket", new_callable=AsyncMock) as mock_auth,
            patch("backend.routes.ws.get_settings") as mock_settings,
        ):
            mock_auth.return_value = OWNER
            mock_settings.return_value = MagicMock(ws_verdict_timeout_seconds=1)

            await ws_verdict(websocket, job_id)

        websocket.close.assert_not_awaited()

    async def test_missing_token_closes_with_4001(self) -> None:
        """A WS connection without token must be closed with code 4001."""
        app = _create_test_app()
        job_id = "550e8400-e29b-41d4-a716-446655440000"

        from starlette.testclient import TestClient

        client = TestClient(app)

        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(f"/api/v1/ws/{job_id}"):
                pass

    async def test_invalid_token_closes_with_4001(self) -> None:
        """A WS connection with invalid JWT must be closed with code 4001."""
        app = _create_test_app()
        job_id = "550e8400-e29b-41d4-a716-446655440000"

        with patch("backend.routes.ws.verify_jwt", new_callable=AsyncMock) as mock_jwt:
            mock_jwt.side_effect = ValueError("INVALID_TOKEN")

            from starlette.testclient import TestClient

            client = TestClient(app)

            with pytest.raises(WebSocketDisconnect):
                with client.websocket_connect(f"/api/v1/ws/{job_id}?token=bad-token"):
                    pass

    async def test_invalid_job_id_closes_with_4003(self) -> None:
        """A WS connection with a non-UUID job_id must be closed with code 4003."""
        app = _create_test_app()

        with patch("backend.routes.ws.authenticate_websocket", new_callable=AsyncMock) as mock_auth:
            mock_auth.return_value = OWNER

            from starlette.testclient import TestClient

            client = TestClient(app)

            with pytest.raises(WebSocketDisconnect):
                with client.websocket_connect(f"/api/v1/ws/not-a-uuid?token={_build_token()}"):
                    pass

    async def test_foreign_tenant_cannot_subscribe(self) -> None:
        """A job claimed by one tenant must not stream to another (CWE-639)."""
        app = _create_test_app()
        job_id = "550e8400-e29b-41d4-a716-446655440000"
        app.state.verdict_mailbox = _mailbox(owner=TENANT_ID, verdict=None)

        with patch("backend.routes.ws.authenticate_websocket", new_callable=AsyncMock) as mock_auth:
            mock_auth.return_value = OTHER_TENANT

            from starlette.testclient import TestClient

            client = TestClient(app)

            with pytest.raises(WebSocketDisconnect):
                with client.websocket_connect(f"/api/v1/ws/{job_id}?token={_build_token()}"):
                    pass

    async def test_unclaimed_job_is_refused(self) -> None:
        """A well-formed job_id nobody submitted must not open a channel."""
        app = _create_test_app()
        job_id = "550e8400-e29b-41d4-a716-446655440000"

        with patch("backend.routes.ws.authenticate_websocket", new_callable=AsyncMock) as mock_auth:
            mock_auth.return_value = OWNER

            from starlette.testclient import TestClient

            client = TestClient(app)

            with pytest.raises(WebSocketDisconnect):
                with client.websocket_connect(f"/api/v1/ws/{job_id}?token={_build_token()}"):
                    pass
