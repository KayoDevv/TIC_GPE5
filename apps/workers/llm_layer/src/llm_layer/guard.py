"""Prompt-injection guard (LLM-side, note.txt #3 + Cahier D4).

Two responsibilities, kept separate on purpose:

* :func:`scan_control_tokens` -- the *fail-loud* check. The sandbox is supposed
  to strip chat-template control tokens from untrusted fields before emission.
  This re-scans those fields; if a raw token survived, the sandbox regressed and
  we refuse to build a prompt on poisoned input (the worker turns this into an
  explicit degraded result + error log, and the contract CI catches it at build
  time). We do NOT silently neutralise control tokens -- that would mask the
  regression ("pas de degradation silencieuse").

* :func:`neutralise_envelope` -- envelope integrity, which IS ours to own. The
  Prompt Builder wraps untrusted data in ``<untrusted_sample_data>`` delimiters;
  untrusted text must not be able to close or reopen that envelope, so any
  occurrence of the delimiter tags inside untrusted content is replaced.
"""

from __future__ import annotations

import re
import unicodedata

from llm_layer.models import SandboxResultIn

OPEN_TAG = "<untrusted_sample_data>"
CLOSE_TAG = "</untrusted_sample_data>"

_CONTROL_TOKENS: tuple[str, ...] = (
    "<|begin_of_text|>",
    "<|start_header_id|>",
    "<|end_header_id|>",
    "<|eot_id|>",
    "<|eom_id|>",
    "<|python_tag|>",
    "[INST]",
    "[/INST]",
    "<<SYS>>",
    "<</SYS>>",
    "<s>",
    "</s>",
    "<|im_start|>",
    "<|im_end|>",
)

_PREFIX_RE = re.compile(r"\n\s*\n\s*(human|assistant|system)\s*:", re.IGNORECASE)


# Raised when a raw control token survived in an untrusted field (sandbox regressed).
class SandboxInputRegression(ValueError):
    pass


def untrusted_fields(report: SandboxResultIn) -> dict[str, str]:
    fields: dict[str, str] = {
        "email_context.sender": str(report.email_context.sender),
        "email_context.subject": report.email_context.subject,
        "email_context.body_text": report.email_context.body_text,
        "behavior_summary": report.behavior_summary,
    }
    for i, ioc in enumerate(report.iocs):
        fields[f"iocs[{i}].value"] = ioc.value
        fields[f"iocs[{i}].description"] = ioc.description or ""
    return fields


def scan_text(text: str) -> list[str]:
    if not text:
        return []
    lowered = text.lower()
    hits = [tok for tok in _CONTROL_TOKENS if tok.lower() in lowered]
    if _PREFIX_RE.search(text):
        hits.append(r"\n\nHuman:/Assistant:/System:")
    return hits


def scan_control_tokens(report: SandboxResultIn) -> None:
    violations: list[str] = []
    for where, text in untrusted_fields(report).items():
        violations.extend(f"{where}: {h}" for h in scan_text(text))
    if violations:
        raise SandboxInputRegression(
            "raw control token(s) survived sandbox sanitisation: "
            + "; ".join(sorted(set(violations)))
        )


def neutralise_envelope(text: str) -> str:
    return text.replace(OPEN_TAG, "[filtered]").replace(CLOSE_TAG, "[filtered]")


_MAX_EXPLANATION_CHARS = 2000


def sanitize_explanation(text: str) -> str:
    # LLM-generated from attacker-influenced input and rendered to users downstream:
    # strip control/non-printable chars (log & terminal-escape injection, zero-width
    # tricks), neutralise chat-template tokens + turn prefixes (so it cannot poison a
    # downstream model), and bound the length. The consumer MUST still output-encode
    # it for its render context (HTML-escape in the UI) -- that is context-specific.
    cleaned = "".join(
        ch for ch in text
        if ch in ("\n", "\t") or (ord(ch) >= 0x20 and unicodedata.category(ch)[0] != "C")
    )
    for token in _CONTROL_TOKENS:
        cleaned = cleaned.replace(token, "[filtered]")
    cleaned = _PREFIX_RE.sub(" ", cleaned)
    return cleaned[:_MAX_EXPLANATION_CHARS]
