# -*- coding: utf-8 -*-
# Tier 2: exports the corn dry-grind ethanol model in the *current* environment.
#
# Gated on SFF_TEST_BIOSTEAM=1 because it imports biosteam and runs a full
# simulation (minutes, and a numba compile on a cold cache). Run it with:
#
#     $env:SFF_TEST_BIOSTEAM = "1"
#     & "C:\Users\saran\anaconda3\envs\HP_2024\python.exe" -m pytest tests/test_export_corn_dry_grind_ethanol.py -q
#
# Gating uses unittest.skipUnless on an environment variable rather than a
# pytest marker so that `python -m unittest discover -s tests` keeps working and
# no pytest.ini is needed to silence unknown-marker warnings.
#
# Scope: STRUCTURAL assertions only. Run from a developer environment this
# exercises whatever biosteam and Bioindustrial-Park happen to be importable
# there, which is not what the recipe pins -- so numeric baselines belong in
# Tier 3 (tests/test_end_to_end_export.py), the only tier where the pins are
# what actually ran.
#
# This test must not run in parallel with any other simulating test; concurrent
# simulations corrupt the shared numba cache.

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = (
    REPO_ROOT
    / "pisces_sff"
    / "models"
    / "biosteam_models"
    / "corn_dry_grind_ethanol"
)
SCHEMA_PATH = REPO_ROOT / "pisces_sff" / "schema" / "sff_schema.json"

RUN_TIER_2 = os.environ.get("SFF_TEST_BIOSTEAM") == "1"


@unittest.skipUnless(RUN_TIER_2, "set SFF_TEST_BIOSTEAM=1 to run (imports biosteam)")
class TestCornDryGrindEthanolExport(unittest.TestCase):
    """One simulation, many assertions: setUpClass runs the export once."""

    @classmethod
    def setUpClass(cls):
        from pisces_sff import _export, _runner
        from pisces_sff._validate import validate_json_against_schema

        cls.validate = staticmethod(validate_json_against_schema)
        cls.tmp = tempfile.TemporaryDirectory()
        cls.output = Path(cls.tmp.name) / "corn_dry_grind_ethanol.json"

        # One simulation, exported at two schema versions: 0.0.7 exercises the
        # new quantity-unit shape (validated below); 0.0.6 guards byte-stability
        # of the historical inline shape. Both come from the same System, so the
        # guard adds no second simulation.
        module = _runner.load_model_module(MODEL_DIR)
        repro = _runner.build_reproducibility(MODEL_DIR, module)
        system, tea = module.load()
        kwargs = dict(module.EXPORT_KWARGS)
        _export.export_biosteam_flowsheet(
            system, str(cls.output), sff_version="0.0.7", tea=tea,
            reproducibility=repro, **kwargs)
        with cls.output.open("r", encoding="utf-8") as f:
            cls.flowsheet = json.load(f)

        cls.output_006 = Path(cls.tmp.name) / "corn_006.json"
        _export.export_biosteam_flowsheet(
            system, str(cls.output_006), sff_version="0.0.6", tea=tea,
            reproducibility=repro, **kwargs)
        with cls.output_006.open("r", encoding="utf-8") as f:
            cls.flowsheet_006 = json.load(f)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_output_validates_against_the_schema(self):
        is_valid, errors = self.validate(str(self.output), str(SCHEMA_PATH))
        self.assertTrue(is_valid, f"validation errors: {errors[:5]}")

    def test_sff_version_is_recorded(self):
        self.assertEqual(self.flowsheet["metadata"]["sff_version"], "0.0.7")

    def test_reproducibility_block_is_present(self):
        self.assertIn("reproducibility", self.flowsheet["metadata"])

    def test_embedded_environment_matches_the_committed_file(self):
        # The embedded hash is what lets a consumer detect drift between the
        # JSON they hold and the recipe in the repository; if the runner ever
        # embeds one file's text with another's digest, this catches it.
        block = self.flowsheet["metadata"]["reproducibility"]["environment"]
        data = (MODEL_DIR / "environment.yml").read_bytes()
        self.assertEqual(block["sha256"], hashlib.sha256(data).hexdigest())
        self.assertEqual(block["content"], data.decode("utf-8"))
        self.assertEqual(block["filename"], "environment.yml")

    def test_embedded_load_script_matches_the_committed_file(self):
        block = self.flowsheet["metadata"]["reproducibility"]["load_script"]
        data = (MODEL_DIR / "load.py").read_bytes()
        self.assertEqual(block["sha256"], hashlib.sha256(data).hexdigest())
        self.assertEqual(block["content"], data.decode("utf-8"))
        self.assertEqual(block["entry_point"], "load")

    def test_package_pins_are_recorded(self):
        block = self.flowsheet["metadata"]["reproducibility"]
        self.assertEqual(
            block["simulator_package"]["commit"],
            "e2d3942dd1076a4516efc91ae194f9e558428551",
        )
        self.assertEqual(
            block["flowsheet_model_package"]["commit"],
            "584232846c999986f108cbd14d53437cd06c8f3d",
        )

    def test_resolved_block_records_the_runtime(self):
        resolved = self.flowsheet["metadata"]["reproducibility"]["resolved"]
        self.assertTrue(resolved["python_version"])
        self.assertTrue(resolved["platform"])
        self.assertEqual(len(resolved["env_key"]), 64)
        self.assertTrue(resolved["exported_at"].endswith("Z"))
        self.assertIn("biosteam", resolved["package_versions"])

    def test_feedstock_is_corn(self):
        feedstocks = {f["stream_id"] for f in self.flowsheet["metadata"]["feedstocks"]}
        self.assertIn("corn", feedstocks)

    def test_ethanol_is_a_product(self):
        products = {p["stream_id"] for p in self.flowsheet["metadata"]["products"]}
        self.assertIn("ethanol", products)

    def test_microorganism_is_declared(self):
        hosts = self.flowsheet["metadata"]["microorganisms"]
        self.assertEqual(hosts[0]["name"], "Saccharomyces cerevisiae")

    def test_graph_is_non_empty(self):
        self.assertTrue(self.flowsheet["units"])
        self.assertTrue(self.flowsheet["streams"])
        self.assertTrue(self.flowsheet["chemicals"])

    def test_streams_reference_declared_units(self):
        # "None" is the exporter's sentinel for a system boundary.
        unit_ids = {u["id"] for u in self.flowsheet["units"]} | {"None"}
        for stream in self.flowsheet["streams"]:
            with self.subTest(stream=stream["id"]):
                self.assertIn(stream["source_unit_id"], unit_ids)
                self.assertIn(stream["sink_unit_id"], unit_ids)

    def test_quantity_units_global_is_present_and_biosteam_native(self):
        reg = self.flowsheet["quantity_units_global"]
        self.assertEqual(reg["temperature"]["quantity_units"], "K")
        self.assertEqual(reg["mass_flow"]["quantity_units"], "kg/hr")
        self.assertEqual(reg["price"]["quantity_units"], "USD/kg")

    def test_stream_scalars_are_bare_numbers(self):
        sp = self.flowsheet["streams"][0]["stream_properties"]
        self.assertIsInstance(sp["temperature"], (int, float))
        self.assertIsInstance(self.flowsheet["streams"][0]["price"], (int, float))

    def test_units_carry_design_result_quantity_units(self):
        self.assertTrue(
            all("quantity_units_for_design_results" in u for u in self.flowsheet["units"])
        )

    def test_heat_utilities_use_the_renamed_results_key(self):
        for hu in self.flowsheet["utilities"]["heat_utilities"]:
            self.assertIn("quantity_units_for_utility_results", hu)
            self.assertNotIn("units_for_utility_results", hu)

    def test_v0_0_6_export_keeps_the_inline_shape(self):
        # Byte-stability guard: the historical exporter must still emit inline
        # {"value","units"} scalars, the legacy results key, and NO registry.
        self.assertEqual(self.flowsheet_006["metadata"]["sff_version"], "0.0.6")
        self.assertNotIn("quantity_units_global", self.flowsheet_006)
        sp = self.flowsheet_006["streams"][0]["stream_properties"]
        self.assertIn("value", sp["temperature"])
        self.assertIn("units", sp["temperature"])
        for hu in self.flowsheet_006["utilities"]["heat_utilities"]:
            self.assertIn("units_for_utility_results", hu)
            self.assertNotIn("quantity_units_for_utility_results", hu)


if __name__ == "__main__":
    unittest.main()
