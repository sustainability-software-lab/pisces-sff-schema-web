import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "check_release_consistency", ROOT / "scripts/check_release_consistency.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class ReleaseConsistencyTest(unittest.TestCase):
    def write_release(self, root: Path, schema_version: str | None) -> None:
        (root / "pisces_sff/schema").mkdir(parents=True)
        schema = {
            "$id": MODULE.expected_schema_id(schema_version or "missing"),
        }
        if schema_version is not None:
            schema["version"] = schema_version
        (root / "pisces_sff/schema/sff_schema.json").write_text(
            json.dumps(schema), encoding="utf-8"
        )

    def test_accepts_matching_package_schema_and_tag(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self.write_release(root, "0.0.10")

            self.assertEqual(MODULE.check_release_consistency(root, "v0.0.10"), "0.0.10")

    def test_rejects_missing_schema_version(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self.write_release(root, None)

            with self.assertRaisesRegex(ValueError, "schema must declare"):
                MODULE.check_release_consistency(root)

    def test_rejects_tag_skew(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self.write_release(root, "0.0.10")

            with self.assertRaisesRegex(ValueError, "release tag"):
                MODULE.check_release_consistency(root, "v0.0.11")

    def test_rejects_schema_id_skew(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self.write_release(root, "0.0.10")
            schema_path = root / "pisces_sff/schema/sff_schema.json"
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            schema["$id"] = "https://example.invalid/schema.json"
            schema_path.write_text(json.dumps(schema), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "schema \\$id"):
                MODULE.check_release_consistency(root)


if __name__ == "__main__":
    unittest.main()
