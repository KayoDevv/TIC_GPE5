"""LLM-side validator for sandbox_layer.result payloads.

The LLM Layer consumes sandbox_layer.result. This script asserts the LLM can
extract every field it needs from a given payload. Any future LLM change that
requires a new field MUST update this validator AND bump CONTRACT_VERSION on
both sides — the CI workflow `sandbox-llm-contract.yml` enforces alignment.

Usage: python validate_sandbox_input.py <payload.json>
Exit 0 on success, 1 on missing/invalid field.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REQUIRED_TOP = ("job_id", "iocs", "behavior_summary", "email_context", "timestamp")
REQUIRED_EMAIL = ("sender", "subject", "body_text")
ALLOWED_IOC_TYPES = {"ip", "domain", "file_hash", "registry_key", "syscall"}

# D4 — the LLM Layer injects the attacker-influenced free-text fields below into
# an LLM prompt. The sandbox is contractually required to have neutralized any
# chat-template control token that could flip the model out of its data context
# (see sandbox_layer/agent/core/sanitize.py). The consumer verifies this
# INDEPENDENTLY here: if a raw role-switching token reaches the LLM input, the
# contract is broken and the PR cannot merge. This list mirrors the producer's.
_CONTROL_TOKEN_RE = re.compile(
    r"<\|[^|>\n]{0,40}\|>|\[/?INST\]|<</?SYS>>|</?s>|<(?:start|end)_of_turn>"
    r"|\n\n(?:Human|Assistant|System):",
    re.IGNORECASE,
)


def _assert_injection_safe(payload: dict) -> None:
    """Fail if any prompt-bound free-text field still carries a control token."""
    fields = [("behavior_summary", payload.get("behavior_summary", ""))]
    ctx = payload.get("email_context", {})
    if isinstance(ctx, dict):
        fields += [(f"email_context.{k}", v) for k, v in ctx.items()]
    for i, ioc in enumerate(payload.get("iocs", [])):
        fields.append((f"iocs[{i}].value", ioc.get("value", "")))
        fields.append((f"iocs[{i}].description", ioc.get("description", "")))
    for name, val in fields:
        if isinstance(val, str) and _CONTROL_TOKEN_RE.search(val):
            fail(f"prompt-injection control token survived in {name!r} — "
                 f"sandbox must neutralize it (D4 contract)")


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def validate(payload: dict) -> None:
    for k in REQUIRED_TOP:
        if k not in payload:
            fail(f"missing top-level field: {k}")

    if not isinstance(payload["iocs"], list):
        fail("iocs must be a list")
    for i, ioc in enumerate(payload["iocs"]):
        if "type" not in ioc or "value" not in ioc:
            fail(f"iocs[{i}] missing type/value")
        if ioc["type"] not in ALLOWED_IOC_TYPES:
            fail(f"iocs[{i}].type={ioc['type']!r} not in {ALLOWED_IOC_TYPES}")

    if not isinstance(payload["behavior_summary"], str) or not payload["behavior_summary"].strip():
        fail("behavior_summary must be a non-empty string (LLM prompt input)")

    ctx = payload["email_context"]
    if not isinstance(ctx, dict):
        fail("email_context must be an object")
    for k in REQUIRED_EMAIL:
        if k not in ctx:
            fail(f"email_context.{k} missing")

    _assert_injection_safe(payload)

    print(f"OK ({len(payload['iocs'])} IoCs, summary={len(payload['behavior_summary'])} chars, injection-safe)")


def main() -> None:
    if len(sys.argv) != 2:
        fail("usage: validate_sandbox_input.py <payload.json>")
    path = Path(sys.argv[1])
    payload = json.loads(path.read_text(encoding="utf-8"))
    validate(payload)


if __name__ == "__main__":
    main()
