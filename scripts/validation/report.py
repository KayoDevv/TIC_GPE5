"""Generate the validation report from validation/feeder_state.duckdb + results.duckdb.

Three sections:
  A. Determinism    — for samples with ≥2 repetitions in a run, measures |Δscore|.
  B. Distribution   — histogram + per-label stats, comparison across run_ids if available.
  C. Accuracy       — confusion matrix / precision / recall / F1, only on labelled samples.

Output: Markdown on stdout (redirect to a file if needed).

Usage:
    python -m scripts.validation.report                         # all runs
    python -m scripts.validation.report --run-id 2026-04-29_run1
    python -m scripts.validation.report --threshold 0.40 > validation/report.md
"""

from __future__ import annotations

import argparse
import statistics
from collections import defaultdict
from pathlib import Path

from . import db
from .stats import fmt_rate

# Verdict bands — aligned with run_pdf_analysis._verdict_band.
# The sandbox is a tie-breaker: it only says "malicious" with a strong signal,
# "benign" only in the absence of signal, and escalates the ambiguous middle to
# the LLM (needs_more_context). The accuracy matrix reflects these 3 bands.
DEFAULT_MALICIOUS_THRESHOLD = 0.15
DEFAULT_SUSPICIOUS_THRESHOLD = 0.04
DEFAULT_DELTA = 0.05       # determinism tolerance


def _predicted_band(score: float, susp: float, mal: float) -> str:
    if score >= mal:
        return "malicious"
    if score >= susp:
        return "needs_more_context"
    return "benign"


# ---------------------------------------------------------------------------
# Stats helpers
# ---------------------------------------------------------------------------

def _safe_div(n: float, d: float) -> float:
    return n / d if d else 0.0


def _pct(n: int, d: int) -> str:
    return f"{100.0 * _safe_div(n, d):.1f}%"


def _quantiles(values: list[float], qs: list[float]) -> dict[float, float]:
    if not values:
        return {q: 0.0 for q in qs}
    s = sorted(values)
    out = {}
    for q in qs:
        idx = max(0, min(len(s) - 1, int(round(q * (len(s) - 1)))))
        out[q] = s[idx]
    return out


# ---------------------------------------------------------------------------
# Section A — determinism
# ---------------------------------------------------------------------------

def section_determinism(rows: list[dict], delta_threshold: float) -> str:
    by_run_sha: dict[tuple[str, str], list[float]] = defaultdict(list)
    for r in rows:
        if r["anomaly_score"] is None:
            continue
        by_run_sha[(r["run_id"], r["sha256"])].append(r["anomaly_score"])

    multi = [(k, v) for k, v in by_run_sha.items() if len(v) >= 2]
    out = ["## A. Determinism\n"]
    if not multi:
        out.append("_No sample with ≥ 2 repetitions in the same run — re-run the feeder with `--repetitions 2`._\n")
        return "\n".join(out)

    deltas = [max(v) - min(v) for _, v in multi]
    stable = sum(1 for d in deltas if d < delta_threshold)
    total = len(deltas)
    avg_delta = statistics.fmean(deltas)
    p95 = _quantiles(deltas, [0.95])[0.95]
    worst = sorted(multi, key=lambda kv: max(kv[1]) - min(kv[1]), reverse=True)[:5]

    out.append(f"- Samples with ≥ 2 repetitions: **{total}**")
    out.append(f"- Stable (Δ < {delta_threshold}): **{stable} ({_pct(stable, total)})**")
    out.append(f"- Mean Δ: **{avg_delta:.4f}**  ·  Δ p95: **{p95:.4f}**\n")
    out.append("**Top 5 most unstable:**\n")
    out.append("| sha256 (prefix) | run_id | scores | Δ |")
    out.append("|---|---|---|---|")
    for (run_id, sha), scores in worst:
        scores_s = ", ".join(f"{s:.3f}" for s in scores)
        out.append(f"| `{sha[:12]}` | `{run_id}` | {scores_s} | {max(scores) - min(scores):.4f} |")
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------
# Section B — distribution
# ---------------------------------------------------------------------------

def section_distribution(rows: list[dict]) -> str:
    out = ["## B. Score distribution\n"]
    by_label: dict[str, list[float]] = defaultdict(list)
    by_run: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        if r["anomaly_score"] is None:
            continue
        by_label[r["label"] or "unknown"].append(r["anomaly_score"])
        by_run[r["run_id"]].append(r["anomaly_score"])

    if not by_label:
        out.append("_No score received._\n")
        return "\n".join(out)

    out.append("**Per-label stats:**\n")
    out.append("| label | N | min | p25 | median | p75 | p95 | max | mean |")
    out.append("|---|---|---|---|---|---|---|---|---|")
    for label, scores in sorted(by_label.items()):
        q = _quantiles(scores, [0.25, 0.5, 0.75, 0.95])
        out.append(f"| {label} | {len(scores)} | {min(scores):.3f} | {q[0.25]:.3f} | "
                   f"{q[0.5]:.3f} | {q[0.75]:.3f} | {q[0.95]:.3f} | {max(scores):.3f} | "
                   f"{statistics.fmean(scores):.3f} |")

    if len(by_run) >= 2:
        out.append("\n**Per-run stats (inter-run stability test):**\n")
        out.append("| run_id | N | median | mean | std-dev |")
        out.append("|---|---|---|---|---|")
        for run_id, scores in sorted(by_run.items()):
            sd = statistics.pstdev(scores) if len(scores) > 1 else 0.0
            med = _quantiles(scores, [0.5])[0.5]
            out.append(f"| `{run_id}` | {len(scores)} | {med:.3f} | {statistics.fmean(scores):.3f} | {sd:.3f} |")

    # Text histogram — the "= 0" bucket is SEPARATE from the rest: a zero score
    # (no signal observed) is qualitatively different from a low score (0.045 =
    # a faint signal). Without this split, contentless misses hide among the
    # benigns in [0.00, 0.05).
    bins = [0.0, 0.001, 0.05, 0.10, 0.15, 0.25, 0.40, 0.60, 0.80, 1.01]
    all_scores = [s for v in by_label.values() for s in v]
    counts = [0] * (len(bins) - 1)
    for s in all_scores:
        for i in range(len(bins) - 1):
            if bins[i] <= s < bins[i + 1]:
                counts[i] += 1
                break
    out.append("\n**Global histogram:**\n")
    out.append("```")
    max_c = max(counts) or 1
    for i, c in enumerate(counts):
        bar = "█" * int(40 * c / max_c)
        if i == 0:
            label = "= 0.000 (no signal)"
        elif i == 1:
            label = "(0.000, 0.05)"
        else:
            label = f"[{bins[i]:.2f}, {bins[i+1]:.2f})"
        out.append(f"{label:24} {c:5d}  {bar}")
    out.append("```")

    # Per-label zero-score breakdown: surfaces the misses (malicious at 0 =
    # contentless, undetectable without rendering/context) vs clean benigns.
    zero_by_label = {
        lbl: sum(1 for s in scores if s < 0.001)
        for lbl, scores in by_label.items()
    }
    zero_detail = ", ".join(f"{lbl}={n}" for lbl, n in sorted(zero_by_label.items()) if n)
    if zero_detail:
        out.append(f"\n_Zero score (no signal observed): {zero_detail}. "
                   f"The `malicious` ones at 0 are the contentless misses._")
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------
# Section C — accuracy (labels required)
# ---------------------------------------------------------------------------

def _aggregate_labelled(
    rows: list[dict],
) -> tuple[dict[tuple[str, str], list[float]], dict[tuple[str, str], str], set[tuple[str, str]]]:
    """Dedup labelled rows by (run_id, sha256), averaging reps.

    M2 anti-circularity: samples labelled by AV consensus are split off into
    `av_excluded` (a metric scored on the same AV the sandbox imitates is
    circular). Returns (groups, label_of, av_excluded).
    """
    groups: dict[tuple[str, str], list[float]] = defaultdict(list)
    label_of: dict[tuple[str, str], str] = {}
    av_excluded: set[tuple[str, str]] = set()
    for r in rows:
        if r["anomaly_score"] is None or r["label"] not in ("benign", "malicious"):
            continue
        key = (r["run_id"], r["sha256"])
        if r.get("label_source") == "av_consensus":
            av_excluded.add(key)
            continue
        groups[key].append(r["anomaly_score"])
        label_of[key] = r["label"]
    return groups, label_of, av_excluded


def _confusion_matrix(
    groups: dict[tuple[str, str], list[float]],
    label_of: dict[tuple[str, str], str],
    susp_threshold: float,
    mal_threshold: float,
) -> tuple[dict, list[tuple[str, float]], list[tuple[str, float]]]:
    """3-band confusion matrix m[actual][predicted] + FP / miss example lists."""
    m = {a: {"benign": 0, "needs_more_context": 0, "malicious": 0} for a in ("benign", "malicious")}
    fp_examples: list[tuple[str, float]] = []      # benign predicted malicious (true error)
    miss_examples: list[tuple[str, float]] = []     # malicious predicted benign (true miss)
    for key, scores in groups.items():
        avg = statistics.fmean(scores)
        band = _predicted_band(avg, susp_threshold, mal_threshold)
        actual = label_of[key]
        m[actual][band] += 1
        if actual == "benign" and band == "malicious":
            fp_examples.append((key[1], avg))
        elif actual == "malicious" and band == "benign":
            miss_examples.append((key[1], avg))
    return m, fp_examples, miss_examples


def _format_accuracy(
    m: dict,
    av_excluded: set,
    fp_examples: list[tuple[str, float]],
    miss_examples: list[tuple[str, float]],
    susp_threshold: float,
    mal_threshold: float,
) -> list[str]:
    """Render the §C markdown (matrix + Wilson-CI metrics + caveats) from the matrix."""
    nb = sum(m["benign"].values())
    nm = sum(m["malicious"].values())
    tp = m["malicious"]["malicious"]
    fp = m["benign"]["malicious"]
    miss = m["malicious"]["benign"]
    esc_mal = m["malicious"]["needs_more_context"]
    esc_ben = m["benign"]["needs_more_context"]
    tn = m["benign"]["benign"]

    precision = _safe_div(tp, tp + fp)
    recall_strict = _safe_div(tp, nm)
    f1 = _safe_div(2 * precision * recall_strict, precision + recall_strict)

    out = []
    out.append(f"Bands: **benign** < {susp_threshold} ≤ **needs_more_context** < {mal_threshold} ≤ **malicious**\n")
    out.append("**3-band matrix:**\n")
    out.append("| truth \\ predicted | benign | needs_more_context | malicious |")
    out.append("|---|---|---|---|")
    out.append(f"| **benign** (N={nb})    | {tn} ✅ | {esc_ben} (→LLM) | {fp} ❌ FP |")
    out.append(f"| **malicious** (N={nm}) | {miss} ❌ miss | {esc_mal} (→LLM) | {tp} ✅ |\n")

    # P0c/P0d — every rate carries a Wilson 95% CI + N. A point estimate on a
    # small corpus is not a result; precision 1.0 on a handful of positives has
    # a wide interval and must be read as such.
    out.append(f"- **Confident precision**: {fmt_rate(tp, tp + fp)}  (when the sandbox says *malicious*)")
    out.append(f"- **Confident recall**: {fmt_rate(tp, nm)}  (malicious classified *malicious* directly)")
    out.append(f"- **Recall with escalation**: {fmt_rate(tp + esc_mal, nm)}  (confirmed *or* escalated, never washed)")
    out.append(f"- **False-negative rate (sandbox layer)**: {fmt_rate(miss, nm)}  ← malicious washed to benign — the only real security failure")
    out.append(f"- **Confident F1**: **{f1:.3f}** _(point estimate — composite, no single CI)_")
    out.append(f"- **LLM escalation**: {esc_mal} malicious + {esc_ben} benign → resolved with the email_context")
    out.append("\n> **End-to-end (post-LLM) accuracy is NOT measured here.** The figures above are the "
               "**sandbox layer in isolation**; the LLM Layer that resolves the escalated band does not yet "
               "exist. The false-negative rate is therefore a sandbox-layer floor, not the system's.")
    if av_excluded:
        out.append(f"> **Label independence (M2):** {len(av_excluded)} sample(s) with `av_consensus` labels "
                   f"were **excluded** from the figures above — scoring against the same AV the sandbox "
                   f"imitates would be circular. Independent labels only (academic / synthetic / unspecified).")
    out.append("")

    if fp_examples:
        out.append("**False positives (benign predicted malicious):**")
        for sha, sc in sorted(fp_examples, key=lambda x: -x[1])[:5]:
            out.append(f"- `{sha[:16]}`  score={sc:.3f}")
        out.append("")
    if miss_examples:
        out.append("**Misses (malicious predicted benign):**")
        for sha, sc in sorted(miss_examples, key=lambda x: x[1])[:5]:
            out.append(f"- `{sha[:16]}`  score={sc:.3f}")
        out.append("")
    return out


def section_justness(rows: list[dict], susp_threshold: float, mal_threshold: float) -> str:
    out = ["## C. Accuracy (vs labels) — 3-band verdict\n"]

    groups, label_of, av_excluded = _aggregate_labelled(rows)
    if not groups:
        msg = "_No independently-labelled `benign`/`malicious` sample received — section skipped._"
        if av_excluded:
            msg += (f"\n\n_({len(av_excluded)} sample(s) excluded as `av_consensus` — "
                    f"circular labels, see M2.)_")
        out.append(msg + "\n")
        return "\n".join(out)

    m, fp_examples, miss_examples = _confusion_matrix(groups, label_of, susp_threshold, mal_threshold)
    out += _format_accuracy(m, av_excluded, fp_examples, miss_examples, susp_threshold, mal_threshold)
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Section 0 — executive summary
# ---------------------------------------------------------------------------

def section_summary(rows: list[dict], db_dir: Path, run_id: str | None) -> str:
    run_ids = db.list_run_ids(db_dir)
    received = len(rows)
    timeouts = sum(1 for r in rows if r["timeout_triggered"])
    errors   = sum(1 for r in rows if r["error"])
    by_label: dict[str, int] = defaultdict(int)
    for r in rows:
        by_label[r["label"] or "unknown"] += 1

    inflight = db.inflight_total(db_dir)

    out = ["# Sandbox validation report\n"]
    out.append(f"- Distinct runs: **{len(run_ids)}**  ({', '.join(run_ids[:5])}{'…' if len(run_ids) > 5 else ''})")
    if run_id:
        out.append(f"- Active filter: **run_id={run_id}**")
    out.append(f"- Results collected: **{received}**")
    out.append(f"- Still inflight (not received): **{inflight}**")
    out.append(f"- Timeouts: **{timeouts}** ({_pct(timeouts, received)})")
    out.append(f"- Agent errors: **{errors}**")
    out.append(f"- Label breakdown: " + ", ".join(f"{k}={v}" for k, v in sorted(by_label.items())))
    out.append("")
    return "\n".join(out)


# ---------------------------------------------------------------------------

def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--db-dir", type=Path, default=Path("validation"),
                   help="Folder containing feeder_state.duckdb + results.duckdb (default: validation/)")
    p.add_argument("--run-id", default=None, help="Filter on a single run_id")
    p.add_argument("--threshold", type=float, default=DEFAULT_MALICIOUS_THRESHOLD,
                   help=f"malicious band threshold (default: {DEFAULT_MALICIOUS_THRESHOLD})")
    p.add_argument("--suspicious-threshold", type=float, default=DEFAULT_SUSPICIOUS_THRESHOLD,
                   help=f"needs_more_context band threshold (default: {DEFAULT_SUSPICIOUS_THRESHOLD})")
    p.add_argument("--determinism-delta", type=float, default=DEFAULT_DELTA,
                   help=f"Δscore considered stable (default: {DEFAULT_DELTA})")
    args = p.parse_args()

    db_dir = args.db_dir.resolve()
    rows = db.fetch_run_results(db_dir, run_id=args.run_id)
    if not rows:
        scope = f" for run_id={args.run_id}" if args.run_id else ""
        raise SystemExit(f"No result received{scope}. Is the validator running?")

    print(section_summary(rows, db_dir, args.run_id))
    print(section_determinism(rows, args.determinism_delta))
    print(section_distribution(rows))
    print(section_justness(rows, args.suspicious_threshold, args.threshold))


if __name__ == "__main__":
    main()
