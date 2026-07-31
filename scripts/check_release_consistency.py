#!/usr/bin/env python3
"""Verify that the package, schema, and optional release tag identify one SFF version."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


VERSION_RE = re.compile(r'^CURRENT_SFF_VERSION\s*=\s*["\']([^"\']+)["\']\s*$', re.MULTILINE)
REPOSITORY = "sustainability-software-lab/pisces-standard-flowsheet-format"


def expected_schema_id(version: str) -> str:
    return (
        "https://raw.githubusercontent.com/"
        f"{REPOSITORY}/v{version}/pisces_sff/schema/sff_schema.json"
    )


def read_package_version(root: Path) -> str:
    source = (root / "pisces_sff/_version.py").read_text(encoding="utf-8")
    match = VERSION_RE.search(source)
    if match is None:
        raise ValueError("pisces_sff/_version.py does not declare CURRENT_SFF_VERSION")
    return match.group(1)


def check_release_consistency(root: Path, tag: str | None = None) -> str:
    version = read_package_version(root)
    schema_path = root / "pisces_sff/schema/sff_schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    if schema.get("version") != version:
        raise ValueError(
            f"schema version {schema.get('version')!r} does not match package version {version!r}"
        )

    expected_id = expected_schema_id(version)
    if schema.get("$id") != expected_id:
        raise ValueError(f"schema $id must be {expected_id!r}, got {schema.get('$id')!r}")

    if tag is not None and tag != f"v{version}":
        raise ValueError(f"release tag {tag!r} does not match package version v{version}")

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
