import logging
from dataclasses import dataclass

from jose import JWTError, jwt

from backend.config import Settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class JWTPayload:
    """Validated JWT payload exposed to the rest of the application."""

    sub: str
    tenant_id: str


async def _get_public_key(settings: Settings) -> str:
    """
    Fetch the RSA public key from the SSO JWKS endpoint.

    In production this would call settings.jwt_jwks_url with httpx,
    parse the JWKS JSON, and extract the RSA public key.
    For now this is a placeholder — it will be fully implemented
    when the SSO provider is integrated.
    """
    raise NotImplementedError("JWKS fetching not yet implemented")


async def verify_jwt(token: str, settings: Settings) -> JWTPayload:
    """
    Verify a JWT token and return the validated payload.

    Checks:
    - RS256 signature against the SSO public key
    - exp claim (expiration)
    - aud claim (audience)
    - Presence of sub and tenant_id claims

    Raises:
        ValueError: with message "INVALID_TOKEN" if any check fails.
    """
    public_key = await _get_public_key(settings)

    try:
        payload = jwt.decode(
            token,
            public_key,
            algorithms=[settings.jwt_algorithm],
            audience=settings.jwt_audience,
        )
    except JWTError as e:
        logger.warning(f"JWT verification failed: {e}")
        raise ValueError("INVALID_TOKEN") from e

    sub = payload.get("sub")
    tenant_id = payload.get("tenant_id")

    if not sub or not tenant_id:
        logger.warning("JWT missing required claims (sub or tenant_id)")
        raise ValueError("INVALID_TOKEN")

    return JWTPayload(sub=sub, tenant_id=tenant_id)
