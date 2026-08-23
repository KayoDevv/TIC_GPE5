import logging
import time

logger = logging.getLogger(__name__)


class JobOwnerRegistry:
    """
    In-memory registry mapping a job_id to the tenant that submitted it.

    The verdict WebSocket is the consumer: it refuses to stream a verdict to a
    tenant that did not submit the job. Entries expire so a caller cannot grow
    the registry without bound by submitting jobs it never listens to.
    """

    def __init__(self, ttl_seconds: float) -> None:
        self._owners: dict[str, tuple[str, float]] = {}
        self._ttl = ttl_seconds

    def register(self, job_id: str, tenant_id: str) -> None:
        """Record the tenant owning a job."""
        self._purge()
        self._owners[job_id] = (tenant_id, time.monotonic() + self._ttl)
        logger.debug(f"Registered owner for job {job_id}")

    def owner(self, job_id: str) -> str | None:
        """Return the owning tenant, or None when the job is unknown or expired."""
        entry = self._owners.get(job_id)
        if entry is None:
            return None

        tenant_id, expires_at = entry
        if time.monotonic() >= expires_at:
            del self._owners[job_id]
            return None

        return tenant_id

    def _purge(self) -> None:
        """Drop expired entries."""
        now = time.monotonic()
        for job_id in [j for j, (_, expires_at) in self._owners.items() if now >= expires_at]:
            del self._owners[job_id]
