"""Hypothesis 7 — Living-off-the-Land binaries (LOLBins) abuse.

Detects execution of system binaries commonly abused for fileless/staging attacks:
- Download utilities (curl, wget) with pipe-to-shell or URL patterns
- Shell interpreters with inline payload execution (bash -c, python -c)
- Network backdoor utilities (/dev/tcp, nc, socat)
- Encoding tools for payload decode (base64 -d, xxd)

Source: signals.syscalls_summary — execve syscall sample_args.
         Data is AGGREGATED by strace_collector (not per-call) — parent process
         context is not available. Detection relies on argument pattern matching.

RAM cost: ~0 (re-analysis of already-collected strace aggregates).

MITRE: T1059 — Command and Scripting Interpreter
        T1105 — Ingress Tool Transfer (curl/wget with URLs)

Pure function, no I/O. Phase 4.
"""

from __future__ import annotations

import re

from models import (
    MemoryObservables,
    RuntimeSignals,
    SnapshotDiff,
)

from hypotheses._types import Evidence, HypothesisResult

# ---------------------------------------------------------------------------
# Linux LOLBins — system binaries frequently abused
# ---------------------------------------------------------------------------

# Reference: https://gtfobins.github.io/ (shell, download, exec, reverse shell)
_LOLBINS: frozenset[str] = frozenset({
    # Download / exfiltration
    "curl", "wget",
    # Inline script execution
    "python", "python3", "perl", "ruby", "lua", "node",
    # Shells (with -c / inline)
    "bash", "sh", "dash", "zsh",
    # Network (backdoor / tunnel)
    "nc", "ncat", "netcat", "socat",
    # Payload encoding / decoding
    "base64", "xxd",
    # Indirect execution
    "env", "nohup",
})

# ---------------------------------------------------------------------------
# Suspicious argument patterns (matched against strace args_raw string)
# ---------------------------------------------------------------------------

_SUSPICIOUS_PATTERNS: list[tuple[str, float, str]] = [
    # (pattern, score_contribution, description)
    # Strace args are formatted as: '"/path/bin", ["bin", "-flag", "val"], NULL'
    # Arguments are comma-separated and quoted.

    # Download + pipe to shell — classic C2 staging
    (r"https?://\S+.*\|.*(ba)?sh", 0.50, "download|pipe-to-shell URL"),
    (r"/dev/tcp/",                  0.50, "bash /dev/tcp reverse shell"),

    # Inline encoded payload (strace format: "-enc", "AAAA..." or "-e", "AAAA...")
    (r'"-[eE][nN][cC]"',                        0.40, "base64 encoded argument"),
    (r'"-[eE]",\s*"[A-Za-z0-9+/=]{20,}"',       0.40, "base64 encoded argument"),

    # base64 decode (strace: "base64", "-d" or "base64", "--decode")
    (r'"-d"',       0.35, "base64 decode pipeline"),
    (r'"--decode"', 0.35, "base64 decode pipeline"),

    # URL in args without pipe (download alone, less severe)
    (r"https?://\S{10,}",  0.25, "URL in execve args"),

    # Inline shell with pipe/subshell (strace: "-c", "cmd | sh" or "-c", "$(...))")
    (r'"-c",\s*"[^"]*[\|\$\(`]', 0.30, "inline shell with pipe/subshell"),
]

_COMPILED_PATTERNS: list[tuple[re.Pattern[str], float, str]] = [
    (re.compile(pat, re.IGNORECASE | re.DOTALL), score, desc)
    for pat, score, desc in _SUSPICIOUS_PATTERNS
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_binary_name(args_raw: str) -> str | None:
    """Extract the short binary name from a strace execve args string.

    Strace format: '"/usr/bin/curl", ["curl", "-s", "http://..."], NULL'
    -> returns "curl"
    """
    # Look for the first quoted token (binary path)
    m = re.search(r'"([^"]+)"', args_raw)
    if not m:
        return None
    path = m.group(1)
    # Short name = last segment of the path
    return path.rstrip("/").rsplit("/", 1)[-1].lower()


# ---------------------------------------------------------------------------
# evaluate()
# ---------------------------------------------------------------------------

def evaluate(
    diff: SnapshotDiff,    # noqa: ARG001
    signals: RuntimeSignals,
    memory: MemoryObservables,  # noqa: ARG001
) -> HypothesisResult:
    """Detect LOLBin abuse on Linux from aggregated execve syscalls."""

    evidence: list[Evidence] = []
    score = 0.0
    seen_patterns: set[str] = set()  # avoid double-counting on the same pattern

    # Find the execve block in the aggregated syscalls
    execve_summary = next(
        (s for s in signals.syscalls_summary if s.name in ("execve", "execveat")),
        None,
    )
    if not execve_summary:
        return HypothesisResult(value=False, score=0.0, evidence=[])

    for args_raw in execve_summary.sample_args:
        # Ignore the HARNESS's own execution: the agent runs
        # `node /opt/agent/pdf_runner.js` and `python3 /opt/agent/...`. node/python
        # are LOLBins → without this filter, the sandbox detects itself
        # (a 0.10 noise floor on every sample). Filter by the harness's exact PATH
        # (not by binary name): malware that runs `node -e <payload>` with other
        # args is still scored.
        if "/opt/agent" in args_raw:
            continue

        binary = _extract_binary_name(args_raw)
        if binary not in _LOLBINS:
            continue

        # Match suspicious patterns
        hit_pattern = False
        for compiled, contrib, desc in _COMPILED_PATTERNS:
            if desc in seen_patterns:
                continue
            if compiled.search(args_raw):
                score += contrib
                seen_patterns.add(desc)
                evidence.append(Evidence(
                    source="runtime_signals",
                    field_path=f"syscalls_summary[execve].sample_args",
                    value=f"{binary}: {desc} — {args_raw[:200]}",
                ))
                hit_pattern = True

        # LOLBin present without suspicious pattern -> weak signal (presence only)
        if not hit_pattern and f"lolbin_present:{binary}" not in seen_patterns:
            score += 0.10
            seen_patterns.add(f"lolbin_present:{binary}")
            evidence.append(Evidence(
                source="runtime_signals",
                field_path=f"syscalls_summary[execve].sample_args",
                value=f"{binary} executed (no suspicious args pattern)",
            ))

    score = round(min(score, 1.0), 3)
    return HypothesisResult(
        value=score >= 0.25,
        score=score,
        evidence=evidence,
    )
