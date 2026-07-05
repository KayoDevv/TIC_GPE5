"""Decision matrix and job state model for the verdict layer (pure, no I/O)."""

from dataclasses import dataclass, field
from typing import Any, Literal, Optional

Decision = Literal["allowed", "blocked", "warning"]

ML_BLOCKED_EXPLANATION = "Blocked: static analysis assigned a critical risk score."
ML_DISPUTED_EXPLANATION = (
    "Warning: static analysis flagged this file, but behavioral analysis did not "
    "confirm it as malicious."
)
LLM_BLOCKED_EXPLANATION = "Blocked: semantic analysis identified malicious intent."
SANDBOX_TIMEOUT_EXPLANATION = "Partial analysis: the behavioral sandbox did not respond in time."
SANDBOX_MALICIOUS_EXPLANATION = "Blocked: behavioral analysis confirmed malicious activity."
SANDBOX_ERROR_EXPLANATION = "Partial analysis: the behavioral sandbox could not analyze this file."


@dataclass
class JobState:
    ml_score: Optional[int] = None
    sandbox_received: bool = False
    sandbox_timeout: bool = False
    sandbox_iocs: list[dict[str, Any]] = field(default_factory=list)
    # 3-band sandbox verdict; None means unknown (LLM still expected to resolve).
    sandbox_verdict: Optional[str] = None
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


def _behavioral_decision(
    state: JobState, timeout_default: str, summary: dict[str, Any]
) -> VerdictDecision:
    if state.llm_is_malicious is True:
        explanation = state.llm_explanation or LLM_BLOCKED_EXPLANATION
        return VerdictDecision("blocked", explanation, summary)

    # A confident terminal sandbox verdict of "malicious" blocks even when the
    # LLM never ran (the LLM only resolves the grey needs_more_context band).
    if state.sandbox_verdict == "malicious":
        return VerdictDecision("blocked", SANDBOX_MALICIOUS_EXPLANATION, summary)

    if state.sandbox_timeout:
        decision: Decision = "blocked" if timeout_default == "blocked" else "warning"
        return VerdictDecision(decision, SANDBOX_TIMEOUT_EXPLANATION, summary)

    # The sandbox errored out (could not analyze): partial evidence -> warning,
    # never a confident "allowed".
    if state.sandbox_verdict == "error":
        return VerdictDecision("warning", SANDBOX_ERROR_EXPLANATION, summary)

    return VerdictDecision("allowed", None, summary)


def decide(
    state: JobState,
    ml_block_threshold: int,
    timeout_default: str,
) -> VerdictDecision:
    summary = _build_summary(state)
    behavioral = _behavioral_decision(state, timeout_default, summary)

    # A critical ML score no longer solo-blocks: the behavioral pipeline
    # (sandbox + LLM) can clear a file the static model flagged, so a single
    # over-confident layer cannot block a document the sandbox found benign.
    if _is_ml_critical(state, ml_block_threshold):
        if behavioral.final_decision == "allowed":
            return VerdictDecision("warning", ML_DISPUTED_EXPLANATION, summary)
        return VerdictDecision("blocked", ML_BLOCKED_EXPLANATION, summary)

    return behavioral
