"""Contract types shared by the hypothesis modules.

Each hypothesis exposes exactly one function:

    def evaluate(
        diff: SnapshotDiff,
        signals: RuntimeSignals,
        memory: MemoryObservables,
    ) -> HypothesisResult

Rules:
    - No network I/O in the hypothesis modules (pure, testable).
    - No direct disk access (all data comes from the models).
    - HypothesisResult.evidence must point to precise facts in the inputs
      (via a traceable field_path) — never a vague string like "the file is suspicious".
    - score in [0.0, 1.0] — the final weighting is in pipeline.py (anomaly_score).
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from models import (
    MemoryObservables,
    RuntimeSignals,
    SnapshotDiff,
)


# ---------------------------------------------------------------------------
# Evidence — traceability to a precise observable
# ---------------------------------------------------------------------------


class Evidence(BaseModel):
    """Traceable reference to a precise observable in the inputs.

    Examples:
        Evidence(
            source="snapshot_diff",
            field_path="persistence_changes[0].path",
            value="/etc/cron.d/evil",
        )
        Evidence(
            source="runtime_signals",
            field_path="network.dns_queries[2].query",
            value="c2.evil.com",
        )
        Evidence(
            source="memory",
            field_path="suspicious_regions[0].permissions",
            value="rwx",
        )
    """

    model_config = ConfigDict(frozen=True)

    source: Literal["snapshot_diff", "runtime_signals", "memory"]
    field_path: str  # JSONPath-like path to the observed field
    value: Annotated[str, Field(max_length=256)]  # observed value, truncated


# ---------------------------------------------------------------------------
# HypothesisResult — output of a hypothesis
# ---------------------------------------------------------------------------


class HypothesisResult(BaseModel):
    """Result of a Layer 2 hypothesis.

    value  : True if the signal is positive (behaviour detected).
    score  : confidence in the detection [0.0 = nothing, 1.0 = certainty].
    evidence : list of precise observables that justify the score.
               Must be non-empty if value=True.

    The score is NOT a verdict — it's a raw signal.
    The weighting and aggregation into the global anomaly_score happen
    in orchestrator/pipeline.py.
    """

    model_config = ConfigDict(frozen=True)

    value: bool
    score: Annotated[float, Field(ge=0.0, le=1.0)]
    evidence: list[Evidence] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# AnomalyScore — aggregation of the hypotheses
# ---------------------------------------------------------------------------


class AllHypothesesResults(BaseModel):
    """Results of the 7 hypotheses + global anomaly_score.

    anomaly_score: computed by run_analysis._compute_anomaly_score().
    Weights are defined in run_analysis.DEFAULT_WEIGHTS and tuned in Phase 7
    via scripts/validation/calibrate_weights.py.

    Pipeline v2 — execution order optimized (descending RAM ROI):
        H5 evasion -> H4 encryption -> H2 c2 -> H7 lolbins -> H6 propagation
        -> H1 persistence -> H3 injection (+ possible early-exit before H3)
    """

    model_config = ConfigDict(frozen=True)

    persistence_detected: HypothesisResult
    c2_communication: HypothesisResult
    code_injection: HypothesisResult
    file_encryption: HypothesisResult
    evasion_attempted: HypothesisResult
    propagation: HypothesisResult
    lolbins_abuse: HypothesisResult          # H7 — pipeline v2 addition
    anomaly_score: Annotated[float, Field(ge=0.0, le=1.0)]


# ---------------------------------------------------------------------------
# Protocol / contractual signature of the modules
# ---------------------------------------------------------------------------

# Each hypotheses/*.py module must expose this function:
#
#   def evaluate(
#       diff: SnapshotDiff,
#       signals: RuntimeSignals,
#       memory: MemoryObservables,
#   ) -> HypothesisResult:
#       ...
#
# No class, no global state — pure function.
# Testable via mocked fixtures in tests/unit/fixtures/.

__all__ = [
    "Evidence",
    "HypothesisResult",
    "AllHypothesesResults",
    "SnapshotDiff",
    "RuntimeSignals",
    "MemoryObservables",
]
