"""Redis-backed storage for partial job state, arrival timestamps, and verdict locks."""

import json
import time
from typing import Any, Awaitable, cast

from redis.asyncio import Redis

from verdict_layer.decision_matrix import JobState

STATE_KEY_PREFIX = "verdict:state:"
ARRIVAL_KEY_PREFIX = "verdict:arrival:"
LOCK_KEY_PREFIX = "verdict:lock:"


class StateStore:
    def __init__(self, redis: Redis, ttl_seconds: int, lock_ttl_seconds: int | None = None) -> None:
        self._redis = redis
        self._ttl = ttl_seconds
        self._lock_ttl = lock_ttl_seconds if lock_ttl_seconds is not None else ttl_seconds

    @staticmethod
    def _key(job_id: str) -> str:
        return f"{STATE_KEY_PREFIX}{job_id}"

    @staticmethod
    def _arrival_key(job_id: str) -> str:
        return f"{ARRIVAL_KEY_PREFIX}{job_id}"

    @staticmethod
    def _lock_key(job_id: str) -> str:
        return f"{LOCK_KEY_PREFIX}{job_id}"

    async def _record_first_arrival(self, job_id: str) -> None:
        await self._redis.set(self._arrival_key(job_id), str(time.time()), nx=True, ex=self._ttl)

    async def _refresh_ttl(self, job_id: str) -> None:
        await self._redis.expire(self._key(job_id), self._ttl)

    async def update_ml(self, job_id: str, score: int) -> None:
        await self._record_first_arrival(job_id)
        await cast(Awaitable[Any], self._redis.hset(self._key(job_id), "ml_score", str(score)))
        await self._refresh_ttl(job_id)

    async def update_sandbox(self, job_id: str, iocs: list[dict[str, Any]], timeout: bool) -> None:
        await self._record_first_arrival(job_id)
        await cast(
            Awaitable[Any],
            self._redis.hset(
                self._key(job_id),
                mapping={
                    "sandbox_received": "1",
                    "sandbox_timeout": "1" if timeout else "0",
                    "sandbox_iocs": json.dumps(iocs),
                },
            ),
        )
        await self._refresh_ttl(job_id)

    async def update_llm(self, job_id: str, is_malicious: bool, explanation: str) -> None:
        await self._record_first_arrival(job_id)
        await cast(
            Awaitable[Any],
            self._redis.hset(
                self._key(job_id),
                mapping={
                    "llm_is_malicious": "1" if is_malicious else "0",
                    "llm_explanation": explanation,
                },
            ),
        )
        await self._refresh_ttl(job_id)

    async def mark_sandbox_timeout(self, job_id: str) -> None:
        await cast(
            Awaitable[Any],
            self._redis.hset(
                self._key(job_id),
                mapping={"sandbox_received": "1", "sandbox_timeout": "1"},
            ),
        )
        await self._refresh_ttl(job_id)

    async def get_state(self, job_id: str) -> JobState:
        raw = await cast(Awaitable[Any], self._redis.hgetall(self._key(job_id)))
        if not raw:
            return JobState()
        return JobState(
            ml_score=int(raw["ml_score"]) if "ml_score" in raw else None,
            sandbox_received=raw.get("sandbox_received") == "1",
            sandbox_timeout=raw.get("sandbox_timeout") == "1",
            sandbox_iocs=json.loads(raw["sandbox_iocs"]) if "sandbox_iocs" in raw else [],
            llm_is_malicious=(
                raw["llm_is_malicious"] == "1" if "llm_is_malicious" in raw else None
            ),
            llm_explanation=raw.get("llm_explanation"),
        )

    async def is_complete(self, job_id: str) -> bool:
        state = await self.get_state(job_id)
        return (
            state.ml_score is not None
            and state.sandbox_received
            and state.llm_is_malicious is not None
        )

    async def scan_expired(self, timeout_seconds: int) -> list[str]:
        now = time.time()
        expired: list[str] = []
        async for key in self._redis.scan_iter(match=f"{ARRIVAL_KEY_PREFIX}*"):
            job_id = key.split(ARRIVAL_KEY_PREFIX, 1)[1]
            arrival_raw = await self._redis.get(key)
            if arrival_raw is None:
                continue
            if now - float(arrival_raw) < timeout_seconds:
                continue
            state = await self.get_state(job_id)
            if not state.sandbox_received:
                expired.append(job_id)
        return expired

    async def try_acquire_verdict_lock(self, job_id: str) -> bool:
        acquired = await self._redis.set(self._lock_key(job_id), "1", nx=True, ex=self._lock_ttl)
        return acquired is True

    async def release_verdict_lock(self, job_id: str) -> None:
        await self._redis.delete(self._lock_key(job_id))

    async def clear(self, job_id: str) -> None:
        await self._redis.delete(self._key(job_id))
        await self._redis.delete(self._arrival_key(job_id))
