"""Prepare an analysis corpus from a folder of samples.

Picks N random files from SOURCE and copies them into
scripts/validation/real_corpus/malicious/ (sub-folder created automatically).

Usage:
    python3 -m scripts.validation.prepare_corpus --source /path/to/malware
    python3 -m scripts.validation.prepare_corpus --source /path/to/malware --count 500
    python3 -m scripts.validation.prepare_corpus --source /path/to/malware --output my_corpus
"""

from __future__ import annotations

import argparse
import random
import shutil
from pathlib import Path


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--source", required=True, type=Path, help="Source folder containing the samples")
    p.add_argument("--count", type=int, default=1000, help="Number of files to pick (default: 1000)")
    p.add_argument("--output", type=Path, default=Path("scripts/validation/real_corpus"), help="Target corpus folder (default: scripts/validation/real_corpus)")
    p.add_argument("--label", choices=["malicious", "benign", "unknown"], default="malicious",
                   help="Label sub-folder inside output (default: malicious)")
    p.add_argument("--seed", type=int, default=None, help="Random seed for reproducibility")
    args = p.parse_args()

    source: Path = args.source.resolve()
    if not source.is_dir():
        raise SystemExit(f"ERROR: source folder not found: {source}")

    files = [f for f in source.rglob("*") if f.is_file()]
    if not files:
        raise SystemExit(f"ERROR: no file found in {source}")

    if args.seed is not None:
        random.seed(args.seed)

    count = min(args.count, len(files))
    if count < args.count:
        print(f"WARNING: only {len(files)} files available, {count} copied.")

    selected = random.sample(files, count)

    dest = args.output.resolve() / args.label
    dest.mkdir(parents=True, exist_ok=True)

    for f in selected:
        target = dest / f.name
        # Avoid name collisions
        if target.exists():
            target = dest / f"{f.stem}_{f.parent.name}{f.suffix}"
        shutil.copy2(f, target)

    print(f"✓ {count} files copied into {dest}")
    print(f"\nTo run the analysis:")
    print(f"  make sandbox-validate CORPUS={args.output.resolve()} RUN_ID=run_$(date +%Y%m%d) REPS=2")


if __name__ == "__main__":
    main()
