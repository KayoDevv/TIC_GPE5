import asyncio
import json
import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.auth import verify_jwt
from backend.dependencies import get_settings

logger = logging.getLogger(__name__)

router = APIRouter()


async def authenticate_websocket(websocket: WebSocket) -> bool:
    """
    WebSocket authentication guard.
    Validates the JWT passed as ?token= query parameter.

    Returns True if authentication succeeds.
    Closes the connection with code 4001 and returns False otherwise.
    """
    settings = get_settings()
    token = websocket.query_params.get("token")

    if not token:
        await websocket.close(code=4001, reason="Missing token")
        return False

    try:
        await verify_jwt(token, settings)
        return True
    except ValueError:
        await websocket.close(code=4001, reason="Invalid token")
        return False


def validate_job_id(job_id: str) -> bool:
    """
    Validate that job_id is a valid UUID format.

    Returns True if valid, False otherwise.
    """
    try:
        UUID(job_id)
        return True
    except ValueError:
        return False


@router.websocket("/ws/{job_id}")
async def ws_verdict(websocket: WebSocket, job_id: str) -> None:
    """
    Real-time verdict delivery channel.

    1. Authenticate via guard
    2. Validate job_id via guard
    3. Register a callback in the VerdictDispatcher
    4. Wait for verdict or timeout (130s)
    5. Send verdict and close connection
    """
    # --- 1. Auth guard ---
    if not await authenticate_websocket(websocket):
        return

    # --- 2. Job ID guard ---
    if not validate_job_id(job_id):
        await websocket.close(code=4003, reason="Invalid job_id format")
        return

    # --- 3. Accept connection and register callback ---
    settings = get_settings()
    await websocket.accept()

    verdict_event = asyncio.Event()
    verdict_data: dict[str, Any] = {}

    async def on_verdict(data: dict[str, Any]) -> None:
        nonlocal verdict_data
        verdict_data = data
        verdict_event.set()

    dispatcher = websocket.app.state.verdict_dispatcher
    dispatcher.register(job_id, on_verdict)

    try:
        # --- 4. Wait for verdict or timeout ---
        await asyncio.wait_for(
            verdict_event.wait(),
            timeout=settings.ws_verdict_timeout_seconds,
        )

        # --- 5. Send verdict and close ---
        await websocket.send_text(json.dumps(verdict_data))
        await websocket.close(code=1000)

    except asyncio.TimeoutError:
        logger.warning(f"WebSocket timeout for job {job_id}")
        await websocket.close(code=4008, reason="Verdict timeout")

    except WebSocketDisconnect:
        logger.info(f"Client disconnected for job {job_id}")

    finally:
        dispatcher.unregister(job_id)
