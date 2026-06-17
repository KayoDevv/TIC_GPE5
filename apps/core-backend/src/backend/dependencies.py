from functools import lru_cache
from typing import Any

from fastapi import Depends, Header, HTTPException, Request

from backend.auth import JWTPayload, verify_jwt
from backend.config import Settings


@lru_cache
def get_settings() -> Settings:
    """Return the application settings (cached after first call)."""
    return Settings()


async def get_current_user(
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),  # noqa: B008
) -> JWTPayload:
    """
    FastAPI dependency that extracts and verifies the JWT from
    the Authorization header. Reusable across all protected routes.

    Raises HTTPException 401 if the token is missing, malformed, or invalid.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail={"error": "INVALID_TOKEN", "message": "Missing or malformed Authorization header."},  # noqa: E501
        )

    token = authorization.removeprefix("Bearer ")

    try:
        return await verify_jwt(token, settings)
    except ValueError as err:
        raise HTTPException(
            status_code=401,
            detail={"error": "INVALID_TOKEN", "message": "Invalid or expired JWT token."},
        ) from err


def get_publisher(request: Request) -> Any:
    """Extract KafkaPublisher from app state."""
    return request.app.state.publisher


def get_s3_client(request: Request) -> Any:
    """Extract S3 client from app state."""
    return request.app.state.s3_client
