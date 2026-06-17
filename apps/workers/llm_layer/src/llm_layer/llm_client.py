"""Async LLM client -- one OpenAI-compatible code path for dev and prod.

Both vLLM (production) and the HuggingFace router (development) expose
``POST /v1/chat/completions`` with the OpenAI schema, so a single ``httpx``
client serves both. REST is chosen over gRPC deliberately: identical client code
across profiles, no separate protobuf contract, no measurable latency cost at
this volume (the LLM is invoked only on uncertain samples).
"""

from __future__ import annotations

from typing import Any

import httpx

from llm_layer.config import Endpoint, InferenceParams
from llm_layer.models import ModelDecision
from llm_layer.prompt_builder import Prompt


class TransientLLMError(RuntimeError):
    """Retriable: timeout, connection error, or HTTP 5xx."""


class PermanentLLMError(RuntimeError):
    """Non-retriable: HTTP 4xx or malformed completion envelope."""


class LLMClient:
    """Thin async wrapper around the chat-completions endpoint."""

    def __init__(
        self,
        inference: InferenceParams,
        timeout_s: float,
        guided_decoding: bool,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._inference = inference
        self._timeout_s = timeout_s
        self._guided = guided_decoding
        self._client = client or httpx.AsyncClient(timeout=timeout_s)
        self._owns_client = client is None

    async def __aenter__(self) -> "LLMClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    def _body(self, endpoint: Endpoint, prompt: Prompt) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": endpoint.model,
            "messages": prompt.as_messages(),
            "temperature": self._inference.temperature,
            "top_p": self._inference.top_p,
            "max_tokens": self._inference.max_tokens,
            "stream": False,
        }
        if self._guided:
            body["guided_json"] = ModelDecision.guided_json_schema()
            body["guided_decoding_backend"] = "outlines"
        return body

    async def complete(self, endpoint: Endpoint, prompt: Prompt) -> str:
        """Call ``endpoint`` and return the assistant ``content`` string."""
        headers = {"Content-Type": "application/json"}
        if endpoint.api_key:
            headers["Authorization"] = f"Bearer {endpoint.api_key}"

        try:
            resp = await self._client.post(
                endpoint.chat_completions_url,
                json=self._body(endpoint, prompt),
                headers=headers,
                timeout=self._timeout_s,
            )
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise TransientLLMError(f"{endpoint.label}: transport: {exc}") from exc

        if resp.status_code >= 500:
            raise TransientLLMError(f"{endpoint.label}: HTTP {resp.status_code}")
        if resp.status_code >= 400:
            raise PermanentLLMError(
                f"{endpoint.label}: HTTP {resp.status_code}: {resp.text[:200]}"
            )

        try:
            content = resp.json()["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise PermanentLLMError(
                f"{endpoint.label}: malformed completion envelope: {exc}"
            ) from exc

        if not isinstance(content, str):
            raise PermanentLLMError(f"{endpoint.label}: non-string content")
        return content
