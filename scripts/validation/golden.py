"""Golden run baseline — freeze & compare per-sample verdicts (M3, anti-regression).

Purpose: BEFORE touching core/scoring.py (D1, D-calib, D5...), freeze the
per-sample verdicts of a reference validation run as a committed JSON baseline.
After any scoring change, re-run the same corpus and compare: every verdict-band
move is listed, and the security-critical one (malicious -> benign wash) fails
the comparison. No silent regression.

The baseline contains ONLY sha256 hashes, labels, scores and bands — never
sample bytes or filenames — so it is safe to commit.

Usage (on the VM, where validation/*.duckdb live):

    # 1. Freeze the reference run (writes scripts/validation/golden/baseline.json)
    python3 -m scripts.validation.golden freeze --run-id run_v1.4

    # 2. After a scoring change, replay the SAME corpus under a new run id,
    #    then compare against the frozen baseline:
    python3 -m scripts.validation.golden compare --run-id run_after_D1

    # Exit codes for compare: 0 = no band regression, 1 = regressions found.
    # (Score drift within the same band is reported but does not fail.)

    # 3. Grow the net with hand-picked trap samples surfaced by a benchmark run
    #    (e.g. the passive embedded-dropper class), without re-freezing the whole
    #    baseline. --accept marks a documented out-of-scope sample as non-fatal:
    python3 -m scripts.validation.golden extend --run-id big_test \
        --sha <dropper1> --sha <near_threshold> --accept <fb87d8a7>

Both commands read the DuckDB files via db.fetch_run_results (read-only join
of feeder_state + results), and aggregate repetitions per sample by MEAN score
— same convention as report.py section C.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Allow both `python3 -m scripts.validation.golden` (repo root) and direct call.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.validation.db import fetch_run_results  # noqa: E402
from scripts.validation.report import (  # noqa: E402
    DEFAULT_MALICIOUS_THRESHOLD,
    DEFAULT_SUSPICIOUS_THRESHOLD,
    _predicted_band,
)

DEFAULT_DB_DIR = Path("validation")
DEFAULT_BASELINE = Path(__file__).parent / "golden" / "baseline.json"

# A sample whose |mean_now - mean_baseline| exceeds this is flagged as drift
# even when the band did not move (early warning, non-fatal).
DEFAULT_SCORE_DRIFT = 0.02


# ---------------------------------------------------------------------------
# Aggregation: rows (one per job/rep) -> one entry per sample (sha256)
# ---------------------------------------------------------------------------

def _aggregate(rows: list[dict], susp: float, mal: float) -> dict[str, dict]:
    """Aggregate per-rep rows into one record per sha256 (mean across reps)."""
    by_sha: dict[str, list[dict]] = {}
    for r in rows:
        by_sha.setdefault(r["sha256"], []).append(r)

    out: dict[str, dict] = {}
    for sha, sample_rows in sorted(by_sha.items()):
        scores = [r["anomaly_score"] for r in sample_rows
                  if r["anomaly_score"] is not None and not r["error"]]
        errors = [r["error"] for r in sample_rows if r["error"]]
        mean = sum(scores) / len(scores) if scores else None
        out[sha] = {
            "label":     sample_rows[0]["label"],
            "reps":      len(sample_rows),
            "errors":    len(errors),
            "scores":    [round(s, 6) for s in sorted(scores)],
            "mean":      round(mean, 6) if mean is not None else None,
            "band":      _predicted_band(mean, susp, mal) if mean is not None else "error",
        }
    return out


# ---------------------------------------------------------------------------
# freeze
# ---------------------------------------------------------------------------

def cmd_freeze(args: argparse.Namespace) -> int:
    rows = fetch_run_results(args.db_dir, args.run_id)
    if not rows:
        print(f"ERROR: no results found for run_id={args.run_id!r} in {args.db_dir}/",
              file=sys.stderr)
        return 1

    samples = _aggregate(rows, args.suspicious_threshold, args.threshold)
    baseline = {
        "run_id":     args.run_id,
        "frozen_at":  datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "thresholds": {"suspicious": args.suspicious_threshold,
                       "malicious": args.threshold},
        "samples":    samples,
    }

    args.baseline.parent.mkdir(parents=True, exist_ok=True)
    args.baseline.write_text(
        json.dumps(baseline, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    bands = [s["band"] for s in samples.values()]
    print(f"Baseline frozen: {args.baseline}")
    print(f"  run_id  : {args.run_id}")
    print(f"  samples : {len(samples)} "
          f"(malicious={bands.count('malicious')}, "
          f"needs_more_context={bands.count('needs_more_context')}, "
          f"benign={bands.count('benign')}, error={bands.count('error')})")
    print("Commit it: git add scripts/validation/golden/baseline.json")
    return 0


# ---------------------------------------------------------------------------
# extend — graft hand-picked trap samples from another run onto the baseline
# ---------------------------------------------------------------------------

def cmd_extend(args: argparse.Namespace) -> int:
    """Merge specific samples (by sha256 prefix) from RUN_ID into the baseline.

    Grows the golden with adversarial edge cases surfaced by a larger benchmark
    run — e.g. the passive embedded-dropper class that broke d-calib — without
    re-freezing the whole baseline. Picked samples are re-aggregated with the
    BASELINE's thresholds so their bands stay consistent with the existing ones.

    --accept marks a sample as a documented out-of-scope limit (e.g. fb87d8a7,
    a Windows trojan our Linux detonation cannot execute): compare still REPORTS
    its band moves but never FAILS on them, so the gate stays meaningful while
    the known blind spot stays visible in the net.

        python3 -m scripts.validation.golden extend --run-id big_test \\
            --sha <dropper1> --sha <dropper2> --sha <near_threshold> \\
            --accept <fb87d8a7>
    """
    if not args.baseline.exists():
        print(f"ERROR: baseline not found: {args.baseline}. Run `freeze` first.",
              file=sys.stderr)
        return 1
    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    thr = baseline["thresholds"]

    rows = fetch_run_results(args.db_dir, args.run_id)
    if not rows:
        print(f"ERROR: no results found for run_id={args.run_id!r} in {args.db_dir}/",
              file=sys.stderr)
        return 1
    agg = _aggregate(rows, thr["suspicious"], thr["malicious"])

    samples: dict[str, dict] = baseline["samples"]
    added: list[str] = []
    accepted: list[str] = []
    unmatched: list[str] = []

    def _resolve(prefix: str, pool: dict[str, dict], where: str) -> str | None:
        hits = [sha for sha in pool if sha.startswith(prefix)]
        if len(hits) > 1:
            print(f"ERROR: prefix {prefix!r} matches {len(hits)} samples in {where} "
                  f"— be more specific.", file=sys.stderr)
            raise SystemExit(1)
        return hits[0] if hits else None

    # Gating samples: grafted fresh from the run (we need their current scores).
    for prefix in args.sha:
        sha = _resolve(prefix, agg, f"run {args.run_id!r}")
        if sha is None:
            unmatched.append(prefix)
            continue
        samples[sha] = dict(agg[sha])
        added.append(sha)

    # Accepted (out-of-scope) samples: an out-of-scope sample is typically EXCLUDED
    # from in-scope runs, so look in the existing baseline first, then the run.
    for prefix in args.accept:
        sha = _resolve(prefix, samples, "baseline") or _resolve(prefix, agg, f"run {args.run_id!r}")
        if sha is None:
            unmatched.append(prefix)
            continue
        entry = dict(samples.get(sha) or agg[sha])
        entry["accepted"] = "out_of_scope"
        samples[sha] = entry
        accepted.append(sha)

    if unmatched:
        print(f"ERROR: no sample in run {args.run_id!r} matched prefix(es): "
              f"{', '.join(unmatched)}", file=sys.stderr)
        return 1

    baseline["extended_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    baseline["samples"] = dict(sorted(samples.items()))
    args.baseline.write_text(
        json.dumps(baseline, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"Baseline extended: {args.baseline}")
    print(f"  from run : {args.run_id}")
    print(f"  added    : {len(added)} gating sample(s)")
    print(f"  accepted : {len(accepted)} out-of-scope sample(s) (reported, non-fatal)")
    print(f"  total    : {len(samples)} samples")
    print("Commit it: git add scripts/validation/golden/baseline.json")
    return 0


# ---------------------------------------------------------------------------
# compare
# ---------------------------------------------------------------------------

# Band moves that wash a threat downward = the only true security failures.
_CRITICAL_MOVES = {
    ("malicious", "benign"),
    ("needs_more_context", "benign"),
}


def cmd_compare(args: argparse.Namespace) -> int:
    if not args.baseline.exists():
        print(f"ERROR: baseline not found: {args.baseline}. Run `freeze` first.",
              file=sys.stderr)
        return 1
    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    thr = baseline["thresholds"]

    rows = fetch_run_results(args.db_dir, args.run_id)
    if not rows:
        print(f"ERROR: no results found for run_id={args.run_id!r} in {args.db_dir}/",
              file=sys.stderr)
        return 1
    # Compare with the BASELINE thresholds: a threshold change is a deliberate,
    # reviewed decision and must go through a re-freeze, not slip through here.
    now = _aggregate(rows, thr["suspicious"], thr["malicious"])

    base_samples: dict[str, dict] = baseline["samples"]
    regressions:    list[str] = []  # critical wash, or any move on a malicious sample
    changes:        list[str] = []  # any other band move
    drifts:         list[str] = []  # same band, score moved > tolerance
    accepted_moves: list[str] = []  # band moves on documented out-of-scope samples
    missing = sorted(set(base_samples) - set(now))
    added   = sorted(set(now) - set(base_samples))

    for sha in sorted(set(base_samples) & set(now)):
        b, n = base_samples[sha], now[sha]
        accepted = b.get("accepted")
        tag = f"{sha[:12]}… [{b['label']}{'/' + accepted if accepted else ''}]"
        if b["band"] != n["band"]:
            move = f"{tag} {b['band']} -> {n['band']} (mean {b['mean']} -> {n['mean']})"
            if accepted:
                # Documented limit (e.g. Windows trojan, out of Linux scope):
                # report any move (a fix that finally catches it shows here) but
                # never fail the gate on a sample we accepted we cannot detect.
                accepted_moves.append(move)
            elif (b["band"], n["band"]) in _CRITICAL_MOVES or b["label"] == "malicious":
                regressions.append(move)
            else:
                changes.append(move)
        elif (b["mean"] is not None and n["mean"] is not None
              and abs(b["mean"] - n["mean"]) > args.score_drift):
            drifts.append(f"{tag} score drift {b['mean']} -> {n['mean']} (band stable)")

    print(f"# Golden compare — {args.run_id} vs baseline {baseline['run_id']} "
          f"(frozen {baseline['frozen_at']})\n")
    print(f"samples: baseline={len(base_samples)}  now={len(now)}  "
          f"missing={len(missing)}  added={len(added)}\n")

    def _section(title: str, items: list[str]) -> None:
        if items:
            print(f"## {title} ({len(items)})")
            for it in items:
                print(f"  - {it}")
            print()

    _section("REGRESSIONS (critical — verdict washed or malicious moved)", regressions)
    _section("Accepted out-of-scope moves (documented limit, non-fatal)", accepted_moves)
    _section("Band changes (review)", changes)
    _section(f"Score drift > {args.score_drift} (same band, non-fatal)", drifts)
    _section("Missing from new run (not replayed)", [s[:12] + "…" for s in missing])
    _section("New samples (absent from baseline)", [s[:12] + "…" for s in added])

    if regressions:
        print("RESULT: FAIL — fix the regression or consciously re-freeze the baseline.")
        return 1
    if changes or missing:
        print("RESULT: PASS with warnings (band changes on non-malicious / missing samples).")
        return 0
    print("RESULT: PASS — no verdict regression.")
    return 0


# ---------------------------------------------------------------------------

def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--db-dir", type=Path, default=DEFAULT_DB_DIR,
                   help="directory holding feeder_state.duckdb + results.duckdb")
    p.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE,
                   help=f"baseline JSON path (default: {DEFAULT_BASELINE})")
    sub = p.add_subparsers(dest="cmd", required=True)

    pf = sub.add_parser("freeze", help="freeze a run's verdicts as the baseline")
    pf.add_argument("--run-id", required=True)
    pf.add_argument("--threshold", type=float, default=DEFAULT_MALICIOUS_THRESHOLD)
    pf.add_argument("--suspicious-threshold", type=float,
                    default=DEFAULT_SUSPICIOUS_THRESHOLD)
    pf.set_defaults(fn=cmd_freeze)

    pe = sub.add_parser("extend",
                        help="graft hand-picked samples from a run onto the baseline")
    pe.add_argument("--run-id", required=True,
                    help="source run holding the samples to graft (e.g. big_test)")
    pe.add_argument("--sha", action="append", default=[],
                    help="sha256 prefix of a gating sample to add (repeatable)")
    pe.add_argument("--accept", action="append", default=[],
                    help="sha256 prefix of an out-of-scope sample: reported, never fatal (repeatable)")
    pe.set_defaults(fn=cmd_extend)

    pc = sub.add_parser("compare", help="compare a new run against the baseline")
    pc.add_argument("--run-id", required=True)
    pc.add_argument("--score-drift", type=float, default=DEFAULT_SCORE_DRIFT,
                    help="non-fatal drift tolerance on mean score within a band")
    pc.set_defaults(fn=cmd_compare)

    args = p.parse_args()
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()
