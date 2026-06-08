import asyncio
import hashlib
from functools import partial


async def compute_sha256(data: bytes) -> str:
    """
    Compute the SHA-256 hex digest of raw bytes.

    Runs in a thread executor to avoid blocking the async event loop
    on large payloads (up to 35 MB).
    """
    loop = asyncio.get_running_loop()
    digest: str = await loop.run_in_executor(None, partial(_sha256_sync, data))
    return digest


def _sha256_sync(data: bytes) -> str:
    """Synchronous SHA-256 computation."""
    return hashlib.sha256(data).hexdigest()