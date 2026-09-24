from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

from zt_shared.models.events import VerdictResultEvent

from backend.services.verdict_consumer import build_verdict_handler


class TestBuildVerdictHandler:
    """The Kafka handler must hand verdict events to the mailbox."""

    async def test_handler_delivers_event_as_dict(self) -> None:
        mailbox = AsyncMock()
        job_id = uuid4()

        handler = build_verdict_handler(mailbox)
        event = VerdictResultEvent(
            job_id=job_id,
            final_decision="blocked",
            timestamp=datetime.now(timezone.utc),
        )
        await handler(event)

        mailbox.deliver.assert_awaited_once()
        delivered_job_id, payload = mailbox.deliver.await_args.args
        assert delivered_job_id == str(job_id)
        assert payload["job_id"] == str(job_id)
        assert payload["final_decision"] == "blocked"
