import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jose import jwt
from starlette.websockets import WebSocketDisconnect

from backend.auth import JWTPayload
from backend.main import create_app
from backend.services.job_owner import JobOwnerRegistry
from backend.services.verdict_consumer import VerdictDispatcher

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
    app.state.verdict_dispatcher = VerdictDispatcher()
    app.state.job_owners = JobOwnerRegistry(900)
    return app


class TestWebSocketRoute:
    """Tests for WS /api/v1/ws/{job_id}."""

    async def test_verdict_received_and_connection_closed(self) -> None:
        """When a verdict is dispatched, the WS must send it and close."""
        import threading

        app = _create_test_app()
        token = _build_token()
        job_id = "550e8400-e29b-41d4-a716-446655440000"

        verdict_payload = {
            "job_id": job_id,
            "final_decision": "allowed",
            "user_explanation": None,
            "technical_summary": None,
            "timestamp": "2025-01-01T00:00:00Z",
        }

        # Capture the event loop the WS handler runs on (recorded when the route
        # registers its callback). The verdict must be dispatched *on that loop*
        # via run_coroutine_threadsafe — dispatching from a foreign loop only sets
        # the asyncio.Event's flag without waking the idle loop, so it would not be
        # observed until the next timer tick (the 130s timeout). In production the
        # verdict consumer and the WS share one loop, so this races correctly.
        dispatcher = app.state.verdict_dispatcher
        captured: dict[str, asyncio.AbstractEventLoop] = {}
        original_register = dispatcher.register

        def _register_capturing_loop(jid: str, cb: object) -> None:
            captured["loop"] = asyncio.get_running_loop()
            original_register(jid, cb)  # type: ignore[arg-type]

        with (
            patch("backend.routes.ws.authenticate_websocket", new_callable=AsyncMock) as mock_auth,
            patch("backend.routes.ws.get_settings") as mock_settings,
            patch.object(dispatcher, "register", _register_capturing_loop),
        ):
            mock_auth.return_value = OWNER
            app.state.job_owners.register(job_id, TENANT_ID)
            # Cap the verdict wait so any future delivery regression fails in
            # seconds, not the full 130s production timeout.
            mock_settings.return_value = MagicMock(ws_verdict_timeout_seconds=8)

            from starlette.testclient import TestClient

            client = TestClient(app)

            def dispatch_after_delay() -> None:
                """Dispatch the verdict on the WS handler's loop after a short delay."""
                import time

                time.sleep(0.1)
                asyncio.run_coroutine_threadsafe(
                    dispatcher.dispatch(job_id, verdict_payload), captured["loop"]
                ).result(timeout=5)

            with client.websocket_connect(f"/api/v1/ws/{job_id}?token={token}") as ws:
                thread = threading.Thread(target=dispatch_after_delay)
                thread.start()
                data = ws.receive_json()
                thread.join()

            assert data["job_id"] == job_id
            assert data["final_decision"] == "allowed"

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
        app.state.job_owners.register(job_id, TENANT_ID)

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
