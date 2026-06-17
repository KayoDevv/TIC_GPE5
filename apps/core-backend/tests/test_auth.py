import time
from unittest.mock import AsyncMock, patch

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jose import jwt

from backend.auth import JWTPayload, verify_jwt
from backend.config import Settings

# --- Helpers : generate a real RSA key pair for tests ---


def _generate_rsa_keys() -> tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]:
    """Generate a fresh RSA-2048 key pair."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    return private_key, public_key


def _private_key_pem(private_key: rsa.RSAPrivateKey) -> str:
    """Export private key to PEM string (needed by python-jose to sign)."""
    return private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()


def _public_key_pem(public_key: rsa.RSAPublicKey) -> str:
    """Export public key to PEM string (needed by python-jose to verify)."""
    return public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()


# --- Fixtures ---

PRIVATE_KEY, PUBLIC_KEY = _generate_rsa_keys()
OTHER_PRIVATE_KEY, _ = _generate_rsa_keys()

SETTINGS = Settings(
    jwt_audience="zero-trust-api",
    jwt_algorithm="RS256",
    jwt_jwks_url="http://fake-sso/.well-known/jwks.json",
)


def _build_token(
    sub: str = "user-123",
    tenant_id: str = "tenant-abc",
    aud: str = "zero-trust-api",
    exp: float | None = None,
    private_key: rsa.RSAPrivateKey = PRIVATE_KEY,
) -> str:
    """Build a signed JWT for testing."""
    now = time.time()
    payload = {
        "sub": sub,
        "tenant_id": tenant_id,
        "aud": aud,
        "exp": exp if exp is not None else now + 3600,
        "iat": now,
    }
    return jwt.encode(payload, _private_key_pem(private_key), algorithm="RS256")


# --- Tests ---


class TestVerifyJwt:
    """Tests for JWT verification."""

    async def test_valid_token(self) -> None:
        """A correctly signed token with valid claims returns the payload."""
        token = _build_token()

        with patch("backend.auth._get_public_key", new_callable=AsyncMock) as mock_key:
            mock_key.return_value = _public_key_pem(PUBLIC_KEY)
            result = await verify_jwt(token, SETTINGS)

        assert isinstance(result, JWTPayload)
        assert result.sub == "user-123"
        assert result.tenant_id == "tenant-abc"

    async def test_expired_token(self) -> None:
        """An expired token must be rejected."""
        token = _build_token(exp=time.time() - 60)

        with patch("backend.auth._get_public_key", new_callable=AsyncMock) as mock_key:
            mock_key.return_value = _public_key_pem(PUBLIC_KEY)

            with pytest.raises(ValueError, match="INVALID_TOKEN"):
                await verify_jwt(token, SETTINGS)

    async def test_wrong_audience(self) -> None:
        """A token with a wrong audience must be rejected."""
        token = _build_token(aud="wrong-audience")

        with patch("backend.auth._get_public_key", new_callable=AsyncMock) as mock_key:
            mock_key.return_value = _public_key_pem(PUBLIC_KEY)

            with pytest.raises(ValueError, match="INVALID_TOKEN"):
                await verify_jwt(token, SETTINGS)

    async def test_invalid_signature(self) -> None:
        """A token signed with a different key must be rejected."""
        token = _build_token(private_key=OTHER_PRIVATE_KEY)

        with patch("backend.auth._get_public_key", new_callable=AsyncMock) as mock_key:
            mock_key.return_value = _public_key_pem(PUBLIC_KEY)

            with pytest.raises(ValueError, match="INVALID_TOKEN"):
                await verify_jwt(token, SETTINGS)

    async def test_missing_tenant_id(self) -> None:
        """A token without tenant_id must be rejected."""
        now = time.time()
        payload = {
            "sub": "user-123",
            "aud": "zero-trust-api",
            "exp": now + 3600,
            "iat": now,
        }
        token = jwt.encode(payload, _private_key_pem(PRIVATE_KEY), algorithm="RS256")

        with patch("backend.auth._get_public_key", new_callable=AsyncMock) as mock_key:
            mock_key.return_value = _public_key_pem(PUBLIC_KEY)

            with pytest.raises(ValueError, match="INVALID_TOKEN"):
                await verify_jwt(token, SETTINGS)

    async def test_malformed_token(self) -> None:
        """A completely malformed token string must be rejected."""
        with patch("backend.auth._get_public_key", new_callable=AsyncMock) as mock_key:
            mock_key.return_value = _public_key_pem(PUBLIC_KEY)

            with pytest.raises(ValueError, match="INVALID_TOKEN"):
                await verify_jwt("not.a.real.token", SETTINGS)
