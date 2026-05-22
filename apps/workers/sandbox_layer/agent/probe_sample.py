#!/usr/bin/env python3
"""Harnais d'introspection des sondes statiques PDF — outil de diagnostic.

But : faire parler un sample. Au lieu de lire un anomaly_score agrégé, on
exécute CHAQUE sonde statique isolément sur le fichier et on imprime, par
sonde : son score, son flag `value`, et la liste COMPLÈTE de ses `evidence`
(field_path + value observée). C'est l'analyse bottom-up — on voit exactement
ce que chaque perception capte (ou rate) sur le fichier réel.

Réutilise les modules de production tels quels (aucune logique dupliquée) :
    hypotheses/pdf_static.py, stream_entropy.py, embedded_magic.py,
    pdf_uri.py, pdf_anomaly.py — tous exposent evaluate_static(Path).

L'agrégation reproduite est identique à run_pdf_analysis.py :
    static_score = MAX des 5 sondes ; contribution finale = static_score × 0.30
    (poids PDF_WEIGHTS["pdf_static_indicators"]).

Usage (dans l'image, où pdfid/qpdf existent) :
    python3 /opt/agent/probe_sample.py /chemin/sample.pdf [autre.pdf ...]
    python3 /opt/agent/probe_sample.py /corpus/malicious/      # tout un dossier

Exemples de lecture :
    - une sonde à score 0 avec [] evidence = elle ne voit rien dans ce fichier
    - contraster un FN (tout à 0) avec un TP (une sonde fire) = le gap exact
"""

from __future__ import annotations

import sys
from pathlib import Path

# Les modules hypothèses font `from models import ...` / `from hypotheses._types
# import ...` en supposant le dossier agent dans sys.path (cf. run_pdf_analysis.py:62).
sys.path.insert(0, str(Path(__file__).parent))

from hypotheses.pdf_static import evaluate_static as probe_pdfid          # noqa: E402
from hypotheses.stream_entropy import evaluate_static as probe_entropy    # noqa: E402
from hypotheses.embedded_magic import evaluate_static as probe_embedded   # noqa: E402
from hypotheses.pdf_uri import evaluate_static as probe_uri               # noqa: E402
from hypotheses.pdf_anomaly import evaluate_static as probe_anomaly       # noqa: E402

# Mêmes sondes, même ordre que la couche statique de run_pdf_analysis.py.
_PROBES: list[tuple[str, object]] = [
    ("pdfid",    probe_pdfid),
    ("entropy",  probe_entropy),
    ("embedded", probe_embedded),
    ("uri",      probe_uri),
    ("anomaly",  probe_anomaly),
]

# Poids de la couche statique dans l'anomaly_score (run_pdf_analysis.PDF_WEIGHTS).
_PDF_STATIC_WEIGHT = 0.30


def probe_one(pdf_path: Path) -> float:
    """Exécute les 5 sondes sur un PDF, imprime le détail, retourne le score combiné."""
    print(f"\n{'=' * 78}")
    print(f"=== {pdf_path.name}  ({pdf_path.stat().st_size} octets)")
    print(f"{'=' * 78}")

    scores: list[float] = []
    for name, fn in _PROBES:
        try:
            r = fn(pdf_path)
        except Exception as exc:  # diagnostic : une sonde qui plante ne tue pas le harnais
            print(f"  [{name:8}] ERREUR: {exc}")
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
        f"  → MAX combiné = {combined:.3f}  |  contribution anomaly_score "
        f"(×{_PDF_STATIC_WEIGHT}) = {contribution:.3f}"
        f"  |  seuil malicious 0.08 → {'TP' if contribution >= 0.08 else 'FN (statique seul)'}"
    )
    return combined


def _iter_pdfs(arg: str):
    p = Path(arg)
    if p.is_dir():
        yield from sorted(p.glob("*.pdf"))
    elif p.is_file():
        yield p
    else:
        print(f"  (ignoré, introuvable : {arg})", file=sys.stderr)


def tally_corpus(root: str) -> None:
    """Mode contraste : tally par règle benign vs malicious sur un corpus.

    Pour chaque règle (field_path d'evidence), compte sur combien de FICHIERS
    elle fire, par label. Une règle qui fire plus (en taux) sur benign que sur
    malicious est du BRUIT (source de FP) ; une qui ne fire jamais sur benign
    est DISCRIMINANTE. Permet de calibrer sans casser le recall.

    Usage : probe_sample.py --tally <corpus_root>   (root contient benign/ malicious/)
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
    print(f"\nContraste par règle  (benign N={nb}, malicious N={nm})")
    print(f"{'RÈGLE':46}{'benign':>9}{'malic':>8}   verdict")
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
            verdict = "DISCRIMINANT (0 benign)"
        elif bd > md:
            verdict = "← BRUIT (fire + sur benign)"
        elif bd > 0:
            verdict = "ambigu (fire sur les 2)"
        else:
            verdict = ""
        print(f"{key:46}{b:>9}{m:>8}   {md - bd:+.2f}  {verdict}")


def main() -> None:
    if len(sys.argv) >= 3 and sys.argv[1] == "--tally":
        tally_corpus(sys.argv[2])
        return

    if len(sys.argv) < 2:
        print("Usage:\n"
              "  probe_sample.py <pdf|dossier> [...]      # détail par sonde\n"
              "  probe_sample.py --tally <corpus_root>    # contraste benign vs malicious",
              file=sys.stderr)
        sys.exit(1)

    targets = [pdf for arg in sys.argv[1:] for pdf in _iter_pdfs(arg)]
    if not targets:
        print("Aucun PDF à analyser.", file=sys.stderr)
        sys.exit(1)

    for pdf in targets:
        probe_one(pdf)


if __name__ == "__main__":
    main()
