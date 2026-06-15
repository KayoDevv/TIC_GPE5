"""Circuit breaker for the inference fallback strategy (LLM.md).

1. primary (Llama 3) with one retry on a transient error;
2. fallback (Mistral 7B);
3. both fail -> :class:`AllEndpointsFailed`; the pipeline emits a degraded result
   so the user is never blocked.

A permanent error (4xx) skips the endpoint's remaining retries -- retrying a bad
request or auth failure only burns the SLA budget.
"""

from __future__ import annotations

from dataclasses import dataclass

from llm_layer.config import Endpoint
from llm_layer.llm_client import LLMClient, PermanentLLMError, TransientLLMError
from llm_layer.prompt_builder import Prompt


class AllEndpointsFailed(RuntimeError):
    def __init__(self, attempts: list[str]) -> None:
        self.attempts = attempts
        super().__init__("all LLM endpoints failed: " + " | ".join(attempts))


@dataclass(frozen=True)
class Completion:
    content: str
    model_used: str


class CircuitBreaker:
    def __init__(
        self,
        client: LLMClient,
        primary: Endpoint,
        fallback: Endpoint,
        primary_retries: int = 1,
    ) -> None:
        self._client = client
        self._primary = primary
        self._fallback = fallback
        self._primary_retries = primary_retries

    async def complete(self, prompt: Prompt) -> Completion:
        attempts: list[str] = []

        for attempt in range(self._primary_retries + 1):
            try:
                content = await self._client.complete(self._primary, prompt)
                return Completion(content, self._primary.label)
            except TransientLLMError as exc:
                attempts.append(f"{self._primary.label}#try{attempt + 1}: {exc}")
            except PermanentLLMError as exc:
                attempts.append(f"{self._primary.label}: {exc}")
                break

        try:
            content = await self._client.complete(self._fallback, prompt)
            return Completion(content, self._fallback.label)
        except (TransientLLMError, PermanentLLMError) as exc:
            attempts.append(f"{self._fallback.label}: {exc}")

        raise AllEndpointsFailed(attempts)
