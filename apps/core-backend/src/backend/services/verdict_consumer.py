from typing import Awaitable, Callable

from zt_shared.models.events import VerdictResultEvent

from backend.services.verdict_mailbox import VerdictMailbox


def build_verdict_handler(
    mailbox: VerdictMailbox,
) -> Callable[[VerdictResultEvent], Awaitable[None]]:
    """Return a Kafka handler that hands verdict.result events to the mailbox.

    Wired to a ``KafkaSubscriber`` in the app lifespan so a verdict emitted by the
    Verdict Layer reaches the WebSocket waiting on its job_id, even one that has not
    connected yet.
    """

    async def handle(event: VerdictResultEvent) -> None:
        await mailbox.deliver(str(event.job_id), event.model_dump(mode="json"))

    return handle
