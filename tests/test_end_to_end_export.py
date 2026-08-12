# -*- coding: utf-8 -*-
# Tier 3: the full harness, including conda environment creation.
#
# Gated on SFF_TEST_E2E=1 because it builds a conda environment from scratch on
# a cache miss (tens of minutes) and then simulates. Run it with:
#
#     $env:SFF_TEST_E2E = "1"
#     & "C:\Users\saran\anaconda3\envs\HP_2024\python.exe" -m pytest tests/test_end_to_end_export.py -q
#
# This is the ONLY tier in which the recipe's pins are what actually ran -- the
# export happens inside the environment environment.yml describes, not in the
# developer's environment -- and therefore the only tier permitted to assert
# numeric baselines. Those baselines are recorded from the first successful run
# (see the plan, Task 6 Step 5); they are measurements, not targets.
#
# Must not run in parallel with any other simulating test: concurrent
# simulations corrupt the shared numba cache. The harness lock enforces this.

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
BASELINE_PATH = REPO_ROOT / "tests" / "baselines" / "corn_dry_grind_ethanol.json"

#: Relative tolerance for numeric baselines. Loose enough to absorb BLAS/LAPACK
#: and platform differences between machines running identical pins, tight
#: enough that a genuine model change fails.
RTOL = 1e-4

RUN_TIER_3 = os.environ.get("SFF_TEST_E2E") == "1"


@unittest.skipUnless(RUN_TIER_3, "set SFF_TEST_E2E=1 to run (creates a conda environment)")
class TestEndToEndExport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from pisces_sff import export_model
        from pisces_sff._validate import validate_json_against_schema

        cls.validate = staticmethod(validate_json_against_schema)
        cls.tmp = tempfile.TemporaryDirectory()
        cls.output = Path(cls.tmp.name) / "corn_dry_grind_ethanol.json"
        export_model(MODEL_DIR, cls.output)
        with cls.output.open("r", encoding="utf-8") as f:
            cls.flowsheet = json.load(f)
        with BASELINE_PATH.open("r", encoding="utf-8") as f:
            cls.baseline = json.load(f)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def assertClose(self, actual, expected, label):
        self.assertAlmostEqual(
            actual, expected, delta=abs(expected) * RTOL,
            msg=f"{label}: got {actual!r}, baseline {expected!r}",
        )

    def test_output_validates_against_the_schema(self):
        is_valid, errors = self.validate(str(self.output), str(SCHEMA_PATH))
        self.assertTrue(is_valid, f"validation errors: {errors[:5]}")

    def test_export_ran_in_the_pinned_environment(self):
        # The whole point of the harness: the simulator that ran is the one the
        # recipe pins, not whatever happened to be importable.
        resolved = self.flowsheet["metadata"]["reproducibility"]["resolved"]
        self.assertEqual(
            resolved["package_versions"]["biosteam"],
            self.baseline["biosteam_version"],
        )
        self.assertEqual(resolved["env_key"], self.baseline["env_key"])

    def test_graph_size_matches_the_baseline(self):
        self.assertEqual(len(self.flowsheet["units"]), self.baseline["n_units"])
        self.assertEqual(len(self.flowsheet["streams"]), self.baseline["n_streams"])
        self.assertEqual(len(self.flowsheet["chemicals"]), self.baseline["n_chemicals"])

    def test_tea_year_matches_the_baseline(self):
        self.assertEqual(
            self.flowsheet["metadata"]["TEA_year"], self.baseline["TEA_year"]
        )

    def test_stream_mass_flows_match_the_baseline(self):
        flows = {s["id"]: s["stream_properties"]["total_mass_flow"]
                 for s in self.flowsheet["streams"]}
        for stream_id, expected in self.baseline["stream_mass_flows"].items():
            with self.subTest(stream=stream_id):
                self.assertIn(stream_id, flows)
                self.assertClose(flows[stream_id], expected, stream_id)

    def test_total_installed_cost_matches_the_baseline(self):
        total = sum(sum(u["installed_costs"].values()) for u in self.flowsheet["units"])
        self.assertClose(total, self.baseline["total_installed_cost"],
                         "total installed cost")


if __name__ == "__main__":
    unittest.main()
