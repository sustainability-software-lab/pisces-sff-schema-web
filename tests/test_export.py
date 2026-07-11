import importlib.util
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


def load_export_module():
    thermosteam = types.ModuleType("thermosteam")
    thermosteam.Reaction = type("Reaction", (), {})
    thermosteam.ReactionSet = type("ReactionSet", (), {})
    thermosteam.SeriesReaction = type("SeriesReaction", (), {})
    thermosteam.ParallelReaction = type("ParallelReaction", (), {})
    thermosteam.Chemical = type("Chemical", (), {})

    reaction_package = types.ModuleType("thermosteam.reaction")
    reaction_module = types.ModuleType("thermosteam.reaction._reaction")
    reaction_module.get_stoichiometric_string = lambda *_args, **_kwargs: ""

    biosteam = types.ModuleType("biosteam")
    biosteam.PowerUtility = type("PowerUtility", (), {})
    biosteam.System = type("System", (), {})
    biosteam.__version__ = "test"

    numpy = types.ModuleType("numpy")
    numpy.ndarray = type("ndarray", (), {})

    modules = {
        "numpy": numpy,
        "thermosteam": thermosteam,
        "thermosteam.reaction": reaction_package,
        "thermosteam.reaction._reaction": reaction_module,
        "biosteam": biosteam,
    }
    spec = importlib.util.spec_from_file_location("pisces_sff_export_test", ROOT / "pisces_sff/_export.py")
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, modules):
        spec.loader.exec_module(module)
    return module


class ExportVersionTest(unittest.TestCase):
    def test_v005_export_stamps_v005(self):
        export_module = load_export_module()
        chemical = SimpleNamespace(ID="Water", formula="H2O", CAS="7732-18-5", MW=18.015)
        stream = SimpleNamespace(
            ID="feed",
            source=None,
            sink=None,
            chemicals=[chemical],
            vle_chemicals=[chemical],
        )
        system = SimpleNamespace(
            flowsheet=SimpleNamespace(),
            units=[],
            streams=[stream],
            feeds=[],
            products=[],
            TEA=SimpleNamespace(duration=(2025, 2045)),
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "export.json"
            export_module.export_biosteam_flowsheet(system, output, sff_version="0.0.5")
            document = json.loads(output.read_text())

        self.assertEqual(document["metadata"]["sff_version"], "0.0.5")


if __name__ == "__main__":
    unittest.main()
