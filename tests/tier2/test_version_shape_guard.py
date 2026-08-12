# -*- coding: utf-8 -*-
# Tier 2: exporter version-dispatch guard. Exports one small REAL System at
# 0.0.6, 0.0.7, and 0.0.8 and asserts the scalar-shape, results-key, and
# required-metadata differences the schema versions require. This is about
# exporter version dispatch, not the corn model, so it needs no whole-model
# simulation -- which is why it lives in Tier 2 rather than Tier 3.
#
# All asserted shapes are verified from a real export run:
#   0.0.8 -> like 0.0.7, plus the now-required metadata.TEA_currency ("USD");
#            this is the only version whose export validates against the
#            committed (0.0.8) schema.
#   0.0.7 -> bare-number scalars, a quantity_units_global registry, and the
#            renamed quantity_units_for_utility_results key; omits TEA_currency.
#   0.0.6 -> inline {"value","units"} scalars, NO registry, and the legacy
#            units_for_utility_results key; omits TEA_currency.
#
# Gated on SFF_TEST_BIOSTEAM=1.

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _small_system import build_small_system_and_tea  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / "pisces_sff" / "schema" / "sff_schema.json"
RUN_TIER_2 = os.environ.get("SFF_TEST_BIOSTEAM") == "1"


@unittest.skipUnless(RUN_TIER_2, "set SFF_TEST_BIOSTEAM=1 to run (imports biosteam)")
class TestVersionShapeGuard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from pisces_sff import _export
        from pisces_sff._validate import validate_json_against_schema

        cls.validate = staticmethod(validate_json_against_schema)
        system, _H1, tea = build_small_system_and_tea()
        cls.tmp = tempfile.TemporaryDirectory()
        tmp = Path(cls.tmp.name)

        cls.path_007 = tmp / "small_007.json"
        _export.export_biosteam_flowsheet(
            system, str(cls.path_007), sff_version="0.0.7", tea=tea)
        cls.doc_007 = json.loads(cls.path_007.read_text(encoding="utf-8"))

        cls.path_006 = tmp / "small_006.json"
        _export.export_biosteam_flowsheet(
            system, str(cls.path_006), sff_version="0.0.6", tea=tea)
        cls.doc_006 = json.loads(cls.path_006.read_text(encoding="utf-8"))

        cls.path_008 = tmp / "small_008.json"
        _export.export_biosteam_flowsheet(
            system, str(cls.path_008), sff_version="0.0.8", tea=tea)
        cls.doc_008 = json.loads(cls.path_008.read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_0_0_7_uses_bare_number_scalars(self):
        self.assertEqual(self.doc_007["metadata"]["sff_version"], "0.0.7")
        sp = self.doc_007["streams"][0]["stream_properties"]
        self.assertIsInstance(sp["temperature"], (int, float))
        self.assertIsInstance(self.doc_007["streams"][0]["price"], (int, float))

    def test_0_0_7_has_the_global_registry(self):
        self.assertIn("quantity_units_global", self.doc_007)

    def test_0_0_7_units_carry_design_result_quantity_units(self):
        self.assertTrue(
            all("quantity_units_for_design_results" in u
                for u in self.doc_007["units"])
        )

    def test_0_0_7_heat_utilities_use_the_renamed_results_key(self):
        for hu in self.doc_007["utilities"]["heat_utilities"]:
            self.assertIn("quantity_units_for_utility_results", hu)
            self.assertNotIn("units_for_utility_results", hu)

    def test_0_0_6_uses_inline_scalars(self):
        self.assertEqual(self.doc_006["metadata"]["sff_version"], "0.0.6")
        sp = self.doc_006["streams"][0]["stream_properties"]
        self.assertIn("value", sp["temperature"])
        self.assertIn("units", sp["temperature"])

    def test_0_0_6_has_no_global_registry(self):
        self.assertNotIn("quantity_units_global", self.doc_006)

    def test_0_0_6_heat_utilities_use_the_legacy_results_key(self):
        for hu in self.doc_006["utilities"]["heat_utilities"]:
            self.assertIn("units_for_utility_results", hu)
            self.assertNotIn("quantity_units_for_utility_results", hu)

    def test_0_0_8_validates_and_emits_tea_currency(self):
        is_valid, errors = self.validate(str(self.path_008), str(SCHEMA_PATH))
        self.assertTrue(is_valid, f"validation errors: {errors[:5]}")
        self.assertEqual(self.doc_008["metadata"]["sff_version"], "0.0.8")
        self.assertEqual(self.doc_008["metadata"]["TEA_currency"], "USD")

    def test_pre_0_0_8_versions_omit_tea_currency(self):
        # The field is required only from 0.0.8; older exporters must stay
        # byte-stable and therefore not emit it.
        self.assertNotIn("TEA_currency", self.doc_007["metadata"])
        self.assertNotIn("TEA_currency", self.doc_006["metadata"])


if __name__ == "__main__":
    unittest.main()
