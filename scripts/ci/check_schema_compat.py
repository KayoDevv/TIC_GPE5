#!/usr/bin/env python3
"""BACKWARD_TRANSITIVE JSON Schema compatibility checker.

Checks that a NEW schema can still read data (messages) produced by the OLD
schema — the Confluent BACKWARD_TRANSITIVE guarantee for Kafka consumers.

Rules enforced:
  1. No new required field without a default
     → old messages won't contain it; the consumer would crash trying to
       deserialize a message that's missing a mandatory field.
  2. No type change on an existing property
     → old messages carry the old type; the consumer would fail to parse.
  3. No property removal when additionalProperties is false
     → old messages contain the removed field; the consumer would reject them.

All three rules are applied recursively through nested object properties and
array item schemas (e.g. iocs[].type, email_context.sender).

What is NOT enforced here:
  - $ref resolution, allOf/anyOf/oneOf (not used in this project's flat schemas)

Usage:
    python scripts/ci/check_schema_compat.py <old_schema.json> <new_schema.json>

Exit codes:
    0  — schemas are BACKWARD_TRANSITIVE compatible
    1  — breaking change detected (details printed to stdout)
    2  — usage / I/O error
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def _get_type(definition: dict[str, Any]) -> str | None:
    """Return the JSON Schema 'type' string if present, else None."""
    t = definition.get("type")
    if isinstance(t, list):
        # e.g. ["string", "null"] — normalise to a canonical form for comparison
        return json.dumps(sorted(t))
    return t  # type: ignore[return-value]


def check_backward_compat(
    old: dict[str, Any],
    new: dict[str, Any],
    path: str = "",
) -> list[str]:
    """Return a list of breaking-change descriptions (empty → compatible).

    Recurses into nested object properties and array item schemas.
    """
    errors: list[str] = []
    prefix = f"{path}." if path else ""

    old_required: set[str] = set(old.get("required", []))
    new_required: set[str] = set(new.get("required", []))
    old_props: dict[str, Any] = old.get("properties", {})
    new_props: dict[str, Any] = new.get("properties", {})
    strict_new = new.get("additionalProperties") is False

    # ── Rule 1: newly-required fields without a default ──────────────────────
    for field in sorted(new_required - old_required):
        new_def = new_props.get(field, {})
        if "default" not in new_def:
            errors.append(
                f"  [{prefix}{field}] is now REQUIRED but was optional before and has no "
                f"'default' — old messages won't carry this field"
            )

    # ── Rule 2 & 3: inspect each property that existed in the old schema ─────
    for field, old_def in old_props.items():
        field_path = f"{prefix}{field}"
        if field not in new_props:
            # Rule 3 — removal is breaking only if additionalProperties: false
            if strict_new:
                errors.append(
                    f"  [{field_path}] REMOVED from properties and the new schema has "
                    f"additionalProperties: false — old messages will be rejected"
                )
            continue

        new_def = new_props[field]
        old_type = _get_type(old_def)
        new_type = _get_type(new_def)

        # Rule 2 — type change
        if old_type and new_type and old_type != new_type:
            errors.append(
                f"  [{field_path}] TYPE changed: '{old_type}' → '{new_type}' — "
                f"old messages carry the old type and the consumer will fail to parse"
            )
            continue  # types differ — don't recurse into mismatched children

        # Recurse into nested object properties
        if old_type == "object" and "properties" in old_def and "properties" in new_def:
            errors.extend(check_backward_compat(old_def, new_def, path=field_path))

        # Recurse into array items when items defines an object schema
        if old_type == "array":
            old_items = old_def.get("items", {})
            new_items = new_def.get("items", {})
            if (
                isinstance(old_items, dict)
                and isinstance(new_items, dict)
                and old_items.get("type") == "object"
                and new_items.get("type") == "object"
            ):
                errors.extend(
                    check_backward_compat(old_items, new_items, path=f"{field_path}[]")
                )

    return errors


def main() -> int:
    if len(sys.argv) != 3:
        print(
            f"Usage: {sys.argv[0]} <old_schema.json> <new_schema.json>",
            file=sys.stderr,
        )
        return 2

    old_path, new_path = Path(sys.argv[1]), Path(sys.argv[2])

    try:
        old_schema: dict[str, Any] = json.loads(old_path.read_text(encoding="utf-8"))
        new_schema: dict[str, Any] = json.loads(new_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        print(f"File not found: {exc}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(f"JSON parse error: {exc}", file=sys.stderr)
        return 2

    errors = check_backward_compat(old_schema, new_schema)

    if errors:
        print("❌  BACKWARD_TRANSITIVE compatibility check FAILED:")
        for err in errors:
            print(err)
        print(
            "\nFix: only ADD new optional fields (with defaults). "
            "Never remove fields, never change types, never add required fields "
            "without a default."
        )
        return 1

    print("✅  Schema is BACKWARD_TRANSITIVE compatible.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
