"""Pure core — D4 prompt-injection neutralization at the output boundary.

The fields the sandbox emits (email_context, IOC values, behaviour-summary
fragments) are attacker-influenced and get concatenated into the LLM Layer's
prompt downstream. We strip the chat-template control tokens that can flip the
model out of its data context (`<|im_start|>`, `[INST]`, a `\\n\\nHuman:`
boundary) — the only sequences that switch roles. No intent detection (brittle);
ordinary prose passes through. Neutralised tokens become a visible `[filtered]`
marker since the fields are UI-facing. No I/O — golden-tested (tests/test_sanitize.py).
"""

from __future__ import annotations

import re

FILTERED = "[filtered]"

# Each pattern matches a control token that can switch an LLM's role/turn.
# Order does not matter (single pass, alternation). Kept literal where a family
# uses fixed tokens; the pipe-delimited form is generalised so future
# Llama-family special tokens we did not enumerate are still caught.
_TOKEN_PATTERNS = [
    r"<\|[^|>\n]{0,40}\|>",        # Llama-3 / ChatML: <|...|> (eot_id, im_start, ...)
    r"\[/?INST\]",                  # Llama-2 / Mistral instruction markers
    r"<</?SYS>>",                   # Llama-2 system block
    r"</?s>",                       # BOS / EOS sentinels
    r"<(?:start|end)_of_turn>",     # Gemma turn markers
    r"\n\n(?:Human|Assistant|System):",  # Anthropic-style turn boundary
]
_TOKEN_RE = re.compile("|".join(_TOKEN_PATTERNS), re.IGNORECASE)


def neutralize_untrusted(text):
    """Replace control tokens with `[filtered]`; idempotent no-op on token-free input."""
    if not text or not isinstance(text, str):
        return text
    return _TOKEN_RE.sub(FILTERED, text)


def count_control_tokens(value) -> int:
    """Count control tokens in `value` (str/dict/list, recursive) — a measured fact for `_meta`, not intent detection."""
    if isinstance(value, str):
        return len(_TOKEN_RE.findall(value))
    if isinstance(value, dict):
        return sum(count_control_tokens(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return sum(count_control_tokens(v) for v in value)
    return 0


def sanitize_email_context(ctx: dict) -> dict:
    """Neutralise every string in the attacker-controlled email context (returns a new dict)."""
    if not isinstance(ctx, dict):
        return ctx
    return {k: neutralize_untrusted(v) if isinstance(v, str) else v
            for k, v in ctx.items()}


def sanitize_iocs(iocs: list[dict]) -> list[dict]:
    """Neutralise the sample-derived IOC text (value, description); type/mitre_tactic left verbatim (new dicts)."""
    cleaned: list[dict] = []
    for ioc in iocs:
        new = dict(ioc)
        for field in ("value", "description"):
            if isinstance(new.get(field), str):
                new[field] = neutralize_untrusted(new[field])
        cleaned.append(new)
    return cleaned
