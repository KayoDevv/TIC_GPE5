"""Export a hash-pinned requirements.txt from a poetry.lock (main group)."""
from __future__ import annotations

import sys
import tomllib

NL = chr(10)
CONT = " \\" + NL + "    "


def main() -> None:
    lock_path, out_path = sys.argv[1], sys.argv[2]
    data = tomllib.load(open(lock_path, "rb"))

    out: list[str] = [
        "# AUTO-GENERATED from poetry.lock (main group) -- do not edit by hand.",
        "",
    ]
    count = 0
    for pkg in data["package"]:
        if "main" not in pkg.get("groups", []):
            continue
        if pkg.get("source", {}).get("type") == "directory":
            continue
        hashes = [
            f["hash"] for f in pkg.get("files", [])
            if f.get("hash", "").startswith("sha256:")
        ]
        if not hashes:
            continue
        body = CONT.join(f"--hash={h}" for h in hashes)
        spec = f"{pkg['name']}=={pkg['version']}"
        # poetry locks a per-group marker table when a package spans groups; the
        # main-group requirement only cares about main's marker (absent = always).
        marker = pkg.get("markers")
        if isinstance(marker, dict):
            marker = marker.get("main")
        if marker:
            spec += f" ; {marker}"
        out.append(spec + CONT + body)
        count += 1

    open(out_path, "w", encoding="utf-8", newline=NL).write(NL.join(out) + NL)
    print(f"wrote {out_path}: {count} pinned packages")


if __name__ == "__main__":
    main()
