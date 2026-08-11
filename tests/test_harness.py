# -*- coding: utf-8 -*-
# Tests for the pure half of pisces_sff/_harness.py.
#
# Two invariants matter here and both are silent when broken:
#
#   1. The environment key is the environment's identity. Two models with the
#      same dependencies must share one environment (so the YAML is proven by
#      being used, not merely declared), and any change to a dependency must
#      fork a new one. Cosmetic edits -- renaming the env, reordering keys --
#      must not fork, or every edit strands a stale environment.
#   2. Package records are derived from the environment specification rather
#      than restated by hand, so metadata.reproducibility cannot disagree with
#      the environment the export actually ran in. That derivation is this
#      parser.
#
# Design notes:
#   * _harness.py is loaded by file path rather than via `import pisces_sff`,
#     which would execute the package __init__ and pull in biosteam. _harness
#     itself imports only the standard library and PyYAML, so this works.

import importlib.util
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
HARNESS_PATH = REPO_ROOT / "pisces_sff" / "_harness.py"
CORN_ENV = (
    REPO_ROOT
    / "pisces_sff"
    / "models"
    / "biosteam_models"
    / "corn_dry_grind_ethanol"
    / "environment.yml"
)


def load_harness():
    spec = importlib.util.spec_from_file_location("pisces_sff_harness_under_test", HARNESS_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BASE_YAML = """\
name: sff-example
channels:
  - defaults
dependencies:
  - python=3.9.25
  - pip
  - pip:
      - numpy==1.26.4
      - biosteam @ git+https://github.com/BioSTEAMDevelopmentGroup/biosteam@e2d3942dd1076a4516efc91ae194f9e558428551
"""


class TestEnvironmentKey(unittest.TestCase):
    def setUp(self):
        self.harness = load_harness()

    def test_key_is_a_sha256_hex_digest(self):
        key = self.harness.environment_key(BASE_YAML)
        self.assertEqual(len(key), 64)
        self.assertTrue(all(c in "0123456789abcdef" for c in key))

    def test_key_is_deterministic(self):
        self.assertEqual(
            self.harness.environment_key(BASE_YAML),
            self.harness.environment_key(BASE_YAML),
        )

    def test_key_ignores_the_environment_name(self):
        renamed = BASE_YAML.replace("name: sff-example", "name: something-else")
        self.assertEqual(
            self.harness.environment_key(BASE_YAML),
            self.harness.environment_key(renamed),
        )

    def test_key_ignores_prefix(self):
        with_prefix = BASE_YAML + "prefix: C:\\\\envs\\\\sff-example\n"
        self.assertEqual(
            self.harness.environment_key(BASE_YAML),
            self.harness.environment_key(with_prefix),
        )

    def test_key_ignores_key_order(self):
        reordered = (
            "dependencies:\n"
            "  - python=3.9.25\n"
            "  - pip\n"
            "  - pip:\n"
            "      - numpy==1.26.4\n"
            "      - biosteam @ git+https://github.com/BioSTEAMDevelopmentGroup/biosteam"
            "@e2d3942dd1076a4516efc91ae194f9e558428551\n"
            "channels:\n"
            "  - defaults\n"
            "name: sff-example\n"
        )
        self.assertEqual(
            self.harness.environment_key(BASE_YAML),
            self.harness.environment_key(reordered),
        )

    def test_key_changes_when_a_pin_changes(self):
        bumped = BASE_YAML.replace("numpy==1.26.4", "numpy==1.26.5")
        self.assertNotEqual(
            self.harness.environment_key(BASE_YAML),
            self.harness.environment_key(bumped),
        )

    def test_key_changes_when_a_commit_changes(self):
        bumped = BASE_YAML.replace(
            "e2d3942dd1076a4516efc91ae194f9e558428551", "0" * 40
        )
        self.assertNotEqual(
            self.harness.environment_key(BASE_YAML),
            self.harness.environment_key(bumped),
        )

    def test_environment_name_is_prefixed_and_short(self):
        name = self.harness.environment_name(BASE_YAML)
        self.assertTrue(name.startswith(self.harness.ENV_NAME_PREFIX))
        self.assertEqual(name, "sff-" + self.harness.environment_key(BASE_YAML)[:12])


class TestPipRequirementParsing(unittest.TestCase):
    def setUp(self):
        self.harness = load_harness()

    def test_version_pin(self):
        self.assertEqual(
            self.harness.parse_pip_requirement("numpy==1.26.4"),
            {"name": "numpy", "version": "1.26.4"},
        )

    def test_version_pin_tolerates_whitespace(self):
        self.assertEqual(
            self.harness.parse_pip_requirement("  numpy == 1.26.4  "),
            {"name": "numpy", "version": "1.26.4"},
        )

    def test_pep508_direct_reference(self):
        entry = (
            "biorefineries @ git+https://github.com/BioSTEAMDevelopmentGroup/"
            "Bioindustrial-Park@584232846c999986f108cbd14d53437cd06c8f3d"
        )
        self.assertEqual(
            self.harness.parse_pip_requirement(entry),
            {
                "name": "biorefineries",
                "url": "https://github.com/BioSTEAMDevelopmentGroup/Bioindustrial-Park",
                "commit": "584232846c999986f108cbd14d53437cd06c8f3d",
            },
        )

    def test_bare_git_url_falls_back_to_the_repository_name(self):
        entry = (
            "git+https://github.com/BioSTEAMDevelopmentGroup/biosteam"
            "@e2d3942dd1076a4516efc91ae194f9e558428551"
        )
        self.assertEqual(
            self.harness.parse_pip_requirement(entry),
            {
                "name": "biosteam",
                "url": "https://github.com/BioSTEAMDevelopmentGroup/biosteam",
                "commit": "e2d3942dd1076a4516efc91ae194f9e558428551",
            },
        )

    def test_egg_fragment_names_the_distribution(self):
        entry = (
            "git+https://github.com/BioSTEAMDevelopmentGroup/Bioindustrial-Park"
            "@584232846c999986f108cbd14d53437cd06c8f3d#egg=biorefineries"
        )
        record = self.harness.parse_pip_requirement(entry)
        self.assertEqual(record["name"], "biorefineries")
        self.assertNotIn("#", record["url"])

    def test_directives_are_ignored(self):
        self.assertIsNone(self.harness.parse_pip_requirement("--no-deps"))
        self.assertIsNone(self.harness.parse_pip_requirement("--index-url https://x"))

    def test_blank_lines_are_ignored(self):
        self.assertIsNone(self.harness.parse_pip_requirement("   "))


class TestPackageRecord(unittest.TestCase):
    def setUp(self):
        self.harness = load_harness()

    def test_finds_a_version_pinned_package(self):
        self.assertEqual(
            self.harness.package_record(BASE_YAML, "numpy"),
            {"name": "numpy", "version": "1.26.4"},
        )

    def test_finds_a_commit_pinned_package(self):
        record = self.harness.package_record(BASE_YAML, "biosteam")
        self.assertEqual(record["commit"], "e2d3942dd1076a4516efc91ae194f9e558428551")
        self.assertEqual(record["url"], "https://github.com/BioSTEAMDevelopmentGroup/biosteam")

    def test_branch_is_attached_when_given(self):
        record = self.harness.package_record(BASE_YAML, "biosteam", branch="master")
        self.assertEqual(record["branch"], "master")

    def test_name_matching_ignores_underscore_dash_and_case(self):
        yaml_text = BASE_YAML.replace("numpy==1.26.4", "Free_Properties==0.3.6")
        self.assertEqual(
            self.harness.package_record(yaml_text, "free-properties")["version"], "0.3.6"
        )

    def test_missing_package_raises(self):
        with self.assertRaises(ValueError):
            self.harness.package_record(BASE_YAML, "not-installed-anywhere")


class TestCornEnvironmentSpecification(unittest.TestCase):
    """The committed corn recipe must be readable by this parser."""

    def setUp(self):
        self.harness = load_harness()
        self.text = CORN_ENV.read_text(encoding="utf-8")

    def test_simulator_package_is_commit_pinned(self):
        record = self.harness.package_record(self.text, "biosteam")
        self.assertEqual(record["commit"], "e2d3942dd1076a4516efc91ae194f9e558428551")

    def test_flowsheet_model_package_is_commit_pinned(self):
        record = self.harness.package_record(self.text, "biorefineries")
        self.assertEqual(record["commit"], "584232846c999986f108cbd14d53437cd06c8f3d")
        self.assertEqual(
            record["url"],
            "https://github.com/BioSTEAMDevelopmentGroup/Bioindustrial-Park",
        )

    def test_every_pip_entry_is_parseable(self):
        # An unparseable entry would be installed but absent from the recorded
        # provenance -- silent, and exactly what this catches.
        for entry in self.harness.pip_requirements(self.text):
            with self.subTest(entry=entry):
                self.assertIsNotNone(self.harness.parse_pip_requirement(entry))

    def test_runner_dependencies_are_pinned(self):
        # The child process imports yaml (via _harness) and jsonschema (via
        # _validate); without these pins the export fails inside a freshly
        # created environment.
        for package in ("PyYAML", "jsonschema"):
            with self.subTest(package=package):
                self.assertIn("version", self.harness.package_record(self.text, package))


if __name__ == "__main__":
    unittest.main()
