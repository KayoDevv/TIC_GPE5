import pytest
from unittest.mock import AsyncMock

from backend.services.verdict_consumer import VerdictDispatcher


class TestVerdictDispatcher:
    """Tests for the in-memory verdict dispatcher."""

    def test_register_and_get(self) -> None:
        """A registered callback must be retrievable by job_id."""
        dispatcher = VerdictDispatcher()
        callback = AsyncMock()

        dispatcher.register("job-123", callback)

        assert dispatcher.get("job-123") is callback

    def test_get_unknown_returns_none(self) -> None:
        """Getting an unregistered job_id must return None."""
        dispatcher = VerdictDispatcher()

        assert dispatcher.get("unknown") is None

    def test_unregister(self) -> None:
        """After unregister, the job_id must no longer be found."""
        dispatcher = VerdictDispatcher()
        callback = AsyncMock()

        dispatcher.register("job-123", callback)
        dispatcher.unregister("job-123")

        assert dispatcher.get("job-123") is None

    def test_unregister_unknown_does_not_raise(self) -> None:
        """Unregistering an unknown job_id must not raise."""
        dispatcher = VerdictDispatcher()
        dispatcher.unregister("unknown")

    async def test_dispatch_calls_registered_callback(self) -> None:
        """Dispatch must call the callback for the matching job_id."""
        dispatcher = VerdictDispatcher()
        callback = AsyncMock()
        dispatcher.register("job-456", callback)

        verdict_data = {"job_id": "job-456", "final_decision": "allowed"}
        await dispatcher.dispatch("job-456", verdict_data)

        callback.assert_awaited_once_with(verdict_data)

    async def test_dispatch_unknown_does_not_raise(self) -> None:
        """Dispatching to an unknown job_id must not raise."""
        dispatcher = VerdictDispatcher()
        await dispatcher.dispatch("unknown", {"some": "data"})