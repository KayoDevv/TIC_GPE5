import asyncio

import fakeredis

from backend.services.verdict_mailbox import OWNER_KEY, VERDICT_KEY, VerdictMailbox

JOB_ID = "550e8400-e29b-41d4-a716-446655440000"
VERDICT = {"job_id": JOB_ID, "final_decision": "blocked"}


def _mailbox() -> tuple[VerdictMailbox, fakeredis.FakeAsyncRedis]:
    redis = fakeredis.FakeAsyncRedis(decode_responses=True)
    return VerdictMailbox(redis, owner_ttl_seconds=900, verdict_ttl_seconds=300), redis


class TestOwnership:
    async def test_claimed_job_reports_its_tenant(self) -> None:
        mailbox, redis = _mailbox()

        await mailbox.claim(JOB_ID, "tenant-abc")

        assert await mailbox.owner(JOB_ID) == "tenant-abc"
        assert 0 < await redis.ttl(OWNER_KEY.format(job_id=JOB_ID)) <= 900

    async def test_unknown_job_has_no_owner(self) -> None:
        mailbox, _ = _mailbox()

        assert await mailbox.owner(JOB_ID) is None


class TestVerdictHandOff:
    async def test_verdict_delivered_before_the_wait_is_returned(self) -> None:
        """The race the in-memory dispatcher lost: verdict first, WebSocket second."""
        mailbox, redis = _mailbox()

        await mailbox.deliver(JOB_ID, VERDICT)

        assert await mailbox.wait(JOB_ID, timeout_seconds=1) == VERDICT
        assert 0 < await redis.ttl(VERDICT_KEY.format(job_id=JOB_ID)) <= 300

    async def test_verdict_delivered_during_the_wait_wakes_it(self) -> None:
        mailbox, _ = _mailbox()

        waiting = asyncio.create_task(mailbox.wait(JOB_ID, timeout_seconds=5))
        await asyncio.sleep(0.05)
        await mailbox.deliver(JOB_ID, VERDICT)

        assert await asyncio.wait_for(waiting, timeout=5) == VERDICT

    async def test_another_jobs_verdict_does_not_wake_the_wait(self) -> None:
        mailbox, _ = _mailbox()

        waiting = asyncio.create_task(mailbox.wait(JOB_ID, timeout_seconds=0.3))
        await asyncio.sleep(0.05)
        await mailbox.deliver("other-job", VERDICT)

        assert await waiting is None

    async def test_wait_times_out_without_a_verdict(self) -> None:
        mailbox, _ = _mailbox()

        assert await mailbox.wait(JOB_ID, timeout_seconds=0.1) is None
