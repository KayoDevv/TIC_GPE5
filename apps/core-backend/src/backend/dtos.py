from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class EmailContextDTO(BaseModel):
    """Contexte de l'email envoyé avec la pièce jointe."""

    sender: EmailStr
    subject: str
    body_text: str


class AnalyzeResponseDTO(BaseModel):
    """Réponse 202 Accepted après soumission d'un fichier."""

    job_id: UUID
    message: str = "Analysis started. Connect to WebSocket for the verdict."


class TechnicalSummaryDTO(BaseModel):
    """Résumé technique inclus dans le verdict WebSocket."""

    ml_layer_score: Optional[int] = None
    sandbox_layer_iocs: Optional[list[dict[str, object]]] = None
    sandbox_layer_timeout: Optional[bool] = None
    llm_layer_malicious: Optional[bool] = None


class VerdictMessageDTO(BaseModel):
    """Payload JSON poussé au client via WebSocket."""

    job_id: UUID
    final_decision: Literal["allowed", "blocked", "warning"]
    user_explanation: Optional[str] = None
    technical_summary: Optional[TechnicalSummaryDTO] = None
    timestamp: datetime


class ErrorDTO(BaseModel):
    """Réponse d'erreur standardisée pour toutes les routes 4xx/5xx."""

    error: str = Field(description="Code machine, ex: FILE_TOO_LARGE")
    message: str = Field(description="Description lisible par un humain")