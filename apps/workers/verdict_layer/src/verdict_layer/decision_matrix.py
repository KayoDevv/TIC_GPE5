"""Decision matrix and job state model for the verdict layer (pure, no I/O)."""

from dataclasses import dataclass, field
from typing import Any, Literal, Optional

from zt_shared.models.events import ML_ANALYSIS_COMPLETED, MlAnalysisStatus

Decision = Literal["allowed", "blocked", "warning"]

ALLOWED_ON_ML_ABSTENTION = "allowed"

ML_BLOCKED_EXPLANATION = (
    "Blocked: static analysis assigned a near-certain risk score and behavioral "
    "analysis could not complete."
)
ML_DISPUTED_EXPLANATION = (
    "Warning: static analysis flagged this file, but behavioral analysis did not "
    "confirm it as malicious."
)
LLM_BLOCKED_EXPLANATION = "Blocked: semantic analysis identified malicious intent."
SANDBOX_TIMEOUT_EXPLANATION = "Partial analysis: the behavioral sandbox did not respond in time."
SANDBOX_MALICIOUS_EXPLANATION = "Blocked: behavioral analysis confirmed malicious activity."
SANDBOX_ERROR_EXPLANATION = "Partial analysis: the behavioral sandbox could not analyze this file."
ML_ABSTAINED_EXPLANATION = (
    "Partial analysis: static analysis could not examine this file, so only "
    "behavioral analysis was applied."
)


@dataclass
class JobState:
    ml_score: Optional[int] = None
    # None means no ml_layer.result has arrived yet; any status other than
    # "completed" is an abstention and its ml_score carries no opinion.
    ml_status: Optional[MlAnalysisStatus] = None
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
        "ml_layer_score": None if _ml_abstained(state) else state.ml_score,
        "ml_layer_status": state.ml_status,
        "sandbox_layer_iocs": state.sandbox_iocs or None,
        "sandbox_layer_timeout": state.sandbox_timeout,
        "llm_layer_malicious": state.llm_is_malicious,
    }


def _ml_abstained(state: JobState) -> bool:
    return state.ml_status is not None and state.ml_status != ML_ANALYSIS_COMPLETED


def _is_ml_above(state: JobState, threshold: int) -> bool:
    if _ml_abstained(state):
        return False
    return state.ml_score is not None and state.ml_score > threshold


def _needs_abstention_warning(state: JobState, ml_abstain_verdict: str) -> bool:
    return _ml_abstained(state) and ml_abstain_verdict != ALLOWED_ON_ML_ABSTENTION


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
    ml_solo_block_threshold: int,
    timeout_default: str,
    ml_abstain_verdict: str,
) -> VerdictDecision:
    summary = _build_summary(state)
    behavioral = _behavioral_decision(state, timeout_default, summary)

    # The static model is mostly advisory: a critical score only raises a clean
    # behavioral result to a warning. It blocks alone only when near-certain and
    # the behavioral analysis is partial; a clean sandbox always overrides it.
    if behavioral.final_decision == "allowed":
        if _is_ml_above(state, ml_block_threshold):
            return VerdictDecision("warning", ML_DISPUTED_EXPLANATION, summary)
    elif behavioral.final_decision == "warning" and _is_ml_above(state, ml_solo_block_threshold):
        return VerdictDecision("blocked", ML_BLOCKED_EXPLANATION, summary)

    # An "allowed" that rests on the behavioral layers alone is one layer short
    # of the designed defence, so it is reported as partial rather than clean.
    if behavioral.final_decision == "allowed" and _needs_abstention_warning(
        state, ml_abstain_verdict
    ):
        return VerdictDecision("warning", ML_ABSTAINED_EXPLANATION, summary)

    return behavioral
