import json
import logging
import time
from typing import Any, cast

from redis.asyncio import Redis

logger = logging.getLogger(__name__)

OWNER_KEY = "core-backend:job:{job_id}:owner"
VERDICT_KEY = "core-backend:job:{job_id}:verdict"


class VerdictMailbox:
    """
    Redis hand-off between the verdict consumer and the verdict WebSocket.

    A verdict is stored under its job_id and announced on a channel of the same
    name, so it reaches the client whether the WebSocket connected before or after
    it arrived, and whichever backend replica consumed it. The tenant owning each
    job is kept next to it for the same reasons. Both keys expire: nothing outlives
    the analysis window.
    """

    def __init__(self, redis: Redis, owner_ttl_seconds: int, verdict_ttl_seconds: int) -> None:
        self._redis = redis
        self._owner_ttl = owner_ttl_seconds
        self._verdict_ttl = verdict_ttl_seconds

    async def claim(self, job_id: str, tenant_id: str) -> None:
        """Record the tenant owning a job."""
        await self._redis.set(OWNER_KEY.format(job_id=job_id), tenant_id, ex=self._owner_ttl)

    async def owner(self, job_id: str) -> str | None:
        """Return the owning tenant, or None when the job is unknown or expired."""
        return cast(str | None, await self._redis.get(OWNER_KEY.format(job_id=job_id)))

    async def deliver(self, job_id: str, verdict: dict[str, Any]) -> None:
        """Store a verdict and wake any WebSocket waiting on it."""
        key = VERDICT_KEY.format(job_id=job_id)
        payload = json.dumps(verdict)
        await self._redis.set(key, payload, ex=self._verdict_ttl)
        await self._redis.publish(key, payload)
        logger.info(f"Verdict stored for job {job_id}")

    async def wait(self, job_id: str, timeout_seconds: float) -> dict[str, Any] | None:
        """Return the job's verdict as soon as it exists, or None after the timeout."""
        key = VERDICT_KEY.format(job_id=job_id)
        async with self._redis.pubsub() as pubsub:
            await pubsub.subscribe(key)
            # Read only once subscribed: a verdict landing in between is caught by one or
            # the other, never lost between the two.
            stored = await self._redis.get(key)
            if stored is not None:
                return cast(dict[str, Any], json.loads(stored))

            deadline = time.monotonic() + timeout_seconds
            while (remaining := deadline - time.monotonic()) > 0:
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=remaining
                )
                if message is not None:
                    return cast(dict[str, Any], json.loads(message["data"]))

        return None
