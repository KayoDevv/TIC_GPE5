"""Prépare un corpus d'analyse à partir d'un dossier de samples.

Pioche N fichiers aléatoires dans SOURCE et les copie dans
scripts/validation/real_corpus/malicious/ (sous-dossier créé automatiquement).

Usage :
    python3 -m scripts.validation.prepare_corpus --source /chemin/vers/malwares
    python3 -m scripts.validation.prepare_corpus --source /chemin/vers/malwares --count 500
    python3 -m scripts.validation.prepare_corpus --source /chemin/vers/malwares --output mon_corpus
"""

from __future__ import annotations

import argparse
import random
import shutil
from pathlib import Path


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--source", required=True, type=Path, help="Dossier source contenant les samples")
    p.add_argument("--count", type=int, default=1000, help="Nombre de fichiers à piocher (défaut: 1000)")
    p.add_argument("--output", type=Path, default=Path("scripts/validation/real_corpus"), help="Dossier corpus cible (défaut: scripts/validation/real_corpus)")
    p.add_argument("--label", choices=["malicious", "benign", "unknown"], default="malicious",
                   help="Sous-dossier de label dans output (défaut: malicious)")
    p.add_argument("--seed", type=int, default=None, help="Seed aléatoire pour reproductibilité")
    args = p.parse_args()

    source: Path = args.source.resolve()
    if not source.is_dir():
        raise SystemExit(f"ERREUR: dossier source introuvable : {source}")

    files = [f for f in source.rglob("*") if f.is_file()]
    if not files:
        raise SystemExit(f"ERREUR: aucun fichier trouvé dans {source}")

    if args.seed is not None:
        random.seed(args.seed)

    count = min(args.count, len(files))
    if count < args.count:
        print(f"AVERTISSEMENT: seulement {len(files)} fichiers disponibles, {count} copiés.")

    selected = random.sample(files, count)

    dest = args.output.resolve() / args.label
    dest.mkdir(parents=True, exist_ok=True)

    for f in selected:
        target = dest / f.name
        # Évite les collisions de noms
        if target.exists():
            target = dest / f"{f.stem}_{f.parent.name}{f.suffix}"
        shutil.copy2(f, target)

    print(f"✓ {count} fichiers copiés dans {dest}")
    print(f"\nPour lancer l'analyse :")
    print(f"  make sandbox-validate CORPUS={args.output.resolve()} RUN_ID=run_$(date +%Y%m%d) REPS=2")


if __name__ == "__main__":
    main()
