"""Decision matrix and job state model for the verdict layer (pure, no I/O)."""

from dataclasses import dataclass, field
from typing import Any, Literal, Optional

Decision = Literal["allowed", "blocked", "warning"]

ML_BLOCKED_EXPLANATION = "Blocked: static analysis assigned a critical risk score."
LLM_BLOCKED_EXPLANATION = "Blocked: semantic analysis identified malicious intent."
SANDBOX_TIMEOUT_EXPLANATION = "Partial analysis: the behavioral sandbox did not respond in time."


@dataclass
class JobState:
    ml_score: Optional[int] = None
    sandbox_received: bool = False
    sandbox_timeout: bool = False
    sandbox_iocs: list[dict[str, Any]] = field(default_factory=list)
    llm_is_malicious: Optional[bool] = None
    llm_explanation: Optional[str] = None


@dataclass
class VerdictDecision:
    final_decision: Decision
    user_explanation: Optional[str] = None
    technical_summary: Optional[dict[str, Any]] = None


def _build_summary(state: JobState) -> dict[str, Any]:
    return {
        "ml_layer_score": state.ml_score,
        "sandbox_layer_iocs": state.sandbox_iocs or None,
        "sandbox_layer_timeout": state.sandbox_timeout,
        "llm_layer_malicious": state.llm_is_malicious,
    }


def _is_ml_critical(state: JobState, ml_block_threshold: int) -> bool:
    return state.ml_score is not None and state.ml_score > ml_block_threshold


def decide(
    state: JobState,
    ml_block_threshold: int,
    timeout_default: str,
) -> VerdictDecision:
    summary = _build_summary(state)

    if _is_ml_critical(state, ml_block_threshold):
        return VerdictDecision("blocked", ML_BLOCKED_EXPLANATION, summary)

    if state.llm_is_malicious is True:
        explanation = state.llm_explanation or LLM_BLOCKED_EXPLANATION
        return VerdictDecision("blocked", explanation, summary)

    if state.sandbox_timeout:
        decision: Decision = "blocked" if timeout_default == "blocked" else "warning"
        return VerdictDecision(decision, SANDBOX_TIMEOUT_EXPLANATION, summary)

    return VerdictDecision("allowed", None, summary)
