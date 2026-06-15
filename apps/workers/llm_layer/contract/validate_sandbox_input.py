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

# note.txt #3 / Cahier D4: the sandbox must strip chat-template control tokens
# from the untrusted fields before emission. This validator rejects any payload
# where a raw token survived -- if it ever fires, the sandbox side regressed and
# CI must go red rather than the LLM silently working around it.
CONTROL_TOKENS = (
    "<|begin_of_text|>", "<|start_header_id|>", "<|end_header_id|>",
    "<|eot_id|>", "<|eom_id|>", "<|python_tag|>",
    "[INST]", "[/INST]", "<<SYS>>", "<</SYS>>", "<s>", "</s>",
    "<|im_start|>", "<|im_end|>",
)
_PREFIX_RE = re.compile(r"\n\s*\n\s*(human|assistant|system)\s*:", re.IGNORECASE)


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def _check_no_control_tokens(where: str, text: str) -> None:
    if not isinstance(text, str):
        return
    low = text.lower()
    for tok in CONTROL_TOKENS:
        if tok.lower() in low:
            fail(f"raw control token {tok!r} survived in {where} (sandbox regression)")
    if _PREFIX_RE.search(text):
        fail(f"raw conversational prefix survived in {where} (sandbox regression)")


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
        _check_no_control_tokens(f"iocs[{i}].value", ioc["value"])
        _check_no_control_tokens(f"iocs[{i}].description", ioc.get("description", ""))

    if not isinstance(payload["behavior_summary"], str) or not payload["behavior_summary"].strip():
        fail("behavior_summary must be a non-empty string (LLM prompt input)")
    _check_no_control_tokens("behavior_summary", payload["behavior_summary"])

    ctx = payload["email_context"]
    if not isinstance(ctx, dict):
        fail("email_context must be an object")
    for k in REQUIRED_EMAIL:
        if k not in ctx:
            fail(f"email_context.{k} missing")
        _check_no_control_tokens(f"email_context.{k}", ctx[k])

    print(f"OK ({len(payload['iocs'])} IoCs, summary={len(payload['behavior_summary'])} chars)")


def main() -> None:
    if len(sys.argv) != 2:
        fail("usage: validate_sandbox_input.py <payload.json>")
    path = Path(sys.argv[1])
    payload = json.loads(path.read_text(encoding="utf-8"))
    validate(payload)


if __name__ == "__main__":
    main()
