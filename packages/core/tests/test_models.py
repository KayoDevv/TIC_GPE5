from datetime import datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from zt_shared.models.events import (
    FileRequestedEvent,
    Ioc,
    LlmLayerResultEvent,
    MlLayerResultEvent,
    SandboxLayerResultEvent,
    VerdictResultEvent,
)


def test_file_requested_event_valid(valid_email_context):
    event = FileRequestedEvent(
        job_id=uuid4(),
        s3_url="s3://bucket/file.exe",
        sha256="a"*64,
        email_context=valid_email_context,
        timestamp=datetime.now()
    )
    assert event.sha256 == "a"*64

def test_file_requested_event_invalid_sha256(valid_email_context):
    with pytest.raises(ValidationError):
        FileRequestedEvent(
            job_id=uuid4(),
            s3_url="s3://bucket/file.exe",
            sha256="invalid", # Too short, not 64 hex chars
            email_context=valid_email_context,
            timestamp=datetime.now()
        )

def test_ml_layer_event_valid():
    event = MlLayerResultEvent(
        job_id=uuid4(),
        risk_score=95,
        static_tags=["packer"],
        timestamp=datetime.now()
    )
    assert event.risk_score == 95

def test_ml_layer_event_defaults_to_completed_analysis():
    event = MlLayerResultEvent(
        job_id=uuid4(),
        risk_score=10,
        static_tags=[],
        timestamp=datetime.now()
    )
    assert event.analysis_status == "completed"

def test_ml_layer_event_accepts_an_abstention_status():
    event = MlLayerResultEvent(
        job_id=uuid4(),
        risk_score=0,
        static_tags=["unsupported_file_type"],
        analysis_status="unsupported_file_type",
        timestamp=datetime.now()
    )
    assert event.analysis_status == "unsupported_file_type"

def test_ml_layer_event_rejects_unknown_analysis_status():
    with pytest.raises(ValidationError):
        MlLayerResultEvent(
            job_id=uuid4(),
            risk_score=0,
            static_tags=[],
            analysis_status="not-a-status",
            timestamp=datetime.now()
        )

def test_ml_layer_event_invalid_score():
    with pytest.raises(ValidationError):
        MlLayerResultEvent(
            job_id=uuid4(),
            risk_score=150, # Must be <= 100
            static_tags=[],
            timestamp=datetime.now()
        )

def test_sandbox_layer_event_valid(valid_email_context):
    ioc = Ioc(type="ip", value="192.168.1.1", mitre_tactic="TA0011")
    event = SandboxLayerResultEvent(
        job_id=uuid4(),
        iocs=[ioc],
        behavior_summary="Opened connection",
        email_context=valid_email_context,
        timestamp=datetime.now()
    )
    assert len(event.iocs) == 1

def test_sandbox_layer_event_invalid_ioc_type(valid_email_context):
    with pytest.raises(ValidationError):
        Ioc(type="invalid_type", value="123")

def test_llm_layer_event_valid():
    event = LlmLayerResultEvent(
        job_id=uuid4(),
        is_malicious=True,
        explanation_text="It's malware",
        timestamp=datetime.now()
    )
    assert event.is_malicious is True

def test_verdict_result_event_valid():
    event = VerdictResultEvent(
        job_id=uuid4(),
        final_decision="blocked",
        timestamp=datetime.now()
    )
    assert event.final_decision == "blocked"

def test_verdict_result_event_invalid_decision():
    with pytest.raises(ValidationError):
        VerdictResultEvent(
            job_id=uuid4(),
            final_decision="maybe", # Invalid literal
            timestamp=datetime.now()
        )
