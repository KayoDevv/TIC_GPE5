"""Pure core — D4 prompt-injection neutralization at the output boundary.

The sandbox's attacker-influenced fields (email_context, IOC text, behaviour
summary) feed the LLM Layer's prompt. We strip only the chat-template control
tokens that can switch the model's role (`<|im_start|>`, `[INST]`, `\\n\\nHuman:`);
no intent detection. Neutralised tokens become a visible `[filtered]` marker. No I/O.
"""

from __future__ import annotations

import re

FILTERED = "[filtered]"

# Control tokens that can switch an LLM's role/turn (single-pass alternation).
# The <|...|> form is generalised to catch un-enumerated Llama-family tokens.
_TOKEN_PATTERNS = [
    r"<\|[^|>\n]{0,40}\|>",        # Llama-3 / ChatML: <|...|> (eot_id, im_start, ...)
    r"\[/?INST\]",                  # Llama-2 / Mistral instruction markers
    r"<</?SYS>>",                   # Llama-2 system block
    r"</?s>",                       # BOS / EOS sentinels
    r"<(?:start|end)_of_turn>",     # Gemma turn markers
    r"\n\n(?:Human|Assistant|System):",  # conversational turn boundary
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
