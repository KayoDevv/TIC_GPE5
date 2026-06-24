"""LLM-Layer-local models.

The canonical wire contracts live in ``zt_shared.models.events`` and are the
single source of truth (``SandboxLayerResultEvent`` in, ``LlmLayerResultEvent``
out). This module only adds:

* ``SandboxResultIn`` -- a thin subclass of the canonical input event that also
  captures the optional ``_meta`` block (the sandbox does not emit
  ``prompt_injection_filtered`` yet; we read it when present, default 0);
* ``ModelDecision`` -- the JSON the model is constrained to emit (vLLM
  ``guided_json``), which maps onto the binary ``LlmLayerResultEvent``.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field
from zt_shared.models.events import SandboxLayerResultEvent


class SandboxMeta(BaseModel):
    model_config = ConfigDict(extra="ignore")

    # Count of chat-template control tokens the sandbox neutralised in the
    # sample (note.txt #2). Factual indicator, not a verdict. Optional because
    # the current sandbox build does not emit it yet.
    prompt_injection_filtered: int = 0


class SandboxResultIn(SandboxLayerResultEvent):  # type: ignore[misc]
    model_config = ConfigDict(populate_by_name=True)

    meta: SandboxMeta = Field(default_factory=SandboxMeta, alias="_meta")

    @property
    def timeout_triggered(self) -> bool:
        # Derived from analysis_trust now that the sandbox no longer duplicates it
        # at the top level; absent trust means no observed timeout.
        return bool(self.analysis_trust and self.analysis_trust.timeout_triggered)


class ModelDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_malicious: bool = Field(
        description="Binary decision: does the file behave maliciously?"
    )
    explanation_text: str = Field(
        description="Plain language an SME IT manager understands. State what the "
        "email claims vs what the file did. No attack-reproduction details."
    )
    confidence_score: Optional[int] = Field(
        default=None, ge=0, le=100, description="0-100 confidence in the decision."
    )

    @staticmethod
    def guided_json_schema() -> dict[str, Any]:
        return ModelDecision.model_json_schema()
