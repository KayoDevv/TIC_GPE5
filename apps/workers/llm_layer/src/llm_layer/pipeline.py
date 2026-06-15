"""Per-event analysis pipeline (the functional spine).

guard -> build prompt -> infer (circuit breaker) -> parse -> decide.

Never raises for inference/parse failures: those collapse to a cautious degraded
result so a verdict is always published. A sandbox-input regression
(:class:`SandboxInputRegression`) is the one condition that propagates -- it is a
contract violation the worker must surface loudly.
"""

from __future__ import annotations

from datetime import datetime

from zt_shared.models.events import LlmLayerResultEvent

from llm_layer.circuit_breaker import AllEndpointsFailed, CircuitBreaker
from llm_layer.decision import build_result, degraded_result
from llm_layer.guard import scan_control_tokens
from llm_layer.models import SandboxResultIn
from llm_layer.prompt_builder import build_prompt
from llm_layer.response_parser import ResponseParseError, parse_model_output


async def analyse(
    report: SandboxResultIn,
    breaker: CircuitBreaker,
    *,
    now: datetime | None = None,
) -> LlmLayerResultEvent:
    # Fail loud on a sandbox sanitiser regression (do not build on poisoned input).
    scan_control_tokens(report)

    prompt = build_prompt(report)

    try:
        completion = await breaker.complete(prompt)
    except AllEndpointsFailed as exc:
        return degraded_result(report, reason=str(exc), now=now)

    try:
        decision = parse_model_output(completion.content)
    except ResponseParseError as exc:
        return degraded_result(report, reason=f"parse: {exc}", now=now)

    return build_result(report, decision, now=now)
