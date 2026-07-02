import logging
from typing import Any, Awaitable, Callable

from zt_shared.models.events import VerdictResultEvent

logger = logging.getLogger(__name__)

# Type alias for the callback that sends the verdict to the WebSocket
VerdictCallback = Callable[[dict[str, Any]], Awaitable[None]]


class VerdictDispatcher:
    """
    In-memory registry that maps job_ids to WebSocket callbacks.

    When the Kafka consumer receives a verdict, it calls dispatch()
    which forwards the payload to the matching WebSocket connection.
    """

    def __init__(self) -> None:
        self._callbacks: dict[str, VerdictCallback] = {}

    def register(self, job_id: str, callback: VerdictCallback) -> None:
        """Register a WebSocket callback for a given job_id."""
        self._callbacks[job_id] = callback
        logger.debug(f"Registered callback for job {job_id}")

    def unregister(self, job_id: str) -> None:
        """Remove the callback for a given job_id."""
        self._callbacks.pop(job_id, None)
        logger.debug(f"Unregistered callback for job {job_id}")

    def get(self, job_id: str) -> VerdictCallback | None:
        """Get the callback for a given job_id, or None."""
        return self._callbacks.get(job_id)

    async def dispatch(self, job_id: str, verdict_data: dict[str, Any]) -> None:
        """
        Forward a verdict payload to the registered WebSocket callback.

        If no callback is registered for the job_id, the verdict is silently dropped.
        """
        callback = self._callbacks.get(job_id)
        if callback is None:
            logger.warning(f"No WebSocket registered for job {job_id}, verdict dropped")
            return

        await callback(verdict_data)
        logger.info(f"Verdict dispatched for job {job_id}")


def build_verdict_handler(
    dispatcher: VerdictDispatcher,
) -> Callable[[VerdictResultEvent], Awaitable[None]]:
    """Return a Kafka handler that forwards verdict.result events to the dispatcher.

    Wired to a ``KafkaSubscriber`` in the app lifespan so a verdict emitted by the
    Verdict Layer reaches the WebSocket that is waiting on its job_id.
    """

    async def handle(event: VerdictResultEvent) -> None:
        await dispatcher.dispatch(str(event.job_id), event.model_dump(mode="json"))

    return handle
