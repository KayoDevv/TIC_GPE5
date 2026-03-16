from typing import List, Optional, Literal
from pydantic import BaseModel, Field, EmailStr
from datetime import datetime
from uuid import UUID

class EmailContext(BaseModel):
    sender: EmailStr
    subject: str
    body_text: str = Field(description="Contenu du corps de l'email pour le LLM")

class FileRequestedEvent(BaseModel):
    job_id: UUID = Field(description="ID unique de la requête d'analyse")
    s3_url: str = Field(description="URL S3 pré-signée ou chemin du fichier à analyser dans le bucket")
    sha256: str = Field(pattern=r"^[A-Fa-f0-9]{64}$", description="Empreinte SHA-256 du fichier")
    email_context: EmailContext
    timestamp: datetime

class MlLayerResultEvent(BaseModel):
    job_id: UUID
    risk_score: int = Field(ge=0, le=100, description="Score de risque calculé par le modèle ML statique")
    static_tags: List[str] = Field(description="Tags tels que 'packer_detected', 'high_entropy', 'known_malware'")
    processing_time_ms: Optional[int] = Field(default=None, description="Temps de traitement en ms (SLA < 500ms)")
    timestamp: datetime

class Ioc(BaseModel):
    type: Literal["ip", "domain", "file_hash", "registry_key", "syscall"]
    value: str
    mitre_tactic: Optional[str] = Field(default=None, description="Tactic MITRE ATT&CK (ex: TA0011, TA0002)")
    description: Optional[str] = None

class SandboxLayerResultEvent(BaseModel):
    job_id: UUID
    iocs: List[Ioc] = Field(description="Liste des Indicateurs de Compromission")
    behavior_summary: str = Field(description="Résumé brut du comportement pour ingestion par le LLM")
    email_context: EmailContext = Field(description="Pass-through du contexte de l'email depuis request pour le LLM Layer")
    timeout_triggered: bool = False
    timestamp: datetime

class LlmLayerResultEvent(BaseModel):
    job_id: UUID
    is_malicious: bool = Field(description="Décision binaire Malveillant/Sain")
    explanation_text: str = Field(description="Explication en langage naturel pour l'UI Frontend")
    confidence_score: Optional[int] = Field(default=None, ge=0, le=100)
    timestamp: datetime

class TechnicalSummary(BaseModel):
    ml_layer_score: Optional[int] = None
    sandbox_layer_iocs: Optional[List[dict]] = None
    sandbox_layer_timeout: Optional[bool] = None
    llm_layer_malicious: Optional[bool] = None

class VerdictResultEvent(BaseModel):
    job_id: UUID = Field(description="ID unique de la requête d'analyse")
    final_decision: Literal["allowed", "blocked", "warning"] = Field(description="Décision finale à appliquer par le Frontend")
    user_explanation: Optional[str] = Field(default=None, description="Texte explicatif généré par le LLM Layer (si disponible) ou généré par défaut lors d'un timeout Sandbox")
    technical_summary: Optional[TechnicalSummary] = Field(default=None, description="Résumé des données ayant conduit à la décision")
    timestamp: datetime
