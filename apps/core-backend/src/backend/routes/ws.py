import json
import logging
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.auth import JWTPayload, verify_jwt
from backend.dependencies import get_settings

logger = logging.getLogger(__name__)

router = APIRouter()


async def authenticate_websocket(websocket: WebSocket) -> JWTPayload | None:
    """
    WebSocket authentication guard.
    Validates the JWT passed as ?token= query parameter.

    Returns the validated payload, whose tenant_id gates access to the job.
    Closes the connection with code 4001 and returns None otherwise.
    """
    settings = get_settings()
    token = websocket.query_params.get("token")

    if not token:
        await websocket.close(code=4001, reason="Missing token")
        return None

    try:
        return await verify_jwt(token, settings)
    except ValueError:
        await websocket.close(code=4001, reason="Invalid token")
        return None


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
    3. Check the caller's tenant owns the job
    4. Wait for the verdict in the mailbox, or time out (130s)
    5. Send verdict and close connection
    """
    # --- 1. Auth guard ---
    identity = await authenticate_websocket(websocket)
    if identity is None:
        return

    # --- 2. Job ID guard ---
    if not validate_job_id(job_id):
        await websocket.close(code=4003, reason="Invalid job_id format")
        return

    # --- 3. Ownership guard ---
    # Unknown and foreign jobs get the same answer: distinguishing them would
    # turn this endpoint into an oracle for which job_ids exist.
    mailbox = websocket.app.state.verdict_mailbox
    if await mailbox.owner(job_id) != identity.tenant_id:
        await websocket.close(code=4003, reason="Unknown job_id")
        return

    # --- 4. Wait for the verdict, which may already be in the mailbox ---
    settings = get_settings()
    await websocket.accept()
    verdict = await mailbox.wait(job_id, settings.ws_verdict_timeout_seconds)

    if verdict is None:
        logger.warning(f"WebSocket timeout for job {job_id}")
        await websocket.close(code=4008, reason="Verdict timeout")
        return

    # --- 5. Send verdict and close ---
    try:
        await websocket.send_text(json.dumps(verdict))
        await websocket.close(code=1000)
    except WebSocketDisconnect:
        logger.info(f"Client disconnected for job {job_id}")
