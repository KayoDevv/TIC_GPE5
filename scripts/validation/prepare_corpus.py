"""Prepare an analysis corpus from a folder of samples.

Picks N files from SOURCE and copies them into the corpus under <label>/.
By default the pick is random (seeded with --seed for reproducibility).

Scope filter (--in-scope): keep only PDFs the Linux sandbox can actually
observe — those with active-content markers via pdfid (/JS, /OpenAction,
/Launch, /EmbeddedFile, /AcroForm, /JBIG2Decode, /RichMedia, /XFA, /AA).
This discards out-of-scope samples (Windows-only trojans, fully inert PDFs)
that would never execute under our detonation and only muddy the metrics.
Requires pdfid → run inside the agent image (which ships it). PDF_VERSION comes
from makefiles/versions.mk:

    docker run --rm --user "$(id -u):$(id -g)" \
      -v "$PWD/scripts:/scripts:ro" -v "$HOME/datasets:/datasets:ro" \
      -v "$PWD/scripts/validation/real_corpus:/corpus:ro" -v "/tmp/out:/out" \
      ghcr.io/kayodevv/ubuntu-pdf-sandbox:$PDF_VERSION \
      python3 -m scripts.validation.prepare_corpus --source /datasets \
        --in-scope --dedup-against /corpus --count 400 --output /out

Usage (plain random pick):
    python3 -m scripts.validation.prepare_corpus --source /path/to/malware --count 500
"""

from __future__ import annotations

import argparse
import hashlib
import random
import re
import shutil
import subprocess
import sys
from pathlib import Path

# Active-content markers = what the Linux PDF sandbox can observe.
_ACTIVE_MARKERS = (
    "/JS", "/JavaScript", "/OpenAction", "/AA", "/Launch",
    "/EmbeddedFile", "/JBIG2Decode", "/RichMedia", "/XFA", "/AcroForm",
)
_PDFID_TIMEOUT_S = 30


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _is_in_scope(path: Path) -> bool:
    """True if pdfid reports at least one active-content marker.

    A timeout counts as in-scope: a PDF that hangs the parser is itself
    suspicious. Tool absence is fatal (the filter can't run).
    """
    try:
        r = subprocess.run(["pdfid", str(path)],
                           capture_output=True, text=True, timeout=_PDFID_TIMEOUT_S)
    except FileNotFoundError:
        raise SystemExit("ERROR: --in-scope needs pdfid (run inside the agent image).")
    except subprocess.TimeoutExpired:
        return True
    out = r.stdout + r.stderr
    return any(
        (m := re.search(rf"^\s*{re.escape(kw)}\s+([0-9]+)", out, re.MULTILINE))
        and int(m.group(1)) > 0
        for kw in _ACTIVE_MARKERS
    )


def _existing_hashes(corpus: Path | None) -> set[str]:
    if not corpus or not corpus.exists():
        return set()
    return {_sha256(p) for p in corpus.rglob("*") if p.is_file()}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--source", required=True, type=Path, help="Source folder containing the samples")
    p.add_argument("--count", type=int, default=1000, help="Number of files to pick (default: 1000)")
    p.add_argument("--output", type=Path, default=Path("scripts/validation/real_corpus"), help="Target corpus folder")
    p.add_argument("--label", choices=["malicious", "benign", "unknown"], default="malicious",
                   help="Label sub-folder inside output (default: malicious)")
    p.add_argument("--seed", type=int, default=None, help="Random seed for reproducibility")
    p.add_argument("--in-scope", action="store_true",
                   help="Keep only PDFs with active content (pdfid); discard out-of-scope samples")
    p.add_argument("--dedup-against", type=Path, default=None,
                   help="Existing corpus root: skip any file already present (by sha256)")
    p.add_argument("--exclude-sha", action="append", default=[],
                   help="sha256 prefix to always skip (repeatable)")
    args = p.parse_args()

    source: Path = args.source.resolve()
    if not source.is_dir():
        raise SystemExit(f"ERROR: source folder not found: {source}")

    candidates = [f for f in source.rglob("*") if f.is_file()]
    if not candidates:
        raise SystemExit(f"ERROR: no file found in {source}")
    random.Random(args.seed).shuffle(candidates)

    known = _existing_hashes(args.dedup_against)
    dest = args.output.resolve() / args.label
    dest.mkdir(parents=True, exist_ok=True)

    kept = skipped_dup = skipped_scope = skipped_excl = skipped_unreadable = 0
    for f in candidates:
        if kept >= args.count:
            break
        try:
            sha = _sha256(f)
            if sha in known:
                skipped_dup += 1
                continue
            if any(sha.startswith(pfx) for pfx in args.exclude_sha):
                skipped_excl += 1
                continue
            if args.in_scope and not _is_in_scope(f):
                skipped_scope += 1
                continue
            target = dest / f.name
            if target.exists():
                target = dest / f"{f.stem}_{f.parent.name}{f.suffix}"
            shutil.copy2(f, target)
        except OSError:
            skipped_unreadable += 1
            continue
        kept += 1

    print(f"✓ {kept} files copied into {dest}")
    print(f"  skipped: scope={skipped_scope} dup={skipped_dup} "
          f"excluded={skipped_excl} unreadable={skipped_unreadable}")
    if kept < args.count:
        print(f"WARNING: only {kept}/{args.count} kept "
              f"(source short, or mostly out-of-scope with --in-scope).", file=sys.stderr)
    print(f"\nTo run the analysis:")
    print(f"  make sandbox-validate CORPUS={args.output.resolve()} RUN_ID=run_$(date +%Y%m%d) REPS=2")


if __name__ == "__main__":
    main()
