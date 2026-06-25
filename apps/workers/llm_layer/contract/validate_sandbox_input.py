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
from collections.abc import Iterator
from pathlib import Path

REQUIRED_TOP = ("job_id", "iocs", "behavior_summary", "email_context", "timestamp")
REQUIRED_EMAIL = ("sender",)
OPTIONAL_EMAIL = ("subject", "body_text")
ALLOWED_IOC_TYPES = {"ip", "domain", "file_hash", "registry_key", "syscall", "pdf_indicator"}

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


def _iter_strings(value: object) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _iter_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_strings(item)


def _assert_injection_safe(payload: dict) -> None:
    # Whole-payload sweep backing the "injection-safe" claim end to end: no string
    # anywhere in the event -- including fields the per-field checks above do not
    # enumerate -- may carry a raw chat-template control token or turn prefix.
    for text in _iter_strings(payload):
        low = text.lower()
        for tok in CONTROL_TOKENS:
            if tok.lower() in low:
                fail(f"raw control token {tok!r} survived in payload (sandbox regression)")
        if _PREFIX_RE.search(text):
            fail("raw conversational prefix survived in payload (sandbox regression)")


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
    for k in (*REQUIRED_EMAIL, *OPTIONAL_EMAIL):
        if k in ctx:
            _check_no_control_tokens(f"email_context.{k}", ctx[k])

    _assert_injection_safe(payload)

    print(
        f"OK ({len(payload['iocs'])} IoCs, "
        f"summary={len(payload['behavior_summary'])} chars, injection-safe)"
    )


def main() -> None:
    if len(sys.argv) != 2:
        fail("usage: validate_sandbox_input.py <payload.json>")
    path = Path(sys.argv[1])
    payload = json.loads(path.read_text(encoding="utf-8"))
    validate(payload)


if __name__ == "__main__":
    main()
