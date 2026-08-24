"""Fail the build when an image version disagrees with its Dockerfile header.

The `# ghcr-image: <name>:<version>` header of each Dockerfile listed in
.github/service-matrix.json is authoritative. Every other place that names a
version — manifests, makefiles/versions.mk, Python defaults, docs — must agree.
Run from the repository root.
"""

from __future__ import annotations

import json
import os
import re
import sys

MATRIX = ".github/service-matrix.json"
VERSIONS_MK = "makefiles/versions.mk"

HEADER_RE = re.compile(r"^#\s*ghcr-image:\s*(\S+)")
REFERENCE_RE = re.compile(r"ghcr\.io/[a-z0-9_-]+/([a-z0-9._-]+):([A-Za-z0-9._-]+)")
MK_ASSIGN_RE = re.compile(r"^([A-Z_]+_VERSION)\s*\?=\s*(\S+)")

SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__",
             ".pytest_cache", ".idea", ".remember", "maquette"}
BINARY_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".onnx",
                   ".duckdb", ".zip", ".gz", ".tar", ".woff", ".woff2",
                   ".pyc", ".so", ".bin", ".model", ".npy")
MOVING_TAGS = {"latest"}

MK_VARIABLE_BY_IMAGE = {
    "ubuntu-sandbox": "AGENT_VERSION",
    "ubuntu-pdf-sandbox": "PDF_VERSION",
    "charon-sandbox-consumer": "CONSUMER_VERSION",
    "charon-core-backend": "BACKEND_VERSION",
    "charon-ml-layer": "ML_VERSION",
    "charon-verdict-layer": "VERDICT_VERSION",
    "charon-llm-layer": "LLM_VERSION",
    "inetsim-sinkhole": "SINKHOLE_VERSION",
    "charon-website": "WEBSITE_VERSION",
}


def read_headers() -> dict[str, str]:
    headers: dict[str, str] = {}
    for entry in json.load(open(MATRIX, encoding="utf-8"))["include"]:
        dockerfile, image = entry["dockerfile"], entry["image"]
        if not os.path.isfile(dockerfile):
            continue
        for line in open(dockerfile, encoding="utf-8"):
            match = HEADER_RE.match(line)
            if not match:
                continue
            name, _, version = match.group(1).rpartition(":")
            if not version or name != image:
                sys.exit(f"::error file={dockerfile}::header '{match.group(1)}' "
                         f"does not name '{image}:<version>'")
            headers[image] = version
            break
        if image not in headers:
            sys.exit(f"::error file={dockerfile}::no 'ghcr-image: {image}:<version>' "
                     f"header: nothing would publish this image")
    return headers


def source_files() -> list[str]:
    found: list[str] = []
    for root, dirs, files in os.walk("."):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in files:
            if name.endswith(BINARY_SUFFIXES):
                continue
            found.append(os.path.join(root, name)[2:].replace(os.sep, "/"))
    return found


def check_references(headers: dict[str, str]) -> list[str]:
    problems: list[str] = []
    for path in source_files():
        try:
            lines = open(path, encoding="utf-8", errors="replace").readlines()
        except OSError:
            continue
        for number, line in enumerate(lines, 1):
            for image, version in REFERENCE_RE.findall(line):
                expected = headers.get(image)
                if expected is None or version in MOVING_TAGS or "$" in version:
                    continue
                if version != expected:
                    problems.append(f"::error file={path},line={number}::"
                                    f"{image}:{version} but the Dockerfile header "
                                    f"declares {expected}")
    return problems


def check_versions_mk(headers: dict[str, str]) -> list[str]:
    if not os.path.isfile(VERSIONS_MK):
        return [f"::error::{VERSIONS_MK} is missing"]
    declared: dict[str, str] = {}
    for line in open(VERSIONS_MK, encoding="utf-8"):
        match = MK_ASSIGN_RE.match(line)
        if match:
            declared[match.group(1)] = match.group(2)
    problems: list[str] = []
    for image, expected in headers.items():
        variable = MK_VARIABLE_BY_IMAGE.get(image)
        if variable is None:
            problems.append(f"::error file={VERSIONS_MK}::{image} has no version variable")
        elif declared.get(variable) != expected:
            problems.append(f"::error file={VERSIONS_MK}::{variable}={declared.get(variable)} "
                            f"but {image} declares {expected}")
    return problems


def check_kustomizations(headers: dict[str, str]) -> list[str]:
    problems: list[str] = []
    for path in source_files():
        if os.path.basename(path) != "kustomization.yaml":
            continue
        image = None
        for number, line in enumerate(open(path, encoding="utf-8", errors="replace"), 1):
            named = re.search(r"-\s*name:\s*ghcr\.io/[a-z0-9_-]+/([a-z0-9._-]+)\s*$", line)
            if named:
                image = named.group(1)
                continue
            tagged = re.search(r"newTag:\s*(\S+)\s*$", line)
            if tagged and image:
                expected = headers.get(image)
                if expected is not None and tagged.group(1) != expected:
                    problems.append(f"::error file={path},line={number}::"
                                    f"newTag {tagged.group(1)} for {image} but the "
                                    f"Dockerfile header declares {expected}")
                image = None
    return problems


def rewrite(headers: dict[str, str]) -> int:
    changed = 0
    for path in source_files():
        if path == VERSIONS_MK:
            continue
        try:
            lines = open(path, encoding="utf-8").readlines()
        except (OSError, UnicodeDecodeError):
            continue

        def swap(match: re.Match[str]) -> str:
            expected = headers.get(match.group(1))
            if expected is None or match.group(2) in MOVING_TAGS:
                return match.group(0)
            return f"ghcr.io/kayodevv/{match.group(1)}:{expected}"

        image, out = None, []
        for line in lines:
            named = re.search(r"-\s*name:\s*ghcr\.io/[a-z0-9_-]+/([a-z0-9._-]+)\s*$", line)
            tagged = re.search(r"^(\s*newTag:\s*)(\S+)(\s*)$", line)
            if named:
                image = named.group(1)
            elif tagged and image and image in headers:
                line = f"{tagged.group(1)}{headers[image]}{tagged.group(3)}"
                image = None
            else:
                line = re.sub(r"ghcr\.io/kayodevv/([a-z0-9._-]+):([A-Za-z0-9._-]+)", swap, line)
            out.append(line)

        if out != lines:
            open(path, "w", encoding="utf-8", newline="").writelines(out)
            print(f"  updated {path}")
            changed += 1

    lines = open(VERSIONS_MK, encoding="utf-8").readlines()
    by_variable = {MK_VARIABLE_BY_IMAGE[i]: v for i, v in headers.items()
                   if i in MK_VARIABLE_BY_IMAGE}
    out = []
    for line in lines:
        match = MK_ASSIGN_RE.match(line)
        if match and match.group(1) in by_variable:
            line = re.sub(r"\?=\s*\S+", f"?= {by_variable[match.group(1)]}", line)
        out.append(line)
    open(VERSIONS_MK, "w", encoding="utf-8", newline="").writelines(out)
    print(f"  updated {VERSIONS_MK}")
    return changed


def main() -> int:
    headers = read_headers()
    print(f"Dockerfile headers ({len(headers)}):")
    for image, version in sorted(headers.items()):
        print(f"  {image}: {version}")

    if "--write" in sys.argv:
        print("\nPropagating headers to every derived file:")
        rewrite(headers)
        print("\nDone. Commit the result.")
        return 0

    problems = (check_versions_mk(headers) + check_references(headers)
                + check_kustomizations(headers))
    if problems:
        print(f"\n{len(problems)} version(s) out of sync:")
        for problem in problems:
            print(problem)
        print("\nRun `make sync-versions` to propagate the headers.")
        return 1
    print("\nEvery version matches its Dockerfile header.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
