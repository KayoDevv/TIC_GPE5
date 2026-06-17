from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from zt_shared.models.events import Ioc

from llm_layer.models import SandboxMeta, SandboxResultIn

JOB_ID = UUID("550e8400-e29b-41d4-a716-446655440001")
NOW = datetime(2026, 6, 13, 12, 0, 0, tzinfo=timezone.utc)


def make_report(
    *,
    timeout: bool = False,
    prompt_injection_filtered: int = 0,
    behavior_summary: str = "Sample beaconed to an external host.",
    body_text: str = "Please find attached your payment receipt.",
    sender: str = "billing@example.com",
    iocs: list[Ioc] | None = None,
) -> SandboxResultIn:
    return SandboxResultIn(
        job_id=JOB_ID,
        iocs=iocs if iocs is not None else [
            Ioc(type="ip", value="203.0.113.10", mitre_tactic="TA0011",
                description="outbound beacon"),
        ],
        behavior_summary=behavior_summary,
        email_context={"sender": sender, "subject": "Your receipt", "body_text": body_text},
        timeout_triggered=timeout,
        timestamp=NOW,
        _meta=SandboxMeta(prompt_injection_filtered=prompt_injection_filtered),
    )
