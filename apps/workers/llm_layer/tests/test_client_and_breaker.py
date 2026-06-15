from __future__ import annotations

import json

import httpx
import pytest
import respx
from conftest import make_report

from llm_layer.circuit_breaker import AllEndpointsFailed, CircuitBreaker
from llm_layer.config import Endpoint, InferenceParams
from llm_layer.llm_client import LLMClient, PermanentLLMError, TransientLLMError
from llm_layer.prompt_builder import build_prompt

EP = Endpoint("https://gpu:8000", "llama", "secret", "llama3-vllm")
EP_NOKEY = Endpoint("https://gpu:8000", "llama", None, "llama3-vllm")
PROMPT = build_prompt(make_report())


def _ok(content='{"is_malicious": true, "explanation_text": "x", "confidence_score": 9}'):
    return {"choices": [{"message": {"content": content}}]}


# --------------------------- client --------------------------------------- #


@respx.mock
async def test_success_returns_content():
    respx.post(EP.chat_completions_url).mock(return_value=httpx.Response(200, json=_ok()))
    async with LLMClient(InferenceParams(), 8.0, guided_decoding=False) as c:
        out = await c.complete(EP, PROMPT)
    assert "is_malicious" in out


@respx.mock
async def test_guided_json_present_in_prod_with_auth_header():
    route = respx.post(EP.chat_completions_url).mock(return_value=httpx.Response(200, json=_ok()))
    async with LLMClient(InferenceParams(), 8.0, guided_decoding=True) as c:
        await c.complete(EP, PROMPT)
    body = json.loads(route.calls.last.request.content.decode())
    assert "guided_json" in body
    assert route.calls.last.request.headers["authorization"] == "Bearer secret"


@respx.mock
async def test_guided_json_absent_in_dev_and_no_auth_without_key():
    route = respx.post(EP_NOKEY.chat_completions_url).mock(
        return_value=httpx.Response(200, json=_ok())
    )
    async with LLMClient(InferenceParams(), 30.0, guided_decoding=False) as c:
        await c.complete(EP_NOKEY, PROMPT)
    body = json.loads(route.calls.last.request.content.decode())
    assert "guided_json" not in body
    assert "authorization" not in route.calls.last.request.headers


@respx.mock
async def test_5xx_transient():
    respx.post(EP.chat_completions_url).mock(return_value=httpx.Response(503))
    async with LLMClient(InferenceParams(), 8.0, guided_decoding=False) as c:
        with pytest.raises(TransientLLMError):
            await c.complete(EP, PROMPT)


@respx.mock
async def test_4xx_permanent():
    respx.post(EP.chat_completions_url).mock(return_value=httpx.Response(401, text="bad"))
    async with LLMClient(InferenceParams(), 8.0, guided_decoding=False) as c:
        with pytest.raises(PermanentLLMError):
            await c.complete(EP, PROMPT)


@respx.mock
async def test_timeout_transient():
    respx.post(EP.chat_completions_url).mock(side_effect=httpx.ConnectTimeout("slow"))
    async with LLMClient(InferenceParams(), 8.0, guided_decoding=False) as c:
        with pytest.raises(TransientLLMError):
            await c.complete(EP, PROMPT)


@respx.mock
async def test_malformed_envelope_permanent():
    respx.post(EP.chat_completions_url).mock(return_value=httpx.Response(200, json={"x": 1}))
    async with LLMClient(InferenceParams(), 8.0, guided_decoding=False) as c:
        with pytest.raises(PermanentLLMError):
            await c.complete(EP, PROMPT)


@respx.mock
async def test_non_string_content_permanent():
    respx.post(EP.chat_completions_url).mock(
        return_value=httpx.Response(200, json={"choices": [{"message": {"content": 5}}]})
    )
    async with LLMClient(InferenceParams(), 8.0, guided_decoding=False) as c:
        with pytest.raises(PermanentLLMError):
            await c.complete(EP, PROMPT)


async def test_client_uses_injected_client_and_does_not_close_it():
    injected = httpx.AsyncClient()
    c = LLMClient(InferenceParams(), 8.0, guided_decoding=False, client=injected)
    await c.aclose()
    assert injected.is_closed is False
    await injected.aclose()


# --------------------------- circuit breaker ------------------------------ #

PRIMARY = Endpoint("https://p", "llama", "k", "llama3-vllm")
FALLBACK = Endpoint("https://f", "mistral", "k", "mistral-vllm")


class StubClient:
    def __init__(self, behaviour):
        self.behaviour = {k: list(v) for k, v in behaviour.items()}
        self.calls = []

    async def complete(self, endpoint, prompt):
        self.calls.append(endpoint.label)
        action = self.behaviour[endpoint.label].pop(0)
        if isinstance(action, Exception):
            raise action
        return action


async def test_primary_success():
    client = StubClient({"llama3-vllm": ["{ok}"]})
    res = await CircuitBreaker(client, PRIMARY, FALLBACK).complete(PROMPT)
    assert res.model_used == "llama3-vllm" and client.calls == ["llama3-vllm"]


async def test_retry_then_success():
    client = StubClient({"llama3-vllm": [TransientLLMError("cold"), "{ok}"]})
    res = await CircuitBreaker(client, PRIMARY, FALLBACK).complete(PROMPT)
    assert client.calls == ["llama3-vllm", "llama3-vllm"]
    assert res.model_used == "llama3-vllm"


async def test_transient_exhausted_then_fallback():
    client = StubClient({
        "llama3-vllm": [TransientLLMError("a"), TransientLLMError("b")],
        "mistral-vllm": ["{ok}"],
    })
    res = await CircuitBreaker(client, PRIMARY, FALLBACK).complete(PROMPT)
    assert res.model_used == "mistral-vllm"


async def test_permanent_skips_retry_then_fallback():
    client = StubClient({
        "llama3-vllm": [PermanentLLMError("401")],
        "mistral-vllm": ["{ok}"],
    })
    res = await CircuitBreaker(client, PRIMARY, FALLBACK).complete(PROMPT)
    assert client.calls.count("llama3-vllm") == 1 and res.model_used == "mistral-vllm"


async def test_all_fail_raises():
    client = StubClient({
        "llama3-vllm": [TransientLLMError("a"), TransientLLMError("b")],
        "mistral-vllm": [TransientLLMError("c")],
    })
    with pytest.raises(AllEndpointsFailed):
        await CircuitBreaker(client, PRIMARY, FALLBACK).complete(PROMPT)
