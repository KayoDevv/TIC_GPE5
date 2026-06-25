"""Decision layer -- map the model output onto the canonical wire event.

The wire contract (``zt_shared`` ``LlmLayerResultEvent``) is the agreed binary
form: ``is_malicious`` + ``explanation_text`` + ``confidence_score``. Hard
security gating (ML/Sandbox criticals override the LLM) lives in the Verdict
Engine; here we apply the rules that are the LLM's own responsibility:

* partial evidence (sandbox timeout) may not yield a confident "clean";
* inference/parse failure -> a cautious degraded result so the Saga always
  completes (the user is never blocked);
* a weak prompt-injection hint is appended when the sandbox neutralised
  injection-shaped content (note.txt #2) -- a hint, never a detection claim.

Pure: the clock is injected for deterministic tests.
"""

from __future__ import annotations

from datetime import datetime, timezone

from zt_shared.models.events import LlmLayerResultEvent

from llm_layer.guard import sanitize_explanation
from llm_layer.models import ModelDecision, SandboxResultIn, timed_out

_DEFAULT_CONFIDENCE = 50
_TIMEOUT_CONFIDENCE_CAP = 40

_INJECTION_HINT = (
    " Note: this sample contained prompt-injection-shaped content that was "
    "neutralised before analysis; treat it as a weak signal, not proof of an "
    "attack."
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _injection_suffix(report: SandboxResultIn) -> str:
    return _INJECTION_HINT if report.meta.prompt_injection_filtered > 0 else ""


def build_result(
    report: SandboxResultIn,
    decision: ModelDecision,
    *,
    now: datetime | None = None,
) -> LlmLayerResultEvent:
    confidence = (
        decision.confidence_score
        if decision.confidence_score is not None
        else _DEFAULT_CONFIDENCE
    )
    explanation = sanitize_explanation(decision.explanation_text)

    # Partial evidence must not back a confident "clean".
    if timed_out(report) and not decision.is_malicious:
        confidence = min(confidence, _TIMEOUT_CONFIDENCE_CAP)
        explanation = (
            "The sandbox timed out, so this assessment is based on partial "
            "evidence. " + explanation
        )

    explanation += _injection_suffix(report)

    return LlmLayerResultEvent(
        job_id=report.job_id,
        is_malicious=decision.is_malicious,
        explanation_text=explanation,
        confidence_score=confidence,
        timestamp=now or _now(),
    )


def degraded_result(
    report: SandboxResultIn,
    *,
    reason: str,
    now: datetime | None = None,
) -> LlmLayerResultEvent:
    # Precautionary fallback: flag (is_malicious=True) at zero confidence -- a
    # signal, not a verdict. The Verdict Engine (ML/Sandbox first) makes the call.
    explanation = (
        "Automated semantic analysis could not be completed for this file "
        f"({reason}). As a precaution it is flagged for review; open it only if "
        "you are sure of the sender." + _injection_suffix(report)
    )
    return LlmLayerResultEvent(
        job_id=report.job_id,
        is_malicious=True,
        explanation_text=explanation,
        confidence_score=0,
        timestamp=now or _now(),
    )
