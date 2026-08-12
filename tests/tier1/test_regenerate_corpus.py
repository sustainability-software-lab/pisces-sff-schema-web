# -*- coding: utf-8 -*-
# Tier 1: unit-test the corpus-regeneration ORCHESTRATION without simulating.
# _regenerate_corpus.py performs no biosteam import at module top (export_model
# is imported lazily, only when no `export` callable is injected), so we load it
# by file path -- like tests/tier1/test_exceptions.py loads exceptions.py -- and
# inject a fake export to assert discovery + the per-model output-path loop.
# The REAL harness path is exercised in Tier 3 (tests/tier3).

import importlib.util
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = (
    Path(__file__).resolve().parents[2] / "pisces_sff" / "_regenerate_corpus.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location(
        "pisces_sff_regenerate_corpus_under_test", MODULE_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestIterModelDirs(unittest.TestCase):
    def setUp(self):
        self.m = load_module()

    def test_finds_the_corn_model(self):
        names = {d.name for d in self.m.iter_model_dirs()}
        self.assertIn("corn_dry_grind_ethanol", names)

    def test_every_discovered_dir_has_a_load_script(self):
        for directory in self.m.iter_model_dirs():
            with self.subTest(model=directory.name):
                self.assertTrue((directory / "load.py").is_file())


class TestRegenerateCorpusLoop(unittest.TestCase):
    def setUp(self):
        self.m = load_module()

    def test_calls_export_once_per_model_and_names_outputs(self):
        calls = []

        def fake_export(model_dir, output_path):
            calls.append((Path(model_dir), Path(output_path)))
            Path(output_path).write_text("{}", encoding="utf-8")
            return Path(output_path)

        model_names = {d.name for d in self.m.iter_model_dirs()}
        with tempfile.TemporaryDirectory() as tmp:
            written = self.m.regenerate_corpus(tmp, export=fake_export)
            self.assertEqual(len(written), len(model_names))
            self.assertEqual(len(calls), len(model_names))
            for path in written:
                self.assertEqual(path.suffix, ".json")
                self.assertIn(path.stem, model_names)
                self.assertTrue(path.is_file())


if __name__ == "__main__":
    unittest.main()
