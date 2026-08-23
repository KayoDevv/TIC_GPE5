"""Summarise a semgrep JSON report and fail the build on ERROR findings.

Semgrep runs once and writes JSON; this gates on ERROR only — WARNING and INFO
stay visible without blocking a codebase that was never scanned before. ERROR
findings are printed in full; the lower severities are grouped by rule so a
recurring style warning cannot bury the one finding that matters. Scan errors
(unparsable file, missing ruleset) are reported too, so a degraded scan is not
mistaken for a clean one. The full report is the `semgrep-report` artifact.

Usage: semgrep_report.py <semgrep.json>
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from typing import Any

# Semgrep JSON is free-form; only the keys read below are relied on.
Finding = dict[str, Any]

ORDER = ("ERROR", "WARNING", "INFO")
MAX_EXAMPLES = 3
MAX_SCAN_ERRORS = 5


def location(finding: Finding) -> str:
    return f"{finding.get('path')}:{finding.get('start', {}).get('line', '?')}"


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: semgrep_report.py <semgrep.json>", file=sys.stderr)
        return 2

    with open(sys.argv[1], encoding="utf-8") as handle:
        report = json.load(handle)

    by_severity: defaultdict[str, list[Finding]] = defaultdict(list)
    for finding in report.get("results", []):
        by_severity[finding.get("extra", {}).get("severity", "INFO").upper()].append(finding)

    errors = by_severity["ERROR"]
    if errors:
        print(f"\n=== ERROR ({len(errors)}) ===")
        for finding in errors:
            print(f"{location(finding)}  {finding.get('check_id')}")
            print(f"    {finding.get('extra', {}).get('message', '').strip()}")

    for level in ORDER[1:]:
        findings = by_severity[level]
        if not findings:
            continue
        print(f"\n=== {level} ({len(findings)}) — not blocking ===")
        per_rule: defaultdict[str, list[Finding]] = defaultdict(list)
        for finding in findings:
            per_rule[finding.get("check_id", "?")].append(finding)
        for rule, hits in sorted(per_rule.items(), key=lambda kv: -len(kv[1])):
            examples = ", ".join(location(hit) for hit in hits[:MAX_EXAMPLES])
            more = f", +{len(hits) - MAX_EXAMPLES} more" if len(hits) > MAX_EXAMPLES else ""
            print(f"{len(hits):3d}  {rule}\n     {examples}{more}")

    scan_errors = report.get("errors", [])
    if scan_errors:
        print(f"\n=== SCAN ERRORS ({len(scan_errors)}) ===")
        for error in scan_errors[:MAX_SCAN_ERRORS]:
            print(f"    {error.get('message', error)}")
        if len(scan_errors) > MAX_SCAN_ERRORS:
            hidden = len(scan_errors) - MAX_SCAN_ERRORS
            print(f"    ... {hidden} more, see the semgrep-report artifact")

    counts = ", ".join(f"{level}={len(by_severity[level])}" for level in ORDER)
    print(f"\nSummary: {counts}")

    if errors:
        print("\nFAILED: semgrep reported ERROR-severity findings.")
        return 1

    print("\nPASSED: no ERROR-severity findings.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
