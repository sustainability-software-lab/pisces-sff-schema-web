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
    def write_release(self, root: Path, package_version: str, schema_version: str) -> None:
        (root / "pisces_sff/schema").mkdir(parents=True)
        (root / "pisces_sff/_version.py").write_text(
            f'CURRENT_SFF_VERSION = "{package_version}"\n', encoding="utf-8"
        )
        schema = {
            "$id": MODULE.expected_schema_id(schema_version),
            "version": schema_version,
        }
        (root / "pisces_sff/schema/sff_schema.json").write_text(
            json.dumps(schema), encoding="utf-8"
        )

    def test_accepts_matching_package_schema_and_tag(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self.write_release(root, "0.0.5", "0.0.5")

            self.assertEqual(MODULE.check_release_consistency(root, "v0.0.5"), "0.0.5")

    def test_rejects_schema_version_skew(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self.write_release(root, "0.0.5", "0.0.6")

            with self.assertRaisesRegex(ValueError, "schema version"):
                MODULE.check_release_consistency(root)

    def test_rejects_tag_skew(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self.write_release(root, "0.0.5", "0.0.5")

            with self.assertRaisesRegex(ValueError, "release tag"):
                MODULE.check_release_consistency(root, "v0.0.6")

    def test_rejects_schema_id_skew(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self.write_release(root, "0.0.5", "0.0.5")
            schema_path = root / "pisces_sff/schema/sff_schema.json"
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            schema["$id"] = "https://example.invalid/schema.json"
            schema_path.write_text(json.dumps(schema), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "schema \\$id"):
                MODULE.check_release_consistency(root)


if __name__ == "__main__":
    unittest.main()
