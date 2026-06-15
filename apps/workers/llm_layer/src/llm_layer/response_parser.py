"""Parse the model's chat-completion content into a validated ``ModelDecision``.

Production (vLLM guided decoding): content is schema-valid JSON, strict path
succeeds. Development (HF Serverless): guided decoding is not guaranteed, so a
lenient step recovers a JSON object embedded in prose or a Markdown fence.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator

from pydantic import ValidationError

from llm_layer.models import ModelDecision

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)


class ResponseParseError(ValueError):
    """Model content could not be parsed into a valid ModelDecision."""


def _candidates(content: str) -> Iterator[str]:
    text = content.strip()
    yield text
    for m in _FENCE_RE.finditer(text):
        yield m.group(1).strip()
    first, last = text.find("{"), text.rfind("}")
    if 0 <= first < last:
        yield text[first : last + 1]


def parse_model_output(content: str) -> ModelDecision:
    """Return a validated :class:`ModelDecision` or raise ``ResponseParseError``."""
    if not content or not content.strip():
        raise ResponseParseError("empty model content")

    last_error: Exception | None = None
    for candidate in _candidates(content):
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError as exc:
            last_error = exc
            continue
        try:
            return ModelDecision.model_validate(data)
        except ValidationError as exc:
            last_error = exc
            continue

    raise ResponseParseError(
        f"no schema-valid JSON object in model content "
        f"({type(last_error).__name__}: {last_error})"
    )
