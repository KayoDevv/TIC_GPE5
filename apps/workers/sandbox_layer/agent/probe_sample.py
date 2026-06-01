#!/usr/bin/env python3
"""Introspection harness for the PDF static probes — diagnostic tool.

Goal: make a sample talk. Instead of reading an aggregated anomaly_score, we run
EACH static probe in isolation on the file and print, per probe: its score, its
`value` flag, and the FULL list of its `evidence` (field_path + observed value).
This is bottom-up analysis — you see exactly what each perception catches (or
misses) on the real file.

Reuses the production modules as-is (no duplicated logic):
    hypotheses/pdf_static.py, stream_entropy.py, embedded_magic.py,
    pdf_uri.py, pdf_anomaly.py — all expose evaluate_static(Path).

The aggregation reproduced here is identical to run_pdf_analysis.py:
    static_score = MAX of the 5 probes ; final contribution = static_score × 0.30
    (weight PDF_WEIGHTS["pdf_static_indicators"]).

Usage (inside the image, where pdfid/qpdf exist):
    python3 /opt/agent/probe_sample.py /path/sample.pdf [other.pdf ...]
    python3 /opt/agent/probe_sample.py /corpus/malicious/      # a whole folder

How to read:
    - a probe with score 0 and [] evidence = it sees nothing in this file
    - contrast a FN (all 0) with a TP (one probe fires) = the exact gap
"""

from __future__ import annotations

import sys
from pathlib import Path

# The hypothesis modules do `from models import ...` / `from hypotheses._types
# import ...` assuming the agent dir is on sys.path (cf. run_pdf_analysis.py:62).
sys.path.insert(0, str(Path(__file__).parent))

from hypotheses.pdf_static import evaluate_static as probe_pdfid          # noqa: E402
from hypotheses.stream_entropy import evaluate_static as probe_entropy    # noqa: E402
from hypotheses.embedded_magic import evaluate_static as probe_embedded   # noqa: E402
from hypotheses.pdf_uri import evaluate_static as probe_uri               # noqa: E402
from hypotheses.pdf_anomaly import evaluate_static as probe_anomaly       # noqa: E402

# Same probes, same order as run_pdf_analysis.py's static layer.
_PROBES: list[tuple[str, object]] = [
    ("pdfid",    probe_pdfid),
    ("entropy",  probe_entropy),
    ("embedded", probe_embedded),
    ("uri",      probe_uri),
    ("anomaly",  probe_anomaly),
]

# Weight of the static layer in the anomaly_score (run_pdf_analysis.PDF_WEIGHTS).
_PDF_STATIC_WEIGHT = 0.30


def probe_one(pdf_path: Path) -> float:
    """Run the 5 probes on a PDF, print the detail, return the combined score."""
    print(f"\n{'=' * 78}")
    print(f"=== {pdf_path.name}  ({pdf_path.stat().st_size} bytes)")
    print(f"{'=' * 78}")

    scores: list[float] = []
    for name, fn in _PROBES:
        try:
            r = fn(pdf_path)
        except Exception as exc:  # diagnostic: a crashing probe must not kill the harness
            print(f"  [{name:8}] ERROR: {exc}")
            scores.append(0.0)
            continue

        scores.append(r.score)
        flag = "FIRE" if r.value else "    "
        print(f"  [{name:8}] score={r.score:.3f}  value={str(r.value):5}  {flag}")
        for ev in r.evidence:
            print(f"             └─ {ev.field_path} = {ev.value}")

    combined = max(scores) if scores else 0.0
    contribution = round(combined * _PDF_STATIC_WEIGHT, 3)
    print(f"  {'-' * 74}")
    print(
        f"  → combined MAX = {combined:.3f}  |  anomaly_score contribution "
        f"(×{_PDF_STATIC_WEIGHT}) = {contribution:.3f}"
        f"  |  malicious threshold 0.08 → {'TP' if contribution >= 0.08 else 'FN (static only)'}"
    )
    return combined


def _iter_pdfs(arg: str):
    p = Path(arg)
    if p.is_dir():
        yield from sorted(p.glob("*.pdf"))
    elif p.is_file():
        yield p
    else:
        print(f"  (skipped, not found: {arg})", file=sys.stderr)


def tally_corpus(root: str) -> None:
    """Contrast mode: per-rule benign vs malicious tally over a corpus.

    For each rule (evidence field_path), counts on how many FILES it fires, per
    label. A rule that fires more (by rate) on benign than on malicious is NOISE
    (a source of FP); one that never fires on benign is DISCRIMINATING. Lets you
    calibrate without breaking recall.

    Usage: probe_sample.py --tally <corpus_root>   (root contains benign/ malicious/)
    """
    from collections import defaultdict
    base = Path(root)
    tally: dict[str, dict[str, int]] = defaultdict(lambda: {"benign": 0, "malicious": 0})
    totals: dict[str, int] = {}

    for label in ("benign", "malicious"):
        d = base / label
        files = [f for f in sorted(d.glob("*")) if f.is_file()] if d.is_dir() else []
        totals[label] = len(files)
        for f in files:
            fired: set[str] = set()
            for _name, fn in _PROBES:
                try:
                    r = fn(f)
                except Exception:
                    continue
                if r.score <= 0:
                    continue
                for ev in r.evidence:
                    key = ev.field_path.replace(".rule[", ".").rstrip("]")
                    fired.add(key)
            for key in fired:
                tally[key][label] += 1

    nb, nm = totals.get("benign", 0), totals.get("malicious", 0)
    print(f"\nPer-rule contrast  (benign N={nb}, malicious N={nm})")
    print(f"{'RULE':46}{'benign':>9}{'malic':>8}   verdict")
    print("-" * 88)

    def disc(v: dict[str, int]) -> float:
        bd = v["benign"] / nb if nb else 0.0
        md = v["malicious"] / nm if nm else 0.0
        return md - bd

    for key, v in sorted(tally.items(), key=lambda kv: disc(kv[1]), reverse=True):
        b, m = v["benign"], v["malicious"]
        bd = b / nb if nb else 0.0
        md = m / nm if nm else 0.0
        if bd == 0 and m > 0:
            verdict = "DISCRIMINATING (0 benign)"
        elif bd > md:
            verdict = "← NOISE (fires more on benign)"
        elif bd > 0:
            verdict = "ambiguous (fires on both)"
        else:
            verdict = ""
        print(f"{key:46}{b:>9}{m:>8}   {md - bd:+.2f}  {verdict}")


def main() -> None:
    if len(sys.argv) >= 3 and sys.argv[1] == "--tally":
        tally_corpus(sys.argv[2])
        return

    if len(sys.argv) < 2:
        print("Usage:\n"
              "  probe_sample.py <pdf|folder> [...]       # per-probe detail\n"
              "  probe_sample.py --tally <corpus_root>    # benign vs malicious contrast",
              file=sys.stderr)
        sys.exit(1)

    targets = [pdf for arg in sys.argv[1:] for pdf in _iter_pdfs(arg)]
    if not targets:
        print("No PDF to analyze.", file=sys.stderr)
        sys.exit(1)

    for pdf in targets:
        probe_one(pdf)


if __name__ == "__main__":
    main()
