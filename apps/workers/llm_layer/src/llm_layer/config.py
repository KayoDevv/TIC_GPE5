"""Runtime configuration for the LLM Layer worker.

The single environment variable ``VLLM_URL`` selects the runtime profile:

* unset -> development (HuggingFace OpenAI-compatible router, guided decoding not
  guaranteed -> the lenient response parser is armed, 30 s timeout for cold start).
* set   -> production (on-premise vLLM, native guided decoding enforced, 8 s
  timeout, no sample data leaves the cluster).

The worker code is identical across both profiles; only this object changes.
Nothing else in the package reads ``os.environ`` directly.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum


class Profile(str, Enum):
    DEVELOPMENT = "development"
    PRODUCTION = "production"


@dataclass(frozen=True)
class InferenceParams:
    temperature: float = 0.2
    top_p: float = 0.9
    max_tokens: int = 512

    def __post_init__(self) -> None:
        if not 0.1 <= self.temperature <= 0.3:
            raise ValueError(
                f"temperature {self.temperature} violates the project constraint "
                "0.1-0.3 (no hallucinations on security decisions)"
            )


@dataclass(frozen=True)
class Endpoint:
    base_url: str
    model: str
    api_key: str | None
    label: str

    @property
    def chat_completions_url(self) -> str:
        return self.base_url.rstrip("/") + "/v1/chat/completions"


@dataclass(frozen=True)
class Settings:
    profile: Profile
    inference: InferenceParams
    primary: Endpoint
    fallback: Endpoint
    request_timeout_s: float
    guided_decoding: bool
    kafka_bootstrap: str
    topic_in: str
    topic_out: str
    consumer_group: str

    @property
    def is_production(self) -> bool:
        return self.profile is Profile.PRODUCTION


def _get(env: dict[str, str], key: str, default: str | None = None) -> str | None:
    value = env.get(key)
    return value if value else default


# Like _get but with a mandatory default, so the return is always str (mypy-strict).
def _req(env: dict[str, str], key: str, default: str) -> str:
    value = env.get(key)
    return value if value else default


def load_settings(env: dict[str, str] | None = None) -> Settings:
    env = dict(os.environ) if env is None else env

    inference = InferenceParams(
        temperature=float(_req(env, "LLM_TEMPERATURE", "0.2")),
        top_p=float(_req(env, "LLM_TOP_P", "0.9")),
        max_tokens=int(_req(env, "LLM_MAX_TOKENS", "512")),
    )
    kafka_bootstrap = _req(env, "KAFKA_BOOTSTRAP", "kafka:9092")
    topic_in = _req(env, "TOPIC_IN", "sandbox_layer.result")
    topic_out = _req(env, "TOPIC_OUT", "llm_layer.result")
    consumer_group = _req(env, "KAFKA_GROUP", "llm-layer")
    default_model = "meta-llama/Llama-3.3-70B-Instruct"
    fallback_model = "mistralai/Mistral-7B-Instruct-v0.3"

    vllm_url = _get(env, "VLLM_URL")
    if vllm_url:
        api_key = _get(env, "VLLM_API_KEY")
        return Settings(
            profile=Profile.PRODUCTION,
            inference=inference,
            primary=Endpoint(
                base_url=vllm_url,
                model=_req(env, "LLM_MODEL_PRIMARY", default_model),
                api_key=api_key,
                label="llama3-vllm",
            ),
            fallback=Endpoint(
                base_url=_req(env, "VLLM_URL_FALLBACK", vllm_url),
                model=_req(env, "LLM_MODEL_FALLBACK", fallback_model),
                api_key=_get(env, "VLLM_API_KEY_FALLBACK", api_key),
                label="mistral-vllm",
            ),
            request_timeout_s=float(_req(env, "LLM_TIMEOUT_S", "8.0")),
            guided_decoding=True,
            kafka_bootstrap=kafka_bootstrap,
            topic_in=topic_in,
            topic_out=topic_out,
            consumer_group=consumer_group,
        )

    hf_token = _get(env, "HF_TOKEN")
    hf_base = _req(env, "HF_BASE_URL", "https://router.huggingface.co")
    return Settings(
        profile=Profile.DEVELOPMENT,
        inference=inference,
        primary=Endpoint(
            base_url=hf_base,
            model=_req(env, "LLM_MODEL_PRIMARY", default_model),
            api_key=hf_token,
            label="llama3-hf",
        ),
        fallback=Endpoint(
            base_url=hf_base,
            model=_req(env, "LLM_MODEL_FALLBACK", fallback_model),
            api_key=hf_token,
            label="mistral-hf",
        ),
        request_timeout_s=float(_req(env, "LLM_TIMEOUT_S", "30.0")),
        guided_decoding=False,
        kafka_bootstrap=kafka_bootstrap,
        topic_in=topic_in,
        topic_out=topic_out,
        consumer_group=consumer_group,
    )
