"""Types contractuels partagés par les 6 modules d'hypothèse.

Chaque hypothèse expose exactement une fonction :

    def evaluate(
        diff: SnapshotDiff,
        signals: RuntimeSignals,
        memory: MemoryObservables,
    ) -> HypothesisResult

Règles :
    - Pas d'I/O réseau dans les modules hypothèses (purs, testables).
    - Pas d'accès disque direct (toutes les données viennent des modèles).
    - HypothesisResult.evidence doit pointer vers des faits précis dans les inputs
      (via field_path traçable) — jamais de string vague comme "le fichier est suspect".
    - score en [0.0, 1.0] — la pondération finale est dans pipeline.py (anomaly_score).
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
# Evidence — traçabilité vers un observable précis
# ---------------------------------------------------------------------------


class Evidence(BaseModel):
    """Référence traçable vers un observable précis dans les inputs.

    Exemples :
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
    field_path: str  # chemin JSONPath-like vers le champ observé
    value: Annotated[str, Field(max_length=256)]  # valeur observée, tronquée


# ---------------------------------------------------------------------------
# HypothesisResult — sortie d'une hypothèse
# ---------------------------------------------------------------------------


class HypothesisResult(BaseModel):
    """Résultat d'une hypothèse Couche 2.

    value  : True si le signal est positif (comportement détecté).
    score  : confiance dans la détection [0.0 = rien, 1.0 = certitude].
    evidence : liste d'observables précis qui justifient le score.
               Doit être non vide si value=True.

    Le score N'EST PAS un verdict — c'est un signal brut.
    La pondération et l'agrégation en anomaly_score global se font
    dans orchestrator/pipeline.py.
    """

    model_config = ConfigDict(frozen=True)

    value: bool
    score: Annotated[float, Field(ge=0.0, le=1.0)]
    evidence: list[Evidence] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# AnomalyScore — agrégation des 6 hypothèses
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
# Protocol / signature contractuelle des 6 modules
# ---------------------------------------------------------------------------

# Chaque module hypotheses/*.py doit exposer cette fonction :
#
#   def evaluate(
#       diff: SnapshotDiff,
#       signals: RuntimeSignals,
#       memory: MemoryObservables,
#   ) -> HypothesisResult:
#       ...
#
# Pas de classe, pas d'état global — fonction pure.
# Testable via fixtures mockées dans tests/unit/fixtures/.

__all__ = [
    "Evidence",
    "HypothesisResult",
    "AllHypothesesResults",
    "SnapshotDiff",
    "RuntimeSignals",
    "MemoryObservables",
]
