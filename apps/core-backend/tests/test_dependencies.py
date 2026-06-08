import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from jose import jwt

from backend.auth import JWTPayload
from backend.config import Settings
from backend.dependencies import get_settings, get_current_user


# --- Helpers : RSA key pair ---

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


def _build_token(
    sub: str = "user-123",
    tenant_id: str = "tenant-abc",
    aud: str = "zero-trust-api",
) -> str:
    now = time.time()
    payload = {
        "sub": sub,
        "tenant_id": tenant_id,
        "aud": aud,
        "exp": now + 3600,
        "iat": now,
    }
    return jwt.encode(payload, _private_key_pem(PRIVATE_KEY), algorithm="RS256")


class TestGetSettings:
    """Tests for get_settings dependency."""

    def test_returns_settings_instance(self) -> None:
        """get_settings must return a Settings instance."""
        result = get_settings()
        assert isinstance(result, Settings)


class TestGetCurrentUser:
    """Tests for get_current_user dependency."""

    async def test_valid_token_returns_payload(self) -> None:
        """A valid Bearer token must return a JWTPayload."""
        token = _build_token()

        with patch("backend.dependencies.verify_jwt", new_callable=AsyncMock) as mock_jwt:
            mock_jwt.return_value = JWTPayload(sub="user-123", tenant_id="tenant-abc")

            result = await get_current_user(
                authorization=f"Bearer {token}",
                settings=get_settings(),
            )

        assert isinstance(result, JWTPayload)
        assert result.sub == "user-123"
        assert result.tenant_id == "tenant-abc"

    async def test_missing_header_raises_401(self) -> None:
        """Missing Authorization header must raise HTTPException 401."""
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(authorization=None, settings=get_settings())

        assert exc_info.value.status_code == 401

    async def test_malformed_header_raises_401(self) -> None:
        """A header without 'Bearer ' prefix must raise HTTPException 401."""
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(
                authorization="Basic some-token",
                settings=get_settings(),
            )

        assert exc_info.value.status_code == 401

    async def test_invalid_token_raises_401(self) -> None:
        """An invalid JWT must raise HTTPException 401."""
        from fastapi import HTTPException

        with patch("backend.dependencies.verify_jwt", new_callable=AsyncMock) as mock_jwt:
            mock_jwt.side_effect = ValueError("INVALID_TOKEN")

            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(
                    authorization="Bearer bad-token",
                    settings=get_settings(),
                )

        assert exc_info.value.status_code == 401