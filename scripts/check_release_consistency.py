#!/usr/bin/env python3
"""Verify that the package, schema, and optional release tag identify one SFF version."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


REPOSITORY = "sustainability-software-lab/pisces-sff-schema-web"


def expected_schema_id(version: str) -> str:
    return (
        "https://raw.githubusercontent.com/"
        f"{REPOSITORY}/v{version}/pisces_sff/schema/sff_schema.json"
    )


def check_release_consistency(root: Path, tag: str | None = None) -> str:
    schema_path = root / "pisces_sff/schema/sff_schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    version = schema.get("version")
    if not isinstance(version, str) or not version:
        raise ValueError("schema must declare a non-empty string version")

    expected_id = expected_schema_id(version)
    if schema.get("$id") != expected_id:
        raise ValueError(f"schema $id must be {expected_id!r}, got {schema.get('$id')!r}")

    if tag is not None and tag != f"v{version}":
        raise ValueError(f"release tag {tag!r} does not match schema version v{version}")

    return version


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--tag", help="Git tag being validated, for example v0.0.5")
    args = parser.parse_args()
    version = check_release_consistency(args.root.resolve(), args.tag)
    print(f"release metadata is consistent for v{version}")


if __name__ == "__main__":
    main()
