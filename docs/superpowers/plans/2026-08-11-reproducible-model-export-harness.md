# Reproducible Model Export Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make an SFF export reproducible by committing a pinned per-model recipe (conda `environment.yml` + `load.py`), running every export inside the environment that recipe builds, and embedding the recipe in the exported JSON under a new `metadata.reproducibility` block (SFF v0.0.6).

**Architecture:** A two-process harness. The *parent* (`pisces_sff/_harness.py`, runs in any environment) hashes the model's `environment.yml`, creates a conda environment named from that hash if it does not already exist, and launches a *child* (`pisces_sff/_runner.py`) with that environment's `python.exe` and a scrubbed process environment. The child imports the model's `load.py` by file path, calls `load()` to simulate, assembles the reproducibility payload, calls the existing versioned exporter once, and validates the result against the schema. Model recipes live under `pisces_sff/models/biosteam_models/<model_name>/`; dispatch is driven by a `SIMULATOR` declaration inside `load.py`, not by directory name, so a future `models/superpro_models/…` needs no runner change.

**Tech Stack:** Python 3.9, conda (environment provisioning), PyYAML (recipe canonicalization), `jsonschema` 4.25 Draft-07 (validation), BioSTEAM 2.46.1 / thermosteam 0.45.0 / `biorefineries` (simulation, child process only), stdlib `unittest`.

**Design spec:** [docs/superpowers/specs/2026-08-11-reproducible-model-export-harness-design.md](../specs/2026-08-11-reproducible-model-export-harness-design.md)

---

## Global Constraints

Every task's requirements implicitly include this section.

- **Python invocation.** `conda` is not on PATH in non-interactive shells and `conda activate` is unavailable. Always call the environment's interpreter directly: `& "C:\Users\saran\anaconda3\envs\HP_2024\python.exe"`. The bare command `python` hits a Windows Store stub and fails.
- **Never run two simulations concurrently.** Exports recompile a shared on-disk numba cache; two writers corrupt it. One simulation in flight at a time, never split across parallel tool calls or `run_in_background`. Do not use `pytest-xdist`.
- **Numba cache recovery** (if `ReferenceError: ... underlying object has vanished` appears at import): from `C:\Users\saran\Documents\Academia\repository_clones` and again from `C:\Users\saran\anaconda3\envs`, run `cmd /c "del *.PYC /s"`, `cmd /c "del *.nbc /s"`, `cmd /c "del *.nbi /s"`. Then re-run; the first simulation recompiles and is slower.
- **Never modify a non-cache file outside this repo.** `Bioindustrial-Park`, `biosteam`, `thermosteam` and the other sibling clones are read-only. Reading anywhere is fine.
- **Every new Python file starts with this exact header:**
  ```python
  # -*- coding: utf-8 -*-
  # Code to export flowsheets from multiple tools into a standardized JSON format.
  # Copyright (C) 2025-, Sarang S. Bhagwat <sarangbhagwat.developer@gmail.com>
  #
  # This module is under the MIT open-source license. See
  # https://github.com/sustainability-software-lab/pisces-standard-flowsheet-format/blob/main/LICENSE
  # for license details.
  ```
- **Module conventions.** Private modules define `__all__`; `pisces_sff/__init__.py` aggregates them. Use `#%%` cell delimiters for sections and NumPy-style docstrings on public functions.
- **Schema changes are additive and optional only.** Do not remove a property, add to a `required` list, narrow a type, or flip `additionalProperties` to `false`.
- **Do not regenerate any of the 18 committed flowsheets.** The new export is a new file.
- **Tests are stdlib `unittest`**, collected by pytest. Gate expensive tiers with `unittest.skipUnless` on environment variables, never pytest markers — `python -m unittest discover -s tests` must keep working.
- **Canonical validation before every commit** (both commands, read the output, never report an unobserved pass):
  ```bash
  & "C:\Users\saran\anaconda3\envs\HP_2024\python.exe" -c "import glob,os; from pisces_sff import validate_json_against_schema as v; s='pisces_sff/schema/sff_schema.json'; r=[(os.path.basename(f),)+v(f,s) for f in sorted(glob.glob('pisces_sff/exported_flowsheets/bioindustrial_park/*.json'))]; [print(n,'OK' if ok else ('FAIL '+str(e[:2]))) for n,ok,e in r]; print('failures:', sum(1 for _,ok,_ in r if not ok))"
  ```
  ```bash
  & "C:\Users\saran\anaconda3\envs\HP_2024\python.exe" -m pytest tests -q
  ```
  Pass criterion: `failures: 0` (over 18 flowsheets until Task 6, 19 after), all tests pass.
- **Commit to `dev`**, never `main`. Last line of every commit message:
  ```
  Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
  ```
- **`CLAUDE.md` and `.claude/` are gitignored** — edit `CLAUDE.md` when the plan says to, but never `git add` it.
- **Pinned commits** (exact, do not paraphrase):
  - biosteam `e2d3942dd1076a4516efc91ae194f9e558428551` at `https://github.com/BioSTEAMDevelopmentGroup/biosteam`
  - Bioindustrial-Park `584232846c999986f108cbd14d53437cd06c8f3d` (on `master`) at `https://github.com/BioSTEAMDevelopmentGroup/Bioindustrial-Park`

### Deviation from the spec: how `--no-deps` is applied

The spec (§7) puts `- --no-deps` as the first entry of the `pip:` block. **That does not work** and must not be implemented literally. Verified: `conda.env.installers.pip._pip_install_via_requirements` writes the `pip:` list verbatim into a temporary requirements file and runs `pip install -U -r <file>`, and pip's requirements-file parser supports only `index_url`, `extra_index_urls`, `find_links`, `no_index`, `constraints`, `requirements`, `editables`, `format_control`, `pre`, `prefer_binary`, `require_hashes`, `trusted_hosts`, `release_control`, `features_enabled` — `--no-deps` is not among them and pip errors on the unknown option.

**Implementation instead:** the harness sets `PIP_NO_DEPS=1` in the environment of the `conda env create` subprocess (pip reads `PIP_<OPTION>` environment variables for any option, including boolean flags). The `environment.yml` documents this in a comment so a human reproducing by hand knows to set it. The intent of D7 is unchanged: pip performs no dependency resolution, so every transitive dependency is pinned explicitly and BIP's `biosteam>=2.53.0` cannot replace the pinned biosteam build. Task 6 verifies empirically that the created environment holds biosteam 2.46.1.

---

## File Structure

**Created:**

| Path | Responsibility |
|---|---|
| `pisces_sff/_harness.py` | Parent side. Pure recipe helpers (canonicalize/hash YAML, parse pip requirements) + conda provisioning + locked child launch. |
| `pisces_sff/_runner.py` | Child side. Import `load.py`, simulate, build the reproducibility payload, call the exporter, validate. CLI via `python -m pisces_sff._runner`. |
| `pisces_sff/models/__init__.py` | Namespace marker; documents the models tree. |
| `pisces_sff/models/biosteam_models/__init__.py` | Namespace marker for BioSTEAM-sourced models. |
| `pisces_sff/models/biosteam_models/corn_dry_grind_ethanol/environment.yml` | Pinned conda recipe for the corn model. |
| `pisces_sff/models/biosteam_models/corn_dry_grind_ethanol/load.py` | `load()` returning `(system, tea)` plus the model's declarations. |
| `tests/test_schema_reproducibility.py` | Tier 1. Pins the `metadata.reproducibility` schema shape. |
| `tests/test_harness.py` | Tier 1. Pure harness helpers + orchestration with a fake conda. |
| `tests/test_models.py` | Tier 1. Every model directory satisfies the `load.py` contract (AST only, no import). |
| `tests/test_export_corn_dry_grind_ethanol.py` | Tier 2 (`SFF_TEST_BIOSTEAM=1`). Structural export assertions in the current env. |
| `tests/test_end_to_end_export.py` | Tier 3 (`SFF_TEST_E2E=1`). Full `export_model()` incl. env creation; numeric baselines. |
| `tests/baselines/corn_dry_grind_ethanol.json` | Recorded Tier 3 baseline values. |
| `pisces_sff/exported_flowsheets/bioindustrial_park/corn_dry_grind_ethanol.json` | The delivered export (19th corpus file). |

**Modified:**

| Path | Change |
|---|---|
| `pisces_sff/schema/sff_schema.json` | `version` → `0.0.6`; add `metadata.properties.reproducibility`. |
| `pisces_sff/_export.py` | Extract the v0.0.5 body into `_build_sff_dict` + `_write_sff_json`; add `export_biosteam_flowsheet_sff_0_0_6`. |
| `pisces_sff/__init__.py` | Re-export `_harness`. |
| `tests/test_version_sync.py` | Follow the metadata assignment into the shared builder. |
| `docs/full_schema.md` | Add v0.0.4 and v0.0.5 permalinks. |
| `docs/schema_reference.md` | Document `reproducibility`. |
| `CLAUDE.md` | Corpus count 18→19, test count, Tier 2/3 commands, baselines. |

---

## Task 1: Schema v0.0.6 and the v0.0.6 exporter

This is one atomic task because CLAUDE.md's version protocol requires all three parts in a single commit, and because `tests/test_version_sync.py::test_current_schema_version_has_an_exporter` fails between part 1 and part 2.

**Files:**
- Modify: `pisces_sff/schema/sff_schema.json:4` and `:110` (end of `metadata.properties`)
- Modify: `pisces_sff/_export.py:110-116`, `:283-296`, and append a new section
- Modify: `tests/test_version_sync.py:34-37`, `:160-185`
- Modify: `docs/full_schema.md`, `docs/schema_reference.md`
- Test: `tests/test_schema_reproducibility.py` (create)

**Interfaces:**
- Produces: `export_biosteam_flowsheet_sff_0_0_6(sys, filepath, tea=None, stoichiometry="dict", composition_units="both", microorganisms=None, reproducibility=None, sff_version='0.0.6')` — writes the SFF JSON, returns `None`. Reachable through the existing `export_biosteam_flowsheet(sys, filepath, sff_version='0.0.6', **kwargs)` dispatcher.
- Produces: `_build_sff_dict(sys, tea=None, stoichiometry="dict", composition_units="both", microorganisms=None, sff_version=None) -> dict` and `_write_sff_json(flowsheet_to_export, filepath) -> None` (module-private; used by both versioned exporters).
- Produces: schema property `metadata.reproducibility`, consumed by Tasks 5 and 6.

- [ ] **Step 1: Write the failing schema test**

Create `tests/test_schema_reproducibility.py`:

```python
# -*- coding: utf-8 -*-
# Tests for the v0.0.6 `metadata.reproducibility` schema definition.
#
# This block is what makes an exported flowsheet rebuildable from the JSON
# alone, so its shape is a public contract: PISCES reads `simulator_package`
# and `flowsheet_model_package` to index provenance without parsing the
# embedded YAML, and reads `environment.content` / `load_script.content` to
# reconstruct the recipe. The assertions below pin (a) that the block stays
# optional -- all 18 pre-existing flowsheets must keep validating -- and (b)
# that a package pin can never be ambiguous: it names either a VCS commit or a
# PyPI version, and a commit is meaningless without the repository URL.
#
# Design notes:
#   * As in tests/test_schema_microorganisms.py, this test uses `jsonschema`
#     directly rather than importing `pisces_sff`, which would drag in the
#     heavy biosteam/thermosteam stack for what is purely a schema check.

import json
import unittest
from pathlib import Path

from jsonschema import Draft7Validator

SCHEMA_PATH = (
    Path(__file__).resolve().parents[1]
    / "pisces_sff"
    / "schema"
    / "sff_schema.json"
)


def load_schema():
    with SCHEMA_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def reproducibility_subschema(schema):
    return schema["properties"]["metadata"]["properties"]["reproducibility"]


def minimal_block():
    """The smallest reproducibility block the schema accepts."""
    return {
        "environment": {
            "format": "conda-environment-yaml",
            "filename": "environment.yml",
            "sha256": "0" * 64,
            "content": "name: sff-test\n",
        },
        "load_script": {
            "format": "python",
            "filename": "load.py",
            "sha256": "1" * 64,
            "content": "def load():\n    pass\n",
        },
    }


class TestReproducibilityIsOptional(unittest.TestCase):
    """Additive by design: existing flowsheets must not become invalid."""

    def setUp(self):
        self.schema = load_schema()

    def test_block_is_declared(self):
        self.assertIn("reproducibility", self.schema["properties"]["metadata"]["properties"])

    def test_block_is_not_required(self):
        self.assertNotIn("reproducibility", self.schema["properties"]["metadata"]["required"])

    def test_block_is_an_object(self):
        # metadata declares additionalProperties: {"type": "string"}, so an
        # object-valued property is only expressible if declared explicitly.
        self.assertEqual(reproducibility_subschema(self.schema)["type"], "object")


class TestReproducibilityBlockValidation(unittest.TestCase):
    def setUp(self):
        self.validator = Draft7Validator(reproducibility_subschema(load_schema()))

    def assertValid(self, block):
        errors = sorted(self.validator.iter_errors(block), key=lambda e: list(e.path))
        self.assertEqual(errors, [], f"unexpected errors: {[e.message for e in errors]}")

    def assertInvalid(self, block):
        self.assertTrue(list(self.validator.iter_errors(block)))

    def test_minimal_block_is_valid(self):
        self.assertValid(minimal_block())

    def test_environment_is_required(self):
        block = minimal_block()
        del block["environment"]
        self.assertInvalid(block)

    def test_load_script_is_required(self):
        block = minimal_block()
        del block["load_script"]
        self.assertInvalid(block)

    def test_environment_content_is_required(self):
        # Without the verbatim text the JSON stops being self-sufficient.
        block = minimal_block()
        del block["environment"]["content"]
        self.assertInvalid(block)

    def test_commit_pinned_package_is_valid(self):
        block = minimal_block()
        block["simulator_package"] = {
            "name": "biosteam",
            "url": "https://github.com/BioSTEAMDevelopmentGroup/biosteam",
            "commit": "e2d3942dd1076a4516efc91ae194f9e558428551",
        }
        self.assertValid(block)

    def test_version_pinned_package_is_valid(self):
        block = minimal_block()
        block["flowsheet_model_package"] = {"name": "biorefineries", "version": "2.25.0"}
        self.assertValid(block)

    def test_package_without_commit_or_version_is_rejected(self):
        # A package record that pins nothing does not reproduce anything.
        block = minimal_block()
        block["simulator_package"] = {"name": "biosteam"}
        self.assertInvalid(block)

    def test_commit_without_url_is_rejected(self):
        # A bare SHA cannot be fetched; the repository must be named.
        block = minimal_block()
        block["simulator_package"] = {
            "name": "biosteam",
            "commit": "e2d3942dd1076a4516efc91ae194f9e558428551",
        }
        self.assertInvalid(block)

    def test_version_pinned_package_needs_no_url(self):
        block = minimal_block()
        block["simulator_package"] = {"name": "biosteam", "version": "2.46.1"}
        self.assertValid(block)

    def test_resolved_block_is_accepted(self):
        block = minimal_block()
        block["resolved"] = {
            "python_version": "3.9.25",
            "platform": "Windows-10-10.0.26200-SP0",
            "env_key": "a" * 64,
            "exported_at": "2026-08-11T12:00:00Z",
            "package_versions": {"biosteam": "2.46.1"},
        }
        self.assertValid(block)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run it to confirm it fails**

```bash
& "C:\Users\saran\anaconda3\envs\HP_2024\python.exe" -m pytest tests/test_schema_reproducibility.py -q
```

Expected: failures/errors — `KeyError: 'reproducibility'` from `reproducibility_subschema`, and `test_block_is_declared` failing.

- [ ] **Step 3: Add the schema block**

In `pisces_sff/schema/sff_schema.json`, change line 4 from `"version": "0.0.5",` to `"version": "0.0.6",`.

Then, inside `properties.metadata.properties`, insert the following **after** the `relevant_patents` property (which currently ends at line 110 with `},`) and before the closing brace of `properties` — i.e. add a comma after the `relevant_patents` block and paste this as the last property:

```json
        "reproducibility": {
          "type": "object",
          "description": "Everything needed to rebuild the environment and re-run the model that produced this flowsheet. Optional: flowsheets exported without a reproducibility recipe omit this block entirely.",
          "properties": {
            "environment": {
              "type": "object",
              "description": "The environment specification used to build the environment this flowsheet was exported from.",
              "properties": {
                "format": { "type": "string", "description": "Specification format; e.g., 'conda-environment-yaml'." },
                "filename": { "type": "string", "description": "File name of the environment specification." },
                "path": { "type": "string", "description": "Path of the source file relative to the repository root, when known." },
                "sha256": { "type": "string", "description": "SHA-256 hex digest of the verbatim file bytes." },
                "content": { "type": "string", "description": "Full text of the environment specification, embedded so this flowsheet is reproducible on its own." }
              },
              "required": ["format", "filename", "sha256", "content"]
            },
            "load_script": {
              "type": "object",
              "description": "The script that loads and simulates the model exported here.",
              "properties": {
                "format": { "type": "string", "description": "Script format; e.g., 'python'." },
                "filename": { "type": "string", "description": "File name of the load script." },
                "path": { "type": "string", "description": "Path of the source file relative to the repository root, when known." },
                "sha256": { "type": "string", "description": "SHA-256 hex digest of the verbatim file bytes." },
                "content": { "type": "string", "description": "Full text of the load script, embedded so this flowsheet is reproducible on its own." },
                "entry_point": { "type": "string", "description": "Name of the callable in the script that returns the simulated model; e.g., 'load'." }
              },
              "required": ["format", "filename", "sha256", "content"]
            },
            "simulator_package": {
              "type": "object",
              "description": "The process simulator package, pinned. Restates a pin that also appears in the embedded environment specification, so that provenance can be indexed and queried without parsing that text.",
              "properties": {
                "name": { "type": "string", "description": "Distribution name of the package." },
                "url": { "type": "string", "description": "Repository URL; required when 'commit' is given." },
                "commit": { "type": "string", "description": "Full VCS commit SHA the package was installed from." },
                "branch": { "type": "string", "description": "Branch the commit is reachable from, when known." },
                "version": { "type": "string", "description": "Release version, when installed from a package index." }
              },
              "required": ["name"],
              "anyOf": [
                { "required": ["commit"] },
                { "required": ["version"] }
              ],
              "allOf": [
                {
                  "if": { "required": ["commit"] },
                  "then": { "required": ["url"] }
                }
              ]
            },
            "flowsheet_model_package": {
              "type": "object",
              "description": "The package providing the flowsheet model itself, pinned. Restates a pin that also appears in the embedded environment specification, so that provenance can be indexed and queried without parsing that text.",
              "properties": {
                "name": { "type": "string", "description": "Distribution name of the package." },
                "url": { "type": "string", "description": "Repository URL; required when 'commit' is given." },
                "commit": { "type": "string", "description": "Full VCS commit SHA the package was installed from." },
                "branch": { "type": "string", "description": "Branch the commit is reachable from, when known." },
                "version": { "type": "string", "description": "Release version, when installed from a package index." }
              },
              "required": ["name"],
              "anyOf": [
                { "required": ["commit"] },
                { "required": ["version"] }
              ],
              "allOf": [
                {
                  "if": { "required": ["commit"] },
                  "then": { "required": ["url"] }
                }
              ]
            },
            "resolved": {
              "type": "object",
              "description": "Observed inside the environment at export time, distinguishing what actually ran from what was declared.",
              "properties": {
                "python_version": { "type": "string", "description": "Python version the export ran under." },
                "platform": { "type": "string", "description": "Platform identifier the export ran on." },
                "env_key": { "type": "string", "description": "SHA-256 hex digest of the canonicalized environment specification; identifies the environment the export ran in." },
                "exported_at": { "type": "string", "description": "UTC timestamp of the export, ISO-8601." },
                "package_versions": {
                  "type": "object",
                  "description": "Installed versions of relevant packages, keyed by distribution name.",
                  "additionalProperties": { "type": "string" }
                }
              }
            }
          },
          "required": ["environment", "load_script"]
        }
```

- [ ] **Step 4: Run the schema test to verify it passes**

```bash
& "C:\Users\saran\anaconda3\envs\HP_2024\python.exe" -m pytest tests/test_schema_reproducibility.py -q
```

Expected: PASS (13 tests).

- [ ] **Step 5: Confirm the version-sync test now fails**

```bash
& "C:\Users\saran\anaconda3\envs\HP_2024\python.exe" -m pytest tests/test_version_sync.py -q
```

Expected: FAIL on `test_current_schema_version_has_an_exporter` — "schema declares version '0.0.6' but no exporter named export_biosteam_flowsheet_sff_0_0_6 exists". This is the protocol working; Step 6 fixes it.

- [ ] **Step 6: Extract the shared builder in `_export.py`**

Replace the section header and signature at `pisces_sff/_export.py:110-116`:

```python
#%% Export function for SFF schema v0.0.5
def export_biosteam_flowsheet_sff_0_0_5(sys, filepath, tea=None,
                                        stoichiometry="dict", # must be one of (None, "vector", "dict")
                                        composition_units="both", # "mol%", "mass%", or "both"
                                        microorganisms=None, # optional list of microbial hosts; see metadata section below
                                        sff_version='0.0.5', # recorded as metadata['sff_version']; must match this function's name suffix
                                        ):
```

with:

```python
#%% Shared flowsheet assembly
# Every versioned exporter assembles the same core document; only the
# version-specific additions differ. Keeping the assembly here means adding a
# schema version costs one thin function rather than a copy of ~170 lines that
# would drift from this one. metadata['sff_version'] is assigned from the
# argument here and nowhere else -- see tests/test_version_sync.py.
def _build_sff_dict(sys, tea=None,
                    stoichiometry="dict", # must be one of (None, "vector", "dict")
                    composition_units="both", # "mol%", "mass%", or "both"
                    microorganisms=None, # optional list of microbial hosts; see metadata section below
                    sff_version=None, # recorded as metadata['sff_version']
                    ):
    """
    Assemble the SFF document for a simulated BioSTEAM system.

    Parameters
    ----------
    sys : biosteam.System
        A simulated system.
    tea : biosteam.TEA, optional
        TEA object to read cost assumptions from. Defaults to ``sys.TEA``.
    stoichiometry : str, optional
        One of ``None``, ``'vector'``, or ``'dict'``.
    composition_units : str, optional
        ``'mol%'``, ``'mass%'``, or ``'both'``.
    microorganisms : list, optional
        Microbial hosts; each entry is a string or a dict with a ``'name'`` key.
    sff_version : str
        Version recorded as ``metadata['sff_version']``.

    Returns
    -------
    dict
        The SFF document, ready to serialize.
    """
```

Then replace the tail at `pisces_sff/_export.py:283-296`:

```python
    # Export
    flowsheet_to_export = {"metadata": metadata,
                           "units": units,
                           "streams": streams,
                           "chemicals": chemicals,
                           "utilities": {"heat_utilities": heat_utilities,
                                          "power_utilities": power_utilities,
                                          "other_utilities": other_utilities},
                           }
    try:
        with open(filepath, "w") as json_file:
            json.dump(flowsheet_to_export, json_file, indent=4)
    except:
        breakpoint()
```

with:

```python
    return {"metadata": metadata,
            "units": units,
            "streams": streams,
            "chemicals": chemicals,
            "utilities": {"heat_utilities": heat_utilities,
                          "power_utilities": power_utilities,
                          "other_utilities": other_utilities},
            }


def _write_sff_json(flowsheet_to_export, filepath):
    """Serialize an assembled SFF document to `filepath` as indented JSON."""
    # NOTE: the bare `breakpoint()` here is pre-existing (known issue #2) and is
    # deliberately left in place; the harness runs exports with
    # PYTHONBREAKPOINT=0, which makes it a no-op rather than an unkillable hang
    # in a TTY-less subprocess.
    try:
        with open(filepath, "w") as json_file:
            json.dump(flowsheet_to_export, json_file, indent=4)
    except:
        breakpoint()


#%% Export function for SFF schema v0.0.5
def export_biosteam_flowsheet_sff_0_0_5(sys, filepath, tea=None,
                                        stoichiometry="dict", # must be one of (None, "vector", "dict")
                                        composition_units="both", # "mol%", "mass%", or "both"
                                        microorganisms=None, # optional list of microbial hosts
                                        sff_version='0.0.5', # must match this function's name suffix
                                        ):
    """Export a simulated BioSTEAM system against SFF schema v0.0.5."""
    flowsheet_to_export = _build_sff_dict(
        sys, tea=tea, stoichiometry=stoichiometry,
        composition_units=composition_units, microorganisms=microorganisms,
        sff_version=sff_version,
    )
    _write_sff_json(flowsheet_to_export, filepath)


#%% Export function for SFF schema v0.0.6
def export_biosteam_flowsheet_sff_0_0_6(sys, filepath, tea=None,
                                        stoichiometry="dict", # must be one of (None, "vector", "dict")
                                        composition_units="both", # "mol%", "mass%", or "both"
                                        microorganisms=None, # optional list of microbial hosts
                                        reproducibility=None, # optional recipe block; see pisces_sff._runner
                                        sff_version='0.0.6', # must match this function's name suffix
                                        ):
    """
    Export a simulated BioSTEAM system against SFF schema v0.0.6.

    Parameters
    ----------
    sys : biosteam.System
        A simulated system to export.
    filepath : str
        Path to write the SFF JSON file to.
    tea : biosteam.TEA, optional
        TEA object to read cost assumptions from. Defaults to ``sys.TEA``.
    stoichiometry : str, optional
        One of ``None``, ``'vector'``, or ``'dict'``.
    composition_units : str, optional
        ``'mol%'``, ``'mass%'``, or ``'both'``.
    microorganisms : list, optional
        Microbial hosts; each entry is a string or a dict with a ``'name'`` key.
    reproducibility : dict, optional
        Recipe block written to ``metadata['reproducibility']``: the environment
        specification, load script, pinned packages, and resolved runtime facts.
        Built by :func:`pisces_sff._runner.build_reproducibility`. Omitted
        entirely when falsy, so hand exports still validate -- the schema marks
        the block optional.
    sff_version : str, optional
        Version recorded as ``metadata['sff_version']``.
    """
    flowsheet_to_export = _build_sff_dict(
        sys, tea=tea, stoichiometry=stoichiometry,
        composition_units=composition_units, microorganisms=microorganisms,
        sff_version=sff_version,
    )
    if reproducibility:
        flowsheet_to_export['metadata']['reproducibility'] = reproducibility
    _write_sff_json(flowsheet_to_export, filepath)
```

- [ ] **Step 7: Follow the metadata assignment in `test_version_sync.py`**

`test_no_exporter_hardcodes_a_version_into_metadata` walks each exporter function for `metadata['sff_version'] = ...`. After Step 6 that assignment lives in `_build_sff_dict`, so the test would pass vacuously. Point it at the builder instead.

In `tests/test_version_sync.py`, after the `EXPORTER_PREFIX` constant (line 37), add:

```python
# The versioned exporters delegate document assembly to this shared builder,
# which is where metadata['sff_version'] is assigned. Named here so the
# "no hardcoded version" check below follows the assignment instead of passing
# vacuously once the exporters became thin wrappers.
BUILDER_NAME = "_build_sff_dict"
```

After the `versioned_exporters()` helper (line 67), add:

```python
def metadata_writers():
    """Map name -> ast.FunctionDef for every function that may build metadata."""
    writers = {
        f"{EXPORTER_PREFIX}{v.replace('.', '_')}": node
        for v, node in versioned_exporters().items()
    }
    for node in parse(EXPORT_PATH).body:
        if isinstance(node, ast.FunctionDef) and node.name == BUILDER_NAME:
            writers[BUILDER_NAME] = node
    return writers
```

Replace the body of `test_no_exporter_hardcodes_a_version_into_metadata` (lines 160-185) with:

```python
    def test_shared_builder_exists(self):
        # If the builder is renamed or inlined, the check below silently stops
        # inspecting the code that actually assigns metadata['sff_version'].
        self.assertIn(BUILDER_NAME, metadata_writers())

    def test_no_exporter_hardcodes_a_version_into_metadata(self):
        # metadata['sff_version'] must come from the sff_version parameter.
        found = 0
        for name, node in metadata_writers().items():
            for sub in ast.walk(node):
                if not (isinstance(sub, ast.Assign) and len(sub.targets) == 1):
                    continue
                target = sub.targets[0]
                if not isinstance(target, ast.Subscript):
                    continue
                if not (
                    isinstance(target.value, ast.Name)
                    and target.value.id == "metadata"
                ):
                    continue
                key = getattr(target.slice, "value", target.slice)
                key = key.value if isinstance(key, ast.Constant) else None
                if key != "sff_version":
                    continue
                found += 1
                with self.subTest(function=name):
                    self.assertIsInstance(
                        sub.value,
                        ast.Name,
                        "metadata['sff_version'] must be assigned from the "
                        "sff_version argument, not a literal",
                    )
                    self.assertEqual(sub.value.id, "sff_version")
        self.assertEqual(
            found, 1, "metadata['sff_version'] must be assigned in exactly one place"
        )
```

- [ ] **Step 8: Run the full test suite**

```bash
& "C:\Users\saran\anaconda3\envs\HP_2024\python.exe" -m pytest tests -q
```

Expected: PASS. `test_current_schema_version_has_an_exporter` now finds `0.0.6`, and `test_each_exporter_defaults_to_the_version_in_its_name` checks both `0.0.5` and `0.0.6`.

- [ ] **Step 9: Confirm both exporters are dispatchable**

```bash
& "C:\Users\saran\anaconda3\envs\HP_2024\python.exe" -c "from pisces_sff import available_sff_versions; from pisces_sff._export import get_versioned_exporter; print(available_sff_versions()); print(get_versioned_exporter('0.0.6').__name__)"
```

Expected output:
```
['0.0.5', '0.0.6']
export_biosteam_flowsheet_sff_0_0_6
```

- [ ] **Step 10: Add the previous-version permalinks**

Get the SHA of the commit that still declares `0.0.5` (this is `HEAD` before the bump commit exists):

```bash
git rev-parse HEAD
```

In `docs/full_schema.md`, replace the "Previous versions" list with the following, substituting the SHA printed above for `<HEAD_SHA>`. The v0.0.4 entry uses `71495fe6776c9b06f675b7a1ab7410bbbe2c1ac5`, the last commit whose `sff_schema.json` declared `0.0.4` — it was omitted when 0.0.4 was superseded, and is added here to close that gap.

```markdown
## Previous versions

* [v0.0.5](https://github.com/sustainability-software-lab/pisces-standard-flowsheet-format/blob/<HEAD_SHA>/pisces_sff/schema/sff_schema.json)
* [v0.0.4](https://github.com/sustainability-software-lab/pisces-standard-flowsheet-format/blob/71495fe6776c9b06f675b7a1ab7410bbbe2c1ac5/pisces_sff/schema/sff_schema.json)
* [v0.0.3](https://github.com/sustainability-software-lab/pisces-standard-flowsheet-format/blob/cb6c27daa49f83a3cd263521df69d37635770891/pisces_sff/schema/schema_v_0.0.3.json)
* [v0.0.2](https://github.com/sustainability-software-lab/pisces-standard-flowsheet-format/blob/cb6c27daa49f83a3cd263521df69d37635770891/pisces_sff/schema/schema_v_0.0.2.json)
* [v0.0.1](https://github.com/sustainability-software-lab/pisces-standard-flowsheet-format/blob/cb6c27daa49f83a3cd263521df69d37635770891/pisces_sff/schema/schema_v_0.0.1.json)
```

- [ ] **Step 11: Document the block in the schema reference**

In `docs/schema_reference.md`, in the Metadata bullet list, add after the `flowsheet_designers` bullet (line 29):

```markdown
- **reproducibility**: Everything needed to rebuild the environment and re-run the model that produced this flowsheet: the full text and SHA-256 of the environment specification (`environment`) and load script (`load_script`), the pinned `simulator_package` and `flowsheet_model_package` (each identified by a VCS `commit` + `url`, or by a released `version`), and a `resolved` block recording the Python version, platform, environment key, timestamp, and installed package versions observed at export time. Optional — flowsheets exported without a recipe omit it.
```

- [ ] **Step 12: Run canonical validation**

```bash
& "C:\Users\saran\anaconda3\envs\HP_2024\python.exe" -c "import glob,os; from pisces_sff import validate_json_against_schema as v; s='pisces_sff/schema/sff_schema.json'; r=[(os.path.basename(f),)+v(f,s) for f in sorted(glob.glob('pisces_sff/exported_flowsheets/bioindustrial_park/*.json'))]; [print(n,'OK' if ok else ('FAIL '+str(e[:2]))) for n,ok,e in r]; print('failures:', sum(1 for _,ok,_ in r if not ok))"
```

Expected: 18 lines of `OK`, then `failures: 0`. Any failure means the schema edit was not purely additive — fix before committing.

- [ ] **Step 13: Build the docs strictly**

```bash
& "C:\Users\saran\anaconda3\envs\HP_2024\python.exe" -m mkdocs build --strict
```

Expected: exit 0. If `mkdocs` is not installed in `HP_2024`, skip this step and note it.

- [ ] **Step 14: Commit**

```bash
git add pisces_sff/schema/sff_schema.json pisces_sff/_export.py tests/test_schema_reproducibility.py tests/test_version_sync.py docs/full_schema.md docs/schema_reference.md
```

```bash
git commit -m "$(cat <<'EOF'
schema: add optional metadata.reproducibility block (v0.0.6)

Bumps the schema to 0.0.6 and adds an optional metadata.reproducibility
property carrying the environment specification, load script, pinned
simulator/flowsheet-model packages, and resolved runtime facts, so a
flowsheet can be rebuilt from the JSON alone.

Per the version protocol this also adds export_biosteam_flowsheet_sff_0_0_6
and a v0.0.5 permalink; the v0.0.4 permalink, skipped on the previous bump,
is added here too. Document assembly moves into a shared _build_sff_dict so
each new schema version costs a thin wrapper rather than a copy of the body;
test_version_sync follows metadata['sff_version'] into that builder.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: The corn model recipe

**Files:**
- Create: `pisces_sff/models/__init__.py`
- Create: `pisces_sff/models/biosteam_models/__init__.py`
- Create: `pisces_sff/models/biosteam_models/corn_dry_grind_ethanol/environment.yml`
- Create: `pisces_sff/models/biosteam_models/corn_dry_grind_ethanol/load.py`
- Test: `tests/test_models.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: the model directory contract, consumed by Tasks 3–6. Every model directory contains `environment.yml` and a `load.py` declaring module-level `SIMULATOR`, `SIMULATOR_PACKAGE`, `FLOWSHEET_MODEL_PACKAGE`, `MODEL_NAME`, `EXPORT_KWARGS` (dict), optionally `PACKAGE_BRANCHES` (dict mapping package name → branch), and a function `load()` returning `(system, tea)`.

- [ ] **Step 1: Write the failing contract test**

Create `tests/test_models.py`:

```python
# -*- coding: utf-8 -*-
# Tests the per-model recipe contract under pisces_sff/models/.
#
# The runner imports a model's load.py and reads module-level declarations off
# it (SIMULATOR selects the export entry point; SIMULATOR_PACKAGE and
# FLOWSHEET_MODEL_PACKAGE are resolved against the environment specification to
# build metadata.reproducibility). A model missing one of those declarations
# fails only at export time, minutes into a simulation -- these tests catch it
# in milliseconds instead, and they apply to every model directory, so a future
# model added by copy-paste is covered without editing this file.
#
# Design notes:
#   * load.py is inspected with `ast`, never imported: importing it would pull
#     in biosteam via `biorefineries`, which is the exact cost these Tier 1
#     tests exist to avoid.

import ast
import unittest
from pathlib import Path

MODELS_ROOT = Path(__file__).resolve().parents[1] / "pisces_sff" / "models"

REQUIRED_CONSTANTS = (
    "SIMULATOR",
    "SIMULATOR_PACKAGE",
    "FLOWSHEET_MODEL_PACKAGE",
    "MODEL_NAME",
    "EXPORT_KWARGS",
)


def model_dirs():
    """Every directory holding a load.py, at any depth under models/."""
    return sorted(p.parent for p in MODELS_ROOT.rglob("load.py"))


def module_constants(path):
    """Map name -> literal value for module-level assignments in a .py file."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    constants = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                try:
                    constants[target.id] = ast.literal_eval(node.value)
                except ValueError:
                    pass
    return constants


def module_functions(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}


class TestModelsTreeExists(unittest.TestCase):
    def test_at_least_one_model_is_present(self):
        self.assertTrue(model_dirs(), f"no model directories found under {MODELS_ROOT}")

    def test_corn_model_is_present(self):
        names = {d.name for d in model_dirs()}
        self.assertIn("corn_dry_grind_ethanol", names)

    def test_biosteam_models_are_grouped(self):
        # Simulator dispatch is by the SIMULATOR declaration, not by path, but
        # the tree is still grouped per simulator so a non-BioSTEAM model has an
        # obvious home.
        self.assertTrue((MODELS_ROOT / "biosteam_models").is_dir())


class TestModelRecipeContract(unittest.TestCase):
    def test_every_model_has_an_environment_spec(self):
        for directory in model_dirs():
            with self.subTest(model=directory.name):
                self.assertTrue((directory / "environment.yml").is_file())

    def test_every_model_declares_the_required_constants(self):
        for directory in model_dirs():
            constants = module_constants(directory / "load.py")
            for name in REQUIRED_CONSTANTS:
                with self.subTest(model=directory.name, constant=name):
                    self.assertIn(name, constants)

    def test_export_kwargs_is_a_dict(self):
        for directory in model_dirs():
            with self.subTest(model=directory.name):
                constants = module_constants(directory / "load.py")
                self.assertIsInstance(constants["EXPORT_KWARGS"], dict)

    def test_model_name_matches_its_directory(self):
        for directory in model_dirs():
            with self.subTest(model=directory.name):
                constants = module_constants(directory / "load.py")
                self.assertEqual(constants["MODEL_NAME"], directory.name)

    def test_every_model_defines_load(self):
        for directory in model_dirs():
            with self.subTest(model=directory.name):
                self.assertIn("load", module_functions(directory / "load.py"))

    def test_package_branches_is_a_dict_when_present(self):
        for directory in model_dirs():
            constants = module_constants(directory / "load.py")
            if "PACKAGE_BRANCHES" in constants:
                with self.subTest(model=directory.name):
                    self.assertIsInstance(constants["PACKAGE_BRANCHES"], dict)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run it to confirm it fails**

```bash
& "C:\Users\saran\anaconda3\envs\HP_2024\python.exe" -m pytest tests/test_models.py -q
```

Expected: FAIL — `test_at_least_one_model_is_present` reports no model directories (`MODELS_ROOT` does not exist yet, so `rglob` yields nothing).

- [ ] **Step 3: Create the package markers**

`pisces_sff/models/__init__.py`:

```python
# -*- coding: utf-8 -*-
# Code to export flowsheets from multiple tools into a standardized JSON format.
# Copyright (C) 2025-, Sarang S. Bhagwat <sarangbhagwat.developer@gmail.com>
#
# This module is under the MIT open-source license. See
# https://github.com/sustainability-software-lab/pisces-standard-flowsheet-format/blob/main/LICENSE
# for license details.

"""
Per-model export recipes.

Each model lives in its own directory holding an ``environment.yml`` (a pinned
environment specification) and a ``load.py`` (which loads and simulates the
model). :func:`pisces_sff.export_model` builds the environment from the former
and runs the latter inside it, so a recipe cannot claim pins it did not use.

Directories are grouped per source simulator (``biosteam_models/``, and others
as they are added), but that grouping is organizational only: the runner
dispatches on the ``SIMULATOR`` declaration inside each ``load.py``, so a new
simulator needs no change here.
"""

__all__ = ()
```

`pisces_sff/models/biosteam_models/__init__.py`:

```python
# -*- coding: utf-8 -*-
# Code to export flowsheets from multiple tools into a standardized JSON format.
# Copyright (C) 2025-, Sarang S. Bhagwat <sarangbhagwat.developer@gmail.com>
#
# This module is under the MIT open-source license. See
# https://github.com/sustainability-software-lab/pisces-standard-flowsheet-format/blob/main/LICENSE
# for license details.

"""Export recipes for models sourced from BioSTEAM systems."""

__all__ = ()
```

- [ ] **Step 4: Write the corn load script**

`pisces_sff/models/biosteam_models/corn_dry_grind_ethanol/load.py`:

```python
# -*- coding: utf-8 -*-
# Code to export flowsheets from multiple tools into a standardized JSON format.
# Copyright (C) 2025-, Sarang S. Bhagwat <sarangbhagwat.developer@gmail.com>
#
# This module is under the MIT open-source license. See
# https://github.com/sustainability-software-lab/pisces-standard-flowsheet-format/blob/main/LICENSE
# for license details.

"""
Conventional corn dry-grind ethanol biorefinery, from the Bioindustrial-Park
``biorefineries.corn`` module.

Run this file directly to load and simulate the model without the harness:
``python load.py``.
"""

#%% Model declarations

# Selects the export entry point: the runner resolves `export_<SIMULATOR>_flowsheet`
# in pisces_sff._export. Dispatch is by this value rather than by directory
# name, so a model from another simulator only changes this line.
SIMULATOR = 'biosteam'

# Distribution names, resolved against environment.yml's pip requirements to
# fill metadata.reproducibility.simulator_package / .flowsheet_model_package.
# Deriving the pins from the environment specification (instead of restating
# them here) is what keeps the two representations from disagreeing.
SIMULATOR_PACKAGE = 'biosteam'
FLOWSHEET_MODEL_PACKAGE = 'biorefineries'

# Branches the pinned commits are reachable from, where known. Advisory only --
# a branch is not a pin, and is recorded so a reader can locate the commit.
PACKAGE_BRANCHES = {'biorefineries': 'master'}

MODEL_NAME = 'corn_dry_grind_ethanol'

# Forwarded to the exporter. The dry-grind process ferments via simultaneous
# saccharification and fermentation (`biorefineries.corn.units.SSF`), whose
# reaction is Glucose -> 2 Ethanol + 2 CO2 alongside a Yeast growth reaction --
# hence the single yeast host. A BioSTEAM System carries no host identity, so
# this cannot be inferred and must be declared.
EXPORT_KWARGS = {
    'microorganisms': [{'name': 'Saccharomyces cerevisiae', 'label': 'ethanologen'}],
    'stoichiometry': 'dict',
}

#%% Loader


def load():
    """
    Load and simulate the corn dry-grind ethanol biorefinery.

    Returns
    -------
    (biosteam.System, biosteam.TEA)
        The simulated system and its TEA object. ``Biorefinery.__new__``
        simulates the system and solves for IRR, so the returned objects are
        ready to export with no further calls.
    """
    # Imported inside the function so that reading this module's declarations
    # (as the test suite does) does not pull in the biosteam stack.
    from biorefineries import corn
    biorefinery = corn.Biorefinery()
    return biorefinery.corn_sys, biorefinery.corn_tea


if __name__ == '__main__':
    system, tea = load()
    print(system)
    print(f'IRR: {tea.IRR}')
```

- [ ] **Step 5: Write the environment specification**

`pisces_sff/models/biosteam_models/corn_dry_grind_ethanol/environment.yml`:

```yaml
# Pinned environment for the corn dry-grind ethanol model.
#
# `pisces_sff.export_model` builds this environment and runs the export inside
# it, so these pins are what actually produced the exported flowsheet.
#
# Two things to know when reproducing this by hand:
#
#   1. Set PIP_NO_DEPS=1 before running `conda env create`. Bioindustrial-Park
#      declares `biosteam>=2.53.0`, which pip would otherwise honour by
#      replacing the pinned biosteam commit below with a newer PyPI build --
#      defeating the point of pinning. That declaration overstates the real
#      requirement: this model loads and simulates against biosteam 2.46.1.
#      (`--no-deps` cannot be written into the pip: block; pip's
#      requirements-file parser rejects it as an unknown option.)
#   2. Because dependency resolution is off, every transitive dependency is
#      listed explicitly below. Adding a package here is how a missing import
#      gets fixed -- there is no resolver to fall back on.
#
#   PowerShell:  $env:PIP_NO_DEPS = "1"; conda env create -f environment.yml
#   bash:        PIP_NO_DEPS=1 conda env create -f environment.yml
#
# `name` is ignored by the harness, which creates the environment as
# sff-<first 12 hex chars of the environment key>, and is excluded from that
# key so renaming this field does not fork the environment.
name: sff-corn-dry-grind-ethanol
channels:
  - defaults
dependencies:
  - python=3.9.25
  - pip
  - pip:
      # Simulator and flowsheet model, pinned to commits (PEP 508 direct
      # references, so the distribution name is stated rather than guessed
      # from the repository name -- Bioindustrial-Park installs as
      # `biorefineries`).
      - biosteam @ git+https://github.com/BioSTEAMDevelopmentGroup/biosteam@e2d3942dd1076a4516efc91ae194f9e558428551
      - biorefineries @ git+https://github.com/BioSTEAMDevelopmentGroup/Bioindustrial-Park@584232846c999986f108cbd14d53437cd06c8f3d
      # Thermodynamics and property packages
      - thermosteam==0.45.0
      - chemicals==1.2.0
      - thermo==0.2.27
      - fluids==1.0.26
      - flexsolve==0.5.7
      - free-properties==0.3.6
      - colorpalette==0.3.3
      # Numerics
      - numpy==1.26.4
      - scipy==1.13.1
      - pandas==2.2.2
      - numba==0.60.0
      - llvmlite==0.43.0
      # Plotting, units, IO
      - matplotlib==3.5.2
      - Pint==0.23
      - graphviz==0.20.3
      - xlrd==2.0.1
      - openpyxl==3.1.2
      - xlsxwriter==3.2.9
      # Used by the exporter and runner themselves
      - jsonschema==4.25.0
      - PyYAML==6.0.1
      # Declared by biosteam
      - ipython==8.15.0
      - chaospy==4.3.15
      # Declared by Bioindustrial-Park (SALib and seaborn are deliberately
      # excluded: BIP declares them, but neither is installed in the reference
      # HP_2024 environment that exports this model today, so neither is
      # required to load and simulate it.)
      - scikit-learn==1.6.1
```

> **Note for Task 6.** This pin list is a starting point observed in HP_2024, not a verified-complete one. Completing it is a defined loop, run in Task 6: build the environment, run the Tier 3 export, add any package named by a resulting `ModuleNotFoundError` pinned to its HP_2024 version, repeat until the export succeeds from a freshly created environment.

- [ ] **Step 6: Run the contract test to verify it passes**

```bash
& "C:\Users\saran\anaconda3\envs\HP_2024\python.exe" -m pytest tests/test_models.py -q
```

Expected: PASS (9 tests).

- [ ] **Step 7: Verify the YAML parses and its pins are readable**

```bash
& "C:\Users\saran\anaconda3\envs\HP_2024\python.exe" -c "import yaml; d=yaml.safe_load(open('pisces_sff/models/biosteam_models/corn_dry_grind_ethanol/environment.yml')); pips=[e for dep in d['dependencies'] if isinstance(dep,dict) for e in dep['pip']]; print(d['name']); print(len(pips),'pip entries'); print([p for p in pips if 'git+' in p])"
```

Expected: prints `sff-corn-dry-grind-ethanol`, the pip entry count, and the two `git+` entries with the full SHAs.

- [ ] **Step 8: Run the full suite and canonical validation**

```bash
& "C:\Users\saran\anaconda3\envs\HP_2024\python.exe" -m pytest tests -q
```

```bash
& "C:\Users\saran\anaconda3\envs\HP_2024\python.exe" -c "import glob,os; from pisces_sff import validate_json_against_schema as v; s='pisces_sff/schema/sff_schema.json'; r=[(os.path.basename(f),)+v(f,s) for f in sorted(glob.glob('pisces_sff/exported_flowsheets/bioindustrial_park/*.json'))]; print('failures:', sum(1 for _,ok,_ in r if not ok))"
```

Expected: all tests pass; `failures: 0`.

- [ ] **Step 9: Commit**

```bash
git add pisces_sff/models tests/test_models.py
```

```bash
git commit -m "$(cat <<'EOF'
models: add the corn dry-grind ethanol export recipe

Adds pisces_sff/models/, grouped per source simulator, holding one directory
per model with a pinned environment.yml and a load.py exposing load() ->
(system, tea). The corn dry-grind ethanol model is the first entry, pinning
biosteam e2d3942 and Bioindustrial-Park 5842328.

Dependency resolution is disabled when the environment is built (BIP's
biosteam>=2.53.0 would otherwise replace the pinned build), so every
transitive dependency is pinned explicitly.

tests/test_models.py enforces the recipe contract for every model directory
without importing biosteam.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Harness recipe helpers

The pure, environment-independent half of the parent process: turning an `environment.yml` into a stable environment key and into package records for the reproducibility block.

**Files:**
- Create: `pisces_sff/_harness.py` (helpers only; orchestration lands in Task 4)
- Test: `tests/test_harness.py`

**Interfaces:**
- Consumes: the model directory contract from Task 2.
- Produces, all importable from `pisces_sff._harness`:
  - `sha256_bytes(data: bytes) -> str`
  - `canonical_environment_text(text: str) -> str`
  - `environment_key(text: str) -> str` (64-char hex)
  - `environment_name(text: str) -> str` (`'sff-' + environment_key(text)[:12]`)
  - `pip_requirements(text: str) -> list[str]`
  - `parse_pip_requirement(entry: str) -> dict | None` — `{'name', 'version'}` or `{'name', 'url', 'commit'}`, `None` for directives and unparseable entries
  - `package_record(env_text: str, package_name: str, branch=None) -> dict` — raises `ValueError` when absent
  - `ENV_NAME_PREFIX = 'sff-'`, `REPO_ROOT: Path`

- [ ] **Step 1: Write the failing helper tests**

Create `tests/test_harness.py`:

```python
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
```

- [ ] **Step 2: Run it to confirm it fails**

```bash
& "C:\Users\saran\anaconda3\envs\HP_2024\python.exe" -m pytest tests/test_harness.py -q
```

Expected: every test errors — `FileNotFoundError` / `spec_from_file_location` returning `None` for the missing `_harness.py`.

- [ ] **Step 3: Write the helper half of `_harness.py`**

Create `pisces_sff/_harness.py`:

```python
# -*- coding: utf-8 -*-
# Code to export flowsheets from multiple tools into a standardized JSON format.
# Copyright (C) 2025-, Sarang S. Bhagwat <sarangbhagwat.developer@gmail.com>
#
# This module is under the MIT open-source license. See
# https://github.com/sustainability-software-lab/pisces-standard-flowsheet-format/blob/main/LICENSE
# for license details.

"""
Parent side of the reproducible export harness.

Reads a model's pinned environment specification, provisions the conda
environment it describes, and runs the export inside that environment via
:mod:`pisces_sff._runner`. Running in the provisioned environment (rather than
in whatever environment the caller happens to be in) is what makes the recorded
pins true rather than merely declared.

This module imports only the standard library and PyYAML, so it stays usable
from any environment -- including ones without a simulator installed.
"""

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path

import yaml

__all__ = ('export_model', 'ensure_environment', 'environment_key',
           'environment_name', 'canonical_environment_text', 'pip_requirements',
           'parse_pip_requirement', 'package_record', 'sha256_bytes',
           'find_conda_exe')

#: Prefix for harness-created conda environments. The remainder of the name is
#: the first 12 hex characters of the environment key.
ENV_NAME_PREFIX = 'sff-'

#: Repository root; the only entry placed on the child's PYTHONPATH.
REPO_ROOT = Path(__file__).resolve().parents[1]

#: SFF schema version exports are written against by default.
DEFAULT_SFF_VERSION = '0.0.6'

#%% Recipe helpers


def sha256_bytes(data):
    """
    Return the SHA-256 hex digest of `data`.

    Parameters
    ----------
    data : bytes

    Returns
    -------
    str
        64-character lowercase hex digest.
    """
    return hashlib.sha256(data).hexdigest()


def canonical_environment_text(text):
    """
    Return a canonical form of an environment specification.

    ``name`` and ``prefix`` are dropped and mappings are dumped with sorted
    keys, so that cosmetic edits -- renaming the environment, reordering keys --
    do not change the environment key and strand the environment already built
    from the same dependencies.

    Parameters
    ----------
    text : str
        Contents of an ``environment.yml`` file.

    Returns
    -------
    str
    """
    specification = yaml.safe_load(text) or {}
    specification = {k: v for k, v in specification.items()
                     if k not in ('name', 'prefix')}
    return yaml.safe_dump(specification, sort_keys=True, default_flow_style=False)


def environment_key(text):
    """
    Return the content-derived identity of an environment specification.

    Parameters
    ----------
    text : str
        Contents of an ``environment.yml`` file.

    Returns
    -------
    str
        SHA-256 hex digest of the canonicalized specification. Two models with
        identical dependencies therefore share one environment, and any change
        to a dependency forks a new one.
    """
    return sha256_bytes(canonical_environment_text(text).encode('utf-8'))


def environment_name(text):
    """
    Return the conda environment name for an environment specification.

    Parameters
    ----------
    text : str
        Contents of an ``environment.yml`` file.

    Returns
    -------
    str
        ``'sff-'`` followed by the first 12 characters of the environment key.
    """
    return ENV_NAME_PREFIX + environment_key(text)[:12]


def pip_requirements(text):
    """
    Return the pip requirement entries of an environment specification.

    Parameters
    ----------
    text : str
        Contents of an ``environment.yml`` file.

    Returns
    -------
    list of str
        Entries of every ``pip:`` mapping under ``dependencies``, in order.
    """
    specification = yaml.safe_load(text) or {}
    entries = []
    for dependency in specification.get('dependencies') or ():
        if isinstance(dependency, dict):
            entries.extend(dependency.get('pip') or ())
    return entries


def parse_pip_requirement(entry):
    """
    Parse one pip requirement entry into a package record.

    Parameters
    ----------
    entry : str
        A pip requirement, e.g. ``'numpy==1.26.4'`` or
        ``'biorefineries @ git+https://host/org/repo@<sha>'``.

    Returns
    -------
    dict or None
        ``{'name', 'version'}`` for a released pin, ``{'name', 'url', 'commit'}``
        for a VCS pin, or ``None`` for a blank line, an option directive, or a
        requirement this parser does not recognize.
    """
    entry = (entry or '').strip()
    if not entry or entry.startswith('-'):
        return None
    if ' @ ' in entry:
        name, _, reference = entry.partition(' @ ')
        return _vcs_record(name.strip(), reference.strip())
    if entry.startswith('git+'):
        return _vcs_record(None, entry)
    if '==' in entry:
        name, _, version = entry.partition('==')
        return {'name': name.strip(), 'version': version.strip()}
    return None


def _vcs_record(name, reference):
    """Build a package record from a ``git+`` reference; None if not one."""
    if not reference.startswith('git+'):
        return None
    url = reference[len('git+'):]
    url, _, fragment = url.partition('#')
    commit = None
    # Split on '@' only within the final path segment, so that a 'user@host'
    # style URL is not mistaken for a commit pin.
    if '@' in url.rsplit('/', 1)[-1]:
        url, _, commit = url.rpartition('@')
    if name is None:
        for part in fragment.split('&'):
            if part.startswith('egg='):
                name = part[len('egg='):]
        if name is None:
            name = url.rstrip('/').rsplit('/', 1)[-1]
            if name.endswith('.git'):
                name = name[:-len('.git')]
    record = {'name': name, 'url': url}
    if commit:
        record['commit'] = commit
    return record


def _normalized(name):
    """Normalize a distribution name for comparison (PEP 503-ish)."""
    return name.strip().lower().replace('_', '-').replace('.', '-')


def package_record(env_text, package_name, branch=None):
    """
    Return the pinned package record for `package_name`.

    Derived from the environment specification rather than declared separately,
    so the provenance recorded in an exported flowsheet cannot disagree with the
    environment the export ran in.

    Parameters
    ----------
    env_text : str
        Contents of an ``environment.yml`` file.
    package_name : str
        Distribution name to look up; matched ignoring case and ``-``/``_``.
    branch : str, optional
        Branch the pinned commit is reachable from, recorded when given.

    Returns
    -------
    dict
        Suitable for ``metadata.reproducibility.simulator_package`` and
        ``.flowsheet_model_package``.

    Raises
    ------
    ValueError
        If no pip requirement in the specification names `package_name`.
    """
    for entry in pip_requirements(env_text):
        record = parse_pip_requirement(entry)
        if record and _normalized(record['name']) == _normalized(package_name):
            if branch:
                record = dict(record, branch=branch)
            return record
    raise ValueError(
        f'no pip requirement for package {package_name!r} in the environment '
        'specification; every package recorded in metadata.reproducibility must '
        'be pinned there.'
    )
```

- [ ] **Step 4: Run the helper tests to verify they pass**

```bash
& "C:\Users\saran\anaconda3\envs\HP_2024\python.exe" -m pytest tests/test_harness.py -q
```

Expected: PASS (23 tests). If `test_every_pip_entry_is_parseable` fails, the offending entry in `environment.yml` is not in a form the parser recognizes — fix the entry, not the parser, unless the form is legitimately needed.

- [ ] **Step 5: Run the full suite**

```bash
& "C:\Users\saran\anaconda3\envs\HP_2024\python.exe" -m pytest tests -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add pisces_sff/_harness.py tests/test_harness.py
```

```bash
git commit -m "$(cat <<'EOF'
harness: derive environment identity and package pins from environment.yml

Adds the pure half of pisces_sff/_harness.py: a content-derived environment
key (canonicalized so that renaming an environment does not fork it, but any
dependency change does), and a pip-requirement parser that turns the committed
pins into the package records written to metadata.reproducibility. Deriving
those records from the environment specification is what keeps recorded
provenance from disagreeing with the environment an export ran in.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Environment provisioning and the locked child launch

**Files:**
- Modify: `pisces_sff/_harness.py` (append the orchestration section)
- Modify: `pisces_sff/__init__.py`
- Modify: `tests/test_harness.py` (append orchestration tests)

**Interfaces:**
- Consumes: `environment_key`, `environment_name` from Task 3.
- Produces:
  - `find_conda_exe(conda_exe=None) -> str` — raises `FileNotFoundError` if an explicitly given `conda_exe` does not exist (an explicit request must never silently fall back to a different conda)
  - `ensure_environment(env_yaml_path, recreate=False, conda_exe=None, run=None) -> str` — returns the environment prefix. `run` is an injection seam for tests; defaults to `subprocess.run`.
  - `environment_python(prefix) -> Path`
  - `export_lock()` — context manager; `LOCK_PATH`
  - `export_model(model_dir, output_path, recreate_env=False, conda_exe=None, sff_version=DEFAULT_SFF_VERSION, run=None) -> Path`
  - `pisces_sff.export_model` re-exported from the package.
- Note for Task 5: the child is invoked as `<env>/python -m pisces_sff._runner --model-dir <dir> --output <path> --env-key <key> --sff-version <ver>`.

- [ ] **Step 1: Write the failing orchestration tests**

Add `import json`, `import os`, `import subprocess` and `import tempfile` to the imports at the top of `tests/test_harness.py`, then append the following before the `if __name__ == "__main__":` block:

```python
def fake_conda_exe(directory):
    """Create a file named like a conda executable, for find_conda_exe to accept.

    find_conda_exe refuses an explicitly-given path that does not exist (an
    explicit request must not silently fall back to some other conda), and the
    real `conda` is not on PATH in non-interactive shells here -- so tests hand
    it a real file whose name the fake runner can dispatch on.
    """
    path = Path(directory) / ("conda.exe" if os.name == "nt" else "conda")
    path.write_text("", encoding="utf-8")
    return str(path)


class FakeConda:
    """Records conda invocations and answers `conda env list --json`.

    Environment provisioning is the one deliberately conda-shaped part of the
    harness. Driving it through an injected runner keeps its decisions -- reuse
    an environment that already matches the key, tear down a partial one so a
    broken environment is never reused, honour recreate -- testable without
    spending minutes building real environments.
    """

    def __init__(self, existing=(), fail_create=False, root="C:\\envs"):
        self.existing = list(existing)
        self.fail_create = fail_create
        self.root = root
        self.calls = []
        self.kwargs = []

    def __call__(self, cmd, **kwargs):
        self.calls.append(list(cmd))
        self.kwargs.append(dict(kwargs))
        if cmd[1:4] == ["env", "list", "--json"]:
            payload = json.dumps(
                {"envs": [self.root + "\\" + name for name in self.existing]}
            )
            return subprocess.CompletedProcess(cmd, 0, stdout=payload, stderr="")
        if cmd[1:3] == ["env", "create"]:
            name = cmd[cmd.index("-n") + 1]
            if self.fail_create:
                if kwargs.get("check"):
                    raise subprocess.CalledProcessError(1, cmd)
                return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="boom")
            self.existing.append(name)
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if cmd[1:3] == ["env", "remove"]:
            name = cmd[cmd.index("-n") + 1]
            if name in self.existing:
                self.existing.remove(name)
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    def commands(self):
        return [c[1:4] for c in self.calls]


class TestEnsureEnvironment(unittest.TestCase):
    def setUp(self):
        self.harness = load_harness()
        self.tmp = tempfile.TemporaryDirectory()
        self.env_yaml = Path(self.tmp.name) / "environment.yml"
        self.env_yaml.write_text(BASE_YAML, encoding="utf-8")
        self.name = self.harness.environment_name(BASE_YAML)
        self.conda_exe = fake_conda_exe(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def test_creates_the_environment_when_absent(self):
        conda = FakeConda()
        prefix = self.harness.ensure_environment(
            self.env_yaml, conda_exe=self.conda_exe, run=conda
        )
        self.assertIn(["env", "create", "-n"], [c[1:4] for c in conda.calls])
        self.assertTrue(prefix.endswith(self.name))

    def test_reuses_an_existing_environment(self):
        # The environment key is the reuse criterion; rebuilding a matching
        # environment would cost minutes on every export.
        conda = FakeConda(existing=[self.name])
        self.harness.ensure_environment(
            self.env_yaml, conda_exe=self.conda_exe, run=conda
        )
        self.assertNotIn(["env", "create", "-n"], [c[1:4] for c in conda.calls])

    def test_recreate_removes_then_creates(self):
        conda = FakeConda(existing=[self.name])
        self.harness.ensure_environment(
            self.env_yaml, recreate=True, conda_exe=self.conda_exe, run=conda
        )
        commands = [c[1:3] for c in conda.calls]
        self.assertIn(["env", "remove"], commands)
        self.assertIn(["env", "create"], commands)

    def test_failed_creation_removes_the_partial_environment(self):
        # A half-built environment matches the content hash, so without this
        # teardown it would be reused -- broken -- forever after.
        conda = FakeConda(fail_create=True)
        with self.assertRaises(Exception):
            self.harness.ensure_environment(
                self.env_yaml, conda_exe=self.conda_exe, run=conda
            )
        self.assertIn(["env", "remove"], [c[1:3] for c in conda.calls])

    def test_pip_dependency_resolution_is_disabled(self):
        # Bioindustrial-Park declares biosteam>=2.53.0; with resolution on, pip
        # replaces the pinned biosteam commit and every pin below it becomes
        # fiction. --no-deps cannot be written into the pip: block (pip's
        # requirements-file parser rejects it as an unknown option), so it is
        # applied as the PIP_NO_DEPS environment variable instead.
        conda = FakeConda()
        self.harness.ensure_environment(
            self.env_yaml, conda_exe=self.conda_exe, run=conda
        )
        for cmd, kwargs in zip(conda.calls, conda.kwargs):
            if cmd[1:3] == ["env", "create"]:
                self.assertEqual((kwargs.get("env") or {}).get("PIP_NO_DEPS"), "1")
                break
        else:
            self.fail("conda env create was never invoked")

    def test_an_explicit_missing_conda_is_reported_rather_than_replaced(self):
        # Falling back to a different conda than the one asked for would build
        # the environment somewhere the caller did not expect.
        with self.assertRaises(FileNotFoundError) as caught:
            self.harness.find_conda_exe(str(Path(self.tmp.name) / "absent" / "conda.exe"))
        self.assertIn("conda", str(caught.exception).lower())

    def test_conda_is_discovered_without_an_explicit_path(self):
        # conda is routinely absent from PATH in non-interactive shells even
        # where it is installed; discovery must not depend on PATH alone.
        self.assertTrue(Path(self.harness.find_conda_exe()).exists())


class TestExportLock(unittest.TestCase):
    def setUp(self):
        self.harness = load_harness()

    def test_lock_is_released_after_use(self):
        with self.harness.export_lock():
            self.assertTrue(self.harness.LOCK_PATH.exists())
        self.assertFalse(self.harness.LOCK_PATH.exists())

    def test_second_lock_is_refused(self):
        # Two concurrent simulations corrupt the shared numba cache, so this is
        # enforced rather than left to the caller's discipline.
        with self.harness.export_lock():
            with self.assertRaises(RuntimeError):
                with self.harness.export_lock():
                    pass

    def test_lock_is_released_after_an_error(self):
        with self.assertRaises(ValueError):
            with self.harness.export_lock():
                raise ValueError("boom")
        self.assertFalse(self.harness.LOCK_PATH.exists())


class TestExportModelInvocation(unittest.TestCase):
    """export_model must launch the child in the provisioned environment."""

    def setUp(self):
        self.harness = load_harness()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.model_dir = Path(self.tmp.name) / "some_model"
        self.model_dir.mkdir()
        (self.model_dir / "environment.yml").write_text(BASE_YAML, encoding="utf-8")
        (self.model_dir / "load.py").write_text("def load():\n    pass\n", encoding="utf-8")
        self.output = Path(self.tmp.name) / "out" / "some_model.json"
        self.conda_exe = fake_conda_exe(self.tmp.name)
        self.recorded = {}

        def fake_run(cmd, **kwargs):
            if Path(cmd[0]).name.startswith("conda"):
                return FakeConda(existing=[self.harness.environment_name(BASE_YAML)])(
                    cmd, **kwargs
                )
            self.recorded["cmd"] = list(cmd)
            self.recorded["env"] = dict(kwargs.get("env") or {})
            return subprocess.CompletedProcess(cmd, 0)

        self.fake_run = fake_run

    def test_child_runs_the_runner_module(self):
        self.harness.export_model(
            self.model_dir, self.output, conda_exe=self.conda_exe, run=self.fake_run
        )
        cmd = self.recorded["cmd"]
        self.assertIn("-m", cmd)
        self.assertIn("pisces_sff._runner", cmd)
        self.assertIn(str(self.model_dir.resolve()), cmd)

    def test_child_python_comes_from_the_provisioned_environment(self):
        self.harness.export_model(
            self.model_dir, self.output, conda_exe=self.conda_exe, run=self.fake_run
        )
        self.assertIn(
            self.harness.environment_name(BASE_YAML), self.recorded["cmd"][0]
        )

    def test_child_pythonpath_is_only_the_repository_root(self):
        # The reproducibility hole this harness closes: a user-level PYTHONPATH
        # of source clones silently shadows the pinned installs.
        self.harness.export_model(
            self.model_dir, self.output, conda_exe=self.conda_exe, run=self.fake_run
        )
        self.assertEqual(
            self.recorded["env"]["PYTHONPATH"], str(self.harness.REPO_ROOT)
        )

    def test_child_neutralizes_breakpoints(self):
        # _export.py has bare breakpoint() calls; in a TTY-less child they hang.
        self.harness.export_model(
            self.model_dir, self.output, conda_exe=self.conda_exe, run=self.fake_run
        )
        self.assertEqual(self.recorded["env"]["PYTHONBREAKPOINT"], "0")

    def test_child_ignores_conda_and_user_site_context(self):
        # Seeded explicitly: these variables are often unset in a
        # non-interactive shell, so an unseeded assertion would pass without
        # proving anything was scrubbed.
        from unittest import mock

        with mock.patch.dict(
            os.environ,
            {"CONDA_PREFIX": "C:\\envs\\HP_2024", "CONDA_DEFAULT_ENV": "HP_2024"},
        ):
            self.harness.export_model(
                self.model_dir, self.output, conda_exe=self.conda_exe, run=self.fake_run
            )
        env = self.recorded["env"]
        self.assertNotIn("CONDA_PREFIX", env)
        self.assertNotIn("CONDA_DEFAULT_ENV", env)
        self.assertEqual(env["PYTHONNOUSERSITE"], "1")

    def test_environment_key_is_passed_to_the_child(self):
        self.harness.export_model(
            self.model_dir, self.output, conda_exe=self.conda_exe, run=self.fake_run
        )
        cmd = self.recorded["cmd"]
        self.assertIn("--env-key", cmd)
        self.assertEqual(
            cmd[cmd.index("--env-key") + 1], self.harness.environment_key(BASE_YAML)
        )

    def test_nonzero_child_exit_raises(self):
        def failing_run(cmd, **kwargs):
            if Path(cmd[0]).name.startswith("conda"):
                return FakeConda(existing=[self.harness.environment_name(BASE_YAML)])(
                    cmd, **kwargs
                )
            return subprocess.CompletedProcess(cmd, 3)

        with self.assertRaises(RuntimeError):
            self.harness.export_model(
                self.model_dir, self.output, conda_exe=self.conda_exe, run=failing_run
            )

    def test_missing_load_script_is_reported_before_any_work(self):
        (self.model_dir / "load.py").unlink()
        with self.assertRaises(FileNotFoundError):
            self.harness.export_model(
                self.model_dir, self.output, conda_exe=self.conda_exe, run=self.fake_run
            )
```

- [ ] **Step 2: Run to confirm failure**

```bash
& "C:\Users\saran\anaconda3\envs\HP_2024\python.exe" -m pytest tests/test_harness.py -q
```

Expected: the new classes error with `AttributeError: module ... has no attribute 'ensure_environment'` / `'export_lock'` / `'export_model'`.

- [ ] **Step 3: Append the orchestration section to `_harness.py`**

```python
#%% Environment provisioning


def find_conda_exe(conda_exe=None):
    """
    Locate a usable conda executable.

    ``conda`` is frequently absent from ``PATH`` in non-interactive shells even
    where conda is installed, so common installation locations are searched
    before giving up.

    Parameters
    ----------
    conda_exe : str, optional
        Explicit path or command name. When given, only this is tried: silently
        falling back to a different conda would build the environment somewhere
        the caller did not ask for.

    Returns
    -------
    str
        Path to a conda executable.

    Raises
    ------
    FileNotFoundError
        If no candidate exists, naming what was searched.
    """
    if conda_exe:
        for candidate in (conda_exe, shutil.which(conda_exe)):
            if candidate and Path(candidate).exists():
                return str(candidate)
        raise FileNotFoundError(
            f'the conda executable {conda_exe!r} does not exist.'
        )
    home = Path.home()
    candidates = [
        os.environ.get('SFF_CONDA_EXE'),
        os.environ.get('CONDA_EXE'),
        shutil.which('conda'),
        str(home / 'anaconda3' / 'Scripts' / 'conda.exe'),
        str(home / 'miniconda3' / 'Scripts' / 'conda.exe'),
        str(home / 'anaconda3' / 'bin' / 'conda'),
        str(home / 'miniconda3' / 'bin' / 'conda'),
        '/opt/conda/bin/conda',
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return str(candidate)
    raise FileNotFoundError(
        'no conda executable found; environment provisioning needs one. Set the '
        'SFF_CONDA_EXE environment variable or pass conda_exe=... explicitly. '
        'Searched: ' + ', '.join(repr(c) for c in candidates if c)
    )


def _environment_prefix(conda, name, run):
    """Return the prefix of the conda environment called `name`, or None."""
    result = run([conda, 'env', 'list', '--json'],
                 capture_output=True, text=True, check=True)
    for prefix in json.loads(result.stdout).get('envs', ()):
        if Path(prefix).name == name:
            return prefix
    return None


def ensure_environment(env_yaml_path, recreate=False, conda_exe=None, run=None):
    """
    Return the prefix of the conda environment described by an environment file,
    creating it if necessary.

    Parameters
    ----------
    env_yaml_path : str or Path
        Path to an ``environment.yml``.
    recreate : bool, optional
        Remove and rebuild the environment even if it already exists.
    conda_exe : str, optional
        Explicit conda executable; see :func:`find_conda_exe`.
    run : callable, optional
        Subprocess runner, injectable for testing. Defaults to
        :func:`subprocess.run`.

    Returns
    -------
    str
        Path to the environment prefix.
    """
    if run is None:
        run = subprocess.run
    conda = find_conda_exe(conda_exe)
    env_yaml_path = Path(env_yaml_path).resolve()
    text = env_yaml_path.read_text(encoding='utf-8')
    name = environment_name(text)
    prefix = _environment_prefix(conda, name, run)
    if prefix is not None and recreate:
        run([conda, 'env', 'remove', '-n', name, '-y'], check=True)
        prefix = None
    if prefix is None:
        # PIP_NO_DEPS disables pip's dependency resolution for the whole
        # creation. Without it, Bioindustrial-Park's declared `biosteam>=2.53.0`
        # replaces the pinned biosteam commit and every pin below it becomes
        # fiction. It cannot be expressed as `--no-deps` inside the pip: block:
        # conda writes that block verbatim into a requirements file, and pip's
        # requirements-file parser rejects --no-deps as an unknown option.
        env = dict(os.environ, PIP_NO_DEPS='1')
        try:
            run([conda, 'env', 'create', '-n', name, '-f', str(env_yaml_path)],
                check=True, env=env)
        except Exception:
            # A partially-created environment still matches the content hash, so
            # leaving it in place would make every later export reuse a broken
            # environment.
            run([conda, 'env', 'remove', '-n', name, '-y'], check=False)
            raise
        prefix = _environment_prefix(conda, name, run)
        if prefix is None:
            raise RuntimeError(
                f'conda reported success but environment {name!r} does not exist'
            )
    return prefix


def environment_python(prefix):
    """
    Return the Python interpreter inside a conda environment prefix.

    Parameters
    ----------
    prefix : str or Path

    Returns
    -------
    Path
    """
    prefix = Path(prefix)
    return prefix / 'python.exe' if os.name == 'nt' else prefix / 'bin' / 'python'


#%% Export orchestration

#: Guards against concurrent exports; see :func:`export_lock`.
LOCK_PATH = Path(tempfile.gettempdir()) / 'pisces_sff_export.lock'


@contextmanager
def export_lock():
    """
    Refuse to run two exports at once.

    Exporting simulates a system, which recompiles and writes a shared on-disk
    numba cache; two simultaneous writers corrupt it, and the resulting import
    error looks nothing like its cause. Enforced here rather than left to the
    caller.

    Raises
    ------
    RuntimeError
        If the lock is already held.
    """
    try:
        descriptor = os.open(str(LOCK_PATH), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise RuntimeError(
            f'another SFF export appears to be running (lock file {LOCK_PATH}). '
            'Concurrent simulations corrupt the shared numba cache. If no export '
            'is running, delete that file and retry.'
        )
    try:
        os.write(descriptor, str(os.getpid()).encode('utf-8'))
        os.close(descriptor)
        yield
    finally:
        try:
            LOCK_PATH.unlink()
        except FileNotFoundError:
            pass


def export_model(model_dir, output_path, recreate_env=False, conda_exe=None,
                 sff_version=DEFAULT_SFF_VERSION, run=None):
    """
    Export a model to SFF from inside the environment its recipe pins.

    Provisions the conda environment described by ``<model_dir>/environment.yml``
    (reusing it when one already matches), then runs :mod:`pisces_sff._runner`
    with that environment's interpreter. The child's ``PYTHONPATH`` is set to the
    repository root alone, so source clones on a user-level ``PYTHONPATH`` cannot
    shadow the pinned installs -- which is the failure mode that made previous
    exports irreproducible.

    Parameters
    ----------
    model_dir : str or Path
        Directory containing ``environment.yml`` and ``load.py``.
    output_path : str or Path
        Path to write the SFF JSON file to. Parent directories are created.
    recreate_env : bool, optional
        Rebuild the environment even if it already exists.
    conda_exe : str, optional
        Explicit conda executable; see :func:`find_conda_exe`.
    sff_version : str, optional
        SFF schema version to export against.
    run : callable, optional
        Subprocess runner, injectable for testing.

    Returns
    -------
    Path
        `output_path`.

    Raises
    ------
    FileNotFoundError
        If the model directory is missing a required file.
    RuntimeError
        If the child process exits non-zero.
    """
    if run is None:
        run = subprocess.run
    model_dir = Path(model_dir).resolve()
    env_yaml_path = model_dir / 'environment.yml'
    load_script_path = model_dir / 'load.py'
    for required in (env_yaml_path, load_script_path):
        if not required.is_file():
            raise FileNotFoundError(
                f'{required} is required: a model directory must contain both '
                'environment.yml and load.py.'
            )
    output_path = Path(output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    text = env_yaml_path.read_text(encoding='utf-8')
    key = environment_key(text)
    prefix = ensure_environment(env_yaml_path, recreate=recreate_env,
                                conda_exe=conda_exe, run=run)

    # Scrub the inherited context: conda variables would point the child back at
    # the parent's environment, and user site-packages is another shadowing path.
    child_env = {k: v for k, v in os.environ.items()
                 if k not in ('CONDA_PREFIX', 'CONDA_DEFAULT_ENV', 'CONDA_SHLVL',
                              'CONDA_PYTHON_EXE', 'PYTHONHOME')}
    child_env['PYTHONPATH'] = str(REPO_ROOT)
    child_env['PYTHONNOUSERSITE'] = '1'
    # _export.py contains bare breakpoint() calls (a known issue). In a child
    # process with no TTY they hang forever; this makes them no-ops instead.
    child_env['PYTHONBREAKPOINT'] = '0'

    command = [str(environment_python(prefix)), '-m', 'pisces_sff._runner',
               '--model-dir', str(model_dir),
               '--output', str(output_path),
               '--env-key', key,
               '--sff-version', str(sff_version)]
    with export_lock():
        result = run(command, env=child_env)
    if result.returncode != 0:
        raise RuntimeError(
            f'export failed for model {model_dir.name!r} '
            f'(child process exited with code {result.returncode}); '
            'see the output above.'
        )
    return output_path
```

- [ ] **Step 4: Re-export the harness from the package**

In `pisces_sff/__init__.py`, after the `_export` import block (line 19), add:

```python
from . import _harness
from ._harness import *
```

and add `*_harness.__all__,` to the `__all__` tuple, after `*_export.__all__,`.

- [ ] **Step 5: Run the harness tests**

```bash
& "C:\Users\saran\anaconda3\envs\HP_2024\python.exe" -m pytest tests/test_harness.py -q
```

Expected: PASS. If `test_lock_is_released_after_use` fails because a stale lock exists from an interrupted run, delete `%TEMP%\pisces_sff_export.lock` and re-run.

- [ ] **Step 6: Verify the package still imports and exposes `export_model`**

```bash
& "C:\Users\saran\anaconda3\envs\HP_2024\python.exe" -c "import pisces_sff; print(pisces_sff.__version__); print('export_model' in pisces_sff.__all__); print(pisces_sff.find_conda_exe())"
```

Expected: `0.0.6`, `True`, and a real path to `conda.exe`.

- [ ] **Step 7: Run the full suite and canonical validation**

```bash
& "C:\Users\saran\anaconda3\envs\HP_2024\python.exe" -m pytest tests -q
```

```bash
& "C:\Users\saran\anaconda3\envs\HP_2024\python.exe" -c "import glob,os; from pisces_sff import validate_json_against_schema as v; s='pisces_sff/schema/sff_schema.json'; r=[(os.path.basename(f),)+v(f,s) for f in sorted(glob.glob('pisces_sff/exported_flowsheets/bioindustrial_park/*.json'))]; print('failures:', sum(1 for _,ok,_ in r if not ok))"
```

Expected: all tests pass; `failures: 0`.

- [ ] **Step 8: Commit**

```bash
git add pisces_sff/_harness.py pisces_sff/__init__.py tests/test_harness.py
```

```bash
git commit -m "$(cat <<'EOF'
harness: provision the pinned environment and run exports inside it

export_model() creates (or reuses) the conda environment a model's
environment.yml describes, then launches pisces_sff._runner with that
environment's interpreter and a scrubbed process environment: PYTHONPATH is
the repository root alone, so source clones on a user-level PYTHONPATH can no
longer shadow the pinned installs; PYTHONBREAKPOINT=0 keeps _export.py's bare
breakpoint() calls from hanging a TTY-less child.

pip dependency resolution is disabled via PIP_NO_DEPS for environment
creation, a failed creation tears down the partial environment so a broken one
is never reused under a matching key, and a lock file refuses concurrent
exports because simultaneous simulations corrupt the shared numba cache.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: The runner and the Tier 2 export test

**Files:**
- Create: `pisces_sff/_runner.py`
- Test: `tests/test_export_corn_dry_grind_ethanol.py`

**Interfaces:**
- Consumes: `package_record`, `environment_key`, `sha256_bytes`, `REPO_ROOT` (Task 3); the model contract (Task 2); `export_biosteam_flowsheet_sff_0_0_6` (Task 1); the child command line (Task 4).
- Produces:
  - `load_model_module(model_dir) -> module`
  - `build_reproducibility(model_dir, module, env_key=None) -> dict`
  - `run_model_export(model_dir, output_path, sff_version='0.0.6', env_key=None) -> Path`
  - `main(argv=None) -> int` (CLI entry point)

- [ ] **Step 1: Write the failing Tier 2 test**

Create `tests/test_export_corn_dry_grind_ethanol.py`:

```python
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
        from pisces_sff import _runner
        from pisces_sff._validate import validate_json_against_schema

        cls.validate = staticmethod(validate_json_against_schema)
        cls.tmp = tempfile.TemporaryDirectory()
        cls.output = Path(cls.tmp.name) / "corn_dry_grind_ethanol.json"
        _runner.run_model_export(MODEL_DIR, cls.output, sff_version="0.0.6")
        with cls.output.open("r", encoding="utf-8") as f:
            cls.flowsheet = json.load(f)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_output_validates_against_the_schema(self):
        is_valid, errors = self.validate(str(self.output), str(SCHEMA_PATH))
        self.assertTrue(is_valid, f"validation errors: {errors[:5]}")

    def test_sff_version_is_recorded(self):
        self.assertEqual(self.flowsheet["metadata"]["sff_version"], "0.0.6")

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


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run it to confirm it fails**

```bash
$env:SFF_TEST_BIOSTEAM = "1"; & "C:\Users\saran\anaconda3\envs\HP_2024\python.exe" -m pytest tests/test_export_corn_dry_grind_ethanol.py -q; $env:SFF_TEST_BIOSTEAM = $null
```

Expected: error in `setUpClass` — `ImportError: cannot import name '_runner' from 'pisces_sff'`.

- [ ] **Step 3: Write `_runner.py`**

Create `pisces_sff/_runner.py`:

```python
# -*- coding: utf-8 -*-
# Code to export flowsheets from multiple tools into a standardized JSON format.
# Copyright (C) 2025-, Sarang S. Bhagwat <sarangbhagwat.developer@gmail.com>
#
# This module is under the MIT open-source license. See
# https://github.com/sustainability-software-lab/pisces-standard-flowsheet-format/blob/main/LICENSE
# for license details.

"""
Child side of the reproducible export harness.

Runs *inside* the environment a model's recipe pins, launched by
:func:`pisces_sff.export_model`. Loads the model, simulates it, assembles the
``metadata.reproducibility`` payload, calls the versioned exporter once, and
validates the result.

Usable directly for debugging, provided the current environment can import the
model's dependencies::

    python -m pisces_sff._runner --model-dir <dir> --output <path>
"""

import argparse
import importlib.util
import platform
import sys
from datetime import datetime
from pathlib import Path

from ._harness import REPO_ROOT, environment_key, package_record, sha256_bytes
from ._validate import validate_json_against_schema

__all__ = ('run_model_export', 'build_reproducibility', 'load_model_module')

SCHEMA_PATH = Path(__file__).resolve().parent / 'schema' / 'sff_schema.json'

#: Packages whose installed versions are recorded in `resolved.package_versions`.
#: Distinguishes what actually ran from what the recipe declared.
TRACKED_PACKAGES = ('biosteam', 'biorefineries', 'thermosteam', 'chemicals',
                    'thermo', 'fluids', 'flexsolve', 'numpy', 'scipy', 'pandas',
                    'numba', 'llvmlite')

#%% Model loading


def load_model_module(model_dir):
    """
    Import a model's ``load.py`` by file path.

    Imported by path rather than as a package module so that a model directory
    needs no packaging and can be dropped in as data.

    Parameters
    ----------
    model_dir : str or Path
        Directory containing ``load.py``.

    Returns
    -------
    module
    """
    model_dir = Path(model_dir).resolve()
    path = model_dir / 'load.py'
    spec = importlib.util.spec_from_file_location(f'sff_model_{model_dir.name}', path)
    if spec is None:
        raise FileNotFoundError(f'could not load a model module from {path}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

#%% Reproducibility payload


def _installed_versions():
    """Map distribution name -> installed version for TRACKED_PACKAGES."""
    from importlib.metadata import PackageNotFoundError, version

    versions = {}
    for name in TRACKED_PACKAGES:
        try:
            versions[name] = version(name)
        except PackageNotFoundError:
            continue
    return versions


def _file_record(path, file_format, extra=None):
    """Build an embedded-file record: format, filename, path, sha256, content."""
    path = Path(path).resolve()
    data = path.read_bytes()
    record = {'format': file_format,
              'filename': path.name,
              'sha256': sha256_bytes(data),
              'content': data.decode('utf-8')}
    try:
        record['path'] = path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        # Model directories outside the repository simply carry no repo-relative
        # path; the embedded content still makes the record self-sufficient.
        pass
    if extra:
        record.update(extra)
    return record


def build_reproducibility(model_dir, module, env_key=None):
    """
    Assemble the ``metadata.reproducibility`` payload for a model.

    Parameters
    ----------
    model_dir : str or Path
        Directory containing ``environment.yml`` and ``load.py``.
    module : module
        The model's imported ``load.py``, read for its declarations.
    env_key : str, optional
        Environment key supplied by the harness. Recomputed from the
        environment specification when absent.

    Returns
    -------
    dict
        Conforming to ``metadata.reproducibility`` in SFF v0.0.6.
    """
    model_dir = Path(model_dir).resolve()
    env_path = model_dir / 'environment.yml'
    env_text = env_path.read_text(encoding='utf-8')
    branches = getattr(module, 'PACKAGE_BRANCHES', None) or {}
    simulator_package = module.SIMULATOR_PACKAGE
    flowsheet_model_package = module.FLOWSHEET_MODEL_PACKAGE
    return {
        'environment': _file_record(env_path, 'conda-environment-yaml'),
        'load_script': _file_record(model_dir / 'load.py', 'python',
                                    {'entry_point': 'load'}),
        # Derived from the environment specification rather than declared
        # separately, so these pins cannot disagree with the environment used.
        'simulator_package': package_record(env_text, simulator_package,
                                            branches.get(simulator_package)),
        'flowsheet_model_package': package_record(
            env_text, flowsheet_model_package,
            branches.get(flowsheet_model_package)),
        'resolved': {
            'python_version': platform.python_version(),
            'platform': platform.platform(),
            'env_key': env_key or environment_key(env_text),
            'exported_at': datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
            'package_versions': _installed_versions(),
        },
    }

#%% Export


def run_model_export(model_dir, output_path, sff_version='0.0.6', env_key=None):
    """
    Load, simulate, and export a model, then validate the result.

    Parameters
    ----------
    model_dir : str or Path
        Directory containing ``environment.yml`` and ``load.py``.
    output_path : str or Path
        Path to write the SFF JSON file to.
    sff_version : str, optional
        SFF schema version to export against.
    env_key : str, optional
        Environment key supplied by the harness.

    Returns
    -------
    Path
        `output_path`.

    Raises
    ------
    ValueError
        If the model declares a simulator with no export entry point.
    RuntimeError
        If ``load()`` raises, or if the written file fails schema validation.
        A failed validation leaves the file on disk for inspection.
    """
    from . import _export

    model_dir = Path(model_dir).resolve()
    output_path = Path(output_path)
    module = load_model_module(model_dir)
    simulator = getattr(module, 'SIMULATOR', 'biosteam')
    # Name-based dispatch, mirroring the versioned-exporter lookup in _export:
    # adding a simulator means adding an export entry point with the matching
    # name, and nothing here changes.
    entry_point_name = f'export_{simulator}_flowsheet'
    exporter = getattr(_export, entry_point_name, None)
    if exporter is None:
        raise ValueError(
            f'model {model_dir.name!r} declares SIMULATOR={simulator!r}, but no '
            f'export entry point named {entry_point_name!r} exists in '
            'pisces_sff._export.'
        )
    # Built before simulating so a malformed recipe fails in milliseconds
    # instead of after a multi-minute simulation.
    reproducibility = build_reproducibility(model_dir, module, env_key=env_key)

    try:
        system, tea = module.load()
    except Exception as error:
        # Attach the model name: a bare traceback from deep inside a simulator
        # gives no clue which recipe was being run.
        raise RuntimeError(
            f'load() failed for model {model_dir.name!r}: {error}'
        ) from error

    exporter(system, str(output_path), sff_version=sff_version, tea=tea,
             reproducibility=reproducibility,
             **(getattr(module, 'EXPORT_KWARGS', None) or {}))

    is_valid, errors = validate_json_against_schema(str(output_path),
                                                    str(SCHEMA_PATH))
    if not is_valid:
        raise RuntimeError(
            f'exported flowsheet {output_path} failed validation against SFF '
            f'{sff_version}; the file was left in place for inspection:\n'
            + '\n'.join(errors[:10])
        )
    return output_path

#%% Command-line interface


def main(argv=None):
    """
    Command-line entry point invoked by :func:`pisces_sff.export_model`.

    Parameters
    ----------
    argv : list of str, optional

    Returns
    -------
    int
        Process exit code.
    """
    parser = argparse.ArgumentParser(
        prog='python -m pisces_sff._runner',
        description='Load, simulate, and export one model to SFF.',
    )
    parser.add_argument('--model-dir', required=True,
                        help='directory containing environment.yml and load.py')
    parser.add_argument('--output', required=True,
                        help='path to write the SFF JSON file to')
    parser.add_argument('--sff-version', default='0.0.6',
                        help='SFF schema version to export against')
    parser.add_argument('--env-key', default=None,
                        help='environment key recorded in the exported file')
    args = parser.parse_args(argv)
    try:
        path = run_model_export(args.model_dir, args.output,
                                sff_version=args.sff_version,
                                env_key=args.env_key)
    except Exception as error:
        print(f'ERROR: {error}', file=sys.stderr)
        return 1
    print(f'wrote {path}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
```

- [ ] **Step 4: Run the Tier 2 test**

Run exactly one simulating test at a time.

```bash
$env:SFF_TEST_BIOSTEAM = "1"; & "C:\Users\saran\anaconda3\envs\HP_2024\python.exe" -m pytest tests/test_export_corn_dry_grind_ethanol.py -q; $env:SFF_TEST_BIOSTEAM = $null
```

Expected: PASS (12 tests), taking minutes. On `ReferenceError: ... underlying object has vanished`, clear the numba caches (Global Constraints) and re-run.

- [ ] **Step 5: Confirm the tier is skipped by default**

```bash
& "C:\Users\saran\anaconda3\envs\HP_2024\python.exe" -m pytest tests -q
```

Expected: all tests pass, with 12 skipped and no simulation run — the default suite must stay fast (~seconds).

- [ ] **Step 6: Verify the runner CLI is reachable as the harness invokes it**

```bash
& "C:\Users\saran\anaconda3\envs\HP_2024\python.exe" -m pisces_sff._runner --help
```

Expected: the argparse help text listing `--model-dir`, `--output`, `--sff-version`, `--env-key`.

- [ ] **Step 7: Canonical validation**

```bash
& "C:\Users\saran\anaconda3\envs\HP_2024\python.exe" -c "import glob,os; from pisces_sff import validate_json_against_schema as v; s='pisces_sff/schema/sff_schema.json'; r=[(os.path.basename(f),)+v(f,s) for f in sorted(glob.glob('pisces_sff/exported_flowsheets/bioindustrial_park/*.json'))]; print('failures:', sum(1 for _,ok,_ in r if not ok))"
```

Expected: `failures: 0`.

- [ ] **Step 8: Commit**

```bash
git add pisces_sff/_runner.py tests/test_export_corn_dry_grind_ethanol.py
```

```bash
git commit -m "$(cat <<'EOF'
runner: export a model and embed its reproducibility recipe

pisces_sff._runner runs inside the environment a model's recipe pins: it
imports load.py by path, dispatches to an export entry point by the model's
SIMULATOR declaration, embeds the environment specification and load script
(with SHA-256 digests) plus the derived package pins and the observed runtime,
and validates the written file, leaving it on disk when validation fails.

Adds a Tier 2 test gated on SFF_TEST_BIOSTEAM=1. Its assertions are structural
only: run from a developer environment the export exercises whatever biosteam
is importable there rather than the pinned commit, so numeric baselines belong
in the end-to-end tier.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: End-to-end run, pin completion, and the delivered export

This is the task in which the pins are executed for the first time. Read §7.1 of the spec before starting: `biosteam@e2d3942` (2.46.1) paired with `BIP@5842328` (which declares `biosteam>=2.53.0`) has never been run. The evidence says it works — the corn source at `5842328` uses the older `V=` / no-`RH` API — but if it does not, **stop and ask the user**; bumping the biosteam pin changes what gets exported and is their decision.

**Files:**
- Create: `tests/test_end_to_end_export.py`
- Create: `tests/baselines/corn_dry_grind_ethanol.json`
- Create: `pisces_sff/exported_flowsheets/bioindustrial_park/corn_dry_grind_ethanol.json`
- Modify: `pisces_sff/models/biosteam_models/corn_dry_grind_ethanol/environment.yml` (pin completion)
- Modify: `CLAUDE.md` (not committed — gitignored)

**Interfaces:**
- Consumes: `export_model` (Task 4), `run_model_export` (Task 5), the corn recipe (Task 2).
- Produces: the delivered corpus file and the recorded Tier 3 baseline.

- [ ] **Step 1: Write the Tier 3 test**

Create `tests/test_end_to_end_export.py`:

```python
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
        flows = {s["id"]: s["stream_properties"]["total_mass_flow"]["value"]
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
```

- [ ] **Step 2: Confirm the tier is skipped by default**

```bash
& "C:\Users\saran\anaconda3\envs\HP_2024\python.exe" -m pytest tests -q
```

Expected: all tests pass; Tier 2 and Tier 3 skipped. Tier 3 must skip cleanly even though `tests/baselines/` does not exist yet — the baseline is read in `setUpClass`, which never runs when skipped.

- [ ] **Step 3: Build the environment and complete the pin list**

This is the empirical loop from spec §7. Run the export directly, adding pins as they are demanded. **One run at a time.**

```bash
& "C:\Users\saran\anaconda3\envs\HP_2024\python.exe" -c "from pisces_sff import export_model; export_model('pisces_sff/models/biosteam_models/corn_dry_grind_ethanol', 'C:/Users/saran/AppData/Local/Temp/claude/C--Users-saran-Documents-Academia-repository-clones-pisces-standard-flowsheet-format/56a8d604-4b7a-4661-9295-608cf9d05740/scratchpad/corn_dry_grind_ethanol.json')"
```

The loop, repeated until the command succeeds:

1. **`conda env create` fails on `python=3.9.25`** — the exact patch is unavailable on `defaults` for this platform. Relax to `python=3.9` in `environment.yml` and note the resolved patch version in the commit message.
2. **`ModuleNotFoundError: No module named 'X'`** — add `X==<version>` to the `pip:` block, pinned to the version installed in HP_2024. Read that version with:
   ```bash
   & "C:\Users\saran\anaconda3\envs\HP_2024\python.exe" -c "from importlib.metadata import version; print(version('X'))"
   ```
   Then re-run with `recreate_env=True` so the changed key builds a fresh environment:
   ```bash
   & "C:\Users\saran\anaconda3\envs\HP_2024\python.exe" -c "from pisces_sff import export_model; export_model('pisces_sff/models/biosteam_models/corn_dry_grind_ethanol', 'C:/Users/saran/AppData/Local/Temp/claude/C--Users-saran-Documents-Academia-repository-clones-pisces-standard-flowsheet-format/56a8d604-4b7a-4661-9295-608cf9d05740/scratchpad/corn_dry_grind_ethanol.json', recreate_env=True)"
   ```
   (Editing `environment.yml` changes the environment key, so a plain re-run would build a new environment anyway; `recreate_env=True` guarantees no stale reuse.)
3. **An `AttributeError` or `TypeError` from inside `biorefineries.corn`** — this is the §7.1 risk materializing: the biosteam/BIP pairing is incompatible. **Stop. Do not bump the biosteam pin.** Report the traceback to the user and ask; changing that pin changes what gets exported.
4. **The lock file is held from an interrupted run** — delete `%TEMP%\pisces_sff_export.lock` and re-run.

Record every pin added, for the commit message.

- [ ] **Step 4: Verify the pins actually took effect**

Write this verification script to the scratchpad (a file rather than a `-c` snippet, to keep the nested quoting out of PowerShell's way):

`C:\Users\saran\AppData\Local\Temp\claude\C--Users-saran-Documents-Academia-repository-clones-pisces-standard-flowsheet-format\56a8d604-4b7a-4661-9295-608cf9d05740\scratchpad\verify_env.py`

```python
"""Confirm the created environment holds the pinned simulator, not a newer one."""
import subprocess
from pathlib import Path

from pisces_sff._harness import (ensure_environment, environment_name,
                                 environment_python)

env_yaml = Path('pisces_sff/models/biosteam_models/corn_dry_grind_ethanol/environment.yml')
print('environment name:', environment_name(env_yaml.read_text(encoding='utf-8')))
python = environment_python(ensure_environment(env_yaml))
print('interpreter:', python)

probe = (
    "import biosteam\n"
    "from importlib.metadata import version\n"
    "print('biosteam', biosteam.__version__, version('biosteam'))\n"
    "print('biorefineries', version('biorefineries'))\n"
    "print('biosteam location', biosteam.__file__)\n"
)
result = subprocess.run([str(python), '-c', probe], capture_output=True, text=True,
                        env={'PYTHONNOUSERSITE': '1'})
print(result.stdout or result.stderr)
```

```bash
& "C:\Users\saran\anaconda3\envs\HP_2024\python.exe" "C:\Users\saran\AppData\Local\Temp\claude\C--Users-saran-Documents-Academia-repository-clones-pisces-standard-flowsheet-format\56a8d604-4b7a-4661-9295-608cf9d05740\scratchpad\verify_env.py"
```

Expected: `biosteam 2.46.1 2.46.1` — **not** 2.53 or newer. A newer version means `PIP_NO_DEPS` did not take effect and BIP's declaration replaced the pin; fix that before continuing. `biosteam location` must point inside the `sff-…` environment, not into a source clone.

- [ ] **Step 5: Record the baseline**

With the export from Step 3 written to the scratchpad, generate the baseline file:

```bash
& "C:\Users\saran\anaconda3\envs\HP_2024\python.exe" -c "import json, os; src=r'C:/Users/saran/AppData/Local/Temp/claude/C--Users-saran-Documents-Academia-repository-clones-pisces-standard-flowsheet-format/56a8d604-4b7a-4661-9295-608cf9d05740/scratchpad/corn_dry_grind_ethanol.json'; d=json.load(open(src)); r=d['metadata']['reproducibility']['resolved']; flows={s['id']: s['stream_properties']['total_mass_flow']['value'] for s in d['streams']}; keep=['corn','ethanol','DDGS','crude_oil']; b={'recorded_from':'first successful Tier 3 run','biosteam_version':r['package_versions']['biosteam'],'env_key':r['env_key'],'n_units':len(d['units']),'n_streams':len(d['streams']),'n_chemicals':len(d['chemicals']),'TEA_year':d['metadata']['TEA_year'],'stream_mass_flows':{k:flows[k] for k in keep if k in flows},'total_installed_cost':sum(sum(u['installed_costs'].values()) for u in d['units'])}; os.makedirs('tests/baselines', exist_ok=True); json.dump(b, open('tests/baselines/corn_dry_grind_ethanol.json','w'), indent=2); print(json.dumps(b, indent=2))"
```

Read the printed values and sanity-check them before accepting: `biosteam_version` must be `2.46.1`, `TEA_year` should be `2018` (the committed `corn_ethanol.json` reports that), and `n_units` should be near 71 with `n_streams` near 108 (the committed export's counts, from a different BIP commit — a large divergence means something other than the DDGS-section difference described in spec §7.2, and is worth investigating before recording).

- [ ] **Step 6: Run the Tier 3 test**

```bash
$env:SFF_TEST_E2E = "1"; & "C:\Users\saran\anaconda3\envs\HP_2024\python.exe" -m pytest tests/test_end_to_end_export.py -q; $env:SFF_TEST_E2E = $null
```

Expected: PASS (6 tests). The environment now exists, so this run only simulates. This is the check that the recorded baseline is reproducible rather than a one-off.

- [ ] **Step 7: Write the delivered export into the corpus**

```bash
& "C:\Users\saran\anaconda3\envs\HP_2024\python.exe" -c "from pisces_sff import export_model; export_model('pisces_sff/models/biosteam_models/corn_dry_grind_ethanol', 'pisces_sff/exported_flowsheets/bioindustrial_park/corn_dry_grind_ethanol.json')"
```

Expected: `wrote ...corn_dry_grind_ethanol.json`, exit 0. This is a **new** file; `corn_ethanol.json` is not touched.

- [ ] **Step 8: Run canonical validation over the enlarged corpus**

```bash
& "C:\Users\saran\anaconda3\envs\HP_2024\python.exe" -c "import glob,os; from pisces_sff import validate_json_against_schema as v; s='pisces_sff/schema/sff_schema.json'; r=[(os.path.basename(f),)+v(f,s) for f in sorted(glob.glob('pisces_sff/exported_flowsheets/bioindustrial_park/*.json'))]; [print(n,'OK' if ok else ('FAIL '+str(e[:2]))) for n,ok,e in r]; print('count:', len(r)); print('failures:', sum(1 for _,ok,_ in r if not ok))"
```

Expected: `count: 19`, `failures: 0`.

- [ ] **Step 9: Confirm the committed export is unchanged**

```bash
git status --short pisces_sff/exported_flowsheets/
```

Expected: exactly one entry, `?? pisces_sff/exported_flowsheets/bioindustrial_park/corn_dry_grind_ethanol.json`. Any `M` on an existing flowsheet means something regenerated the corpus — revert it (`git checkout -- <file>`) and investigate.

- [ ] **Step 10: Run the default suite**

```bash
& "C:\Users\saran\anaconda3\envs\HP_2024\python.exe" -m pytest tests -q
```

Expected: all tests pass; Tiers 2 and 3 skipped. Record the exact passed/skipped counts — Step 11 writes them into CLAUDE.md.

- [ ] **Step 11: Update CLAUDE.md**

`CLAUDE.md` is gitignored — edit it, but do **not** `git add` it.

In the **Canonical validation** section:
- Change "Pass criterion: `failures: 0` across all **18** flowsheets" to **19**.
- Replace "currently **10 passed**, ~0.1 s" with the counts observed in Step 10.
- Replace the "Smoke tests are planned but not yet written" blockquote with:

```markdown
### 3. Simulating test tiers (run explicitly)

Both tiers simulate; run them one at a time, never concurrently.

**Tier 2** — exports the corn model in the current environment and asserts
structural properties of the output:

    $env:SFF_TEST_BIOSTEAM = "1"; & "C:\Users\saran\anaconda3\envs\HP_2024\python.exe" -m pytest tests/test_export_corn_dry_grind_ethanol.py -q; $env:SFF_TEST_BIOSTEAM = $null

**Tier 3** — the full harness, including conda environment creation. The only
tier in which the recipe's pins are what actually ran, and therefore the only
one asserting numeric baselines:

    $env:SFF_TEST_E2E = "1"; & "C:\Users\saran\anaconda3\envs\HP_2024\python.exe" -m pytest tests/test_end_to_end_export.py -q; $env:SFF_TEST_E2E = $null

Baselines live in `tests/baselines/corn_dry_grind_ethanol.json`, recorded from
the first successful Tier 3 run, compared at a relative tolerance of 1e-4
(`RTOL` in `tests/test_end_to_end_export.py`). Regenerate them only when a pin
changes deliberately — a baseline edit to make a test pass hides exactly what
the tier exists to catch.
```

In the **Known issues** section, extend item 1 to note that `corn_dry_grind_ethanol.json` is the first corpus file reporting `sff_version: "0.0.6"` while the other 18 still report `"0.0.3"`.

In **Structure & Key Files**, add `_harness.py`, `_runner.py`, and `models/` to the tree.

- [ ] **Step 12: Commit**

```bash
git add pisces_sff/models/biosteam_models/corn_dry_grind_ethanol/environment.yml tests/test_end_to_end_export.py tests/baselines pisces_sff/exported_flowsheets/bioindustrial_park/corn_dry_grind_ethanol.json
```

```bash
git commit -m "$(cat <<'EOF'
export corn_dry_grind_ethanol from its pinned environment

First flowsheet exported end to end through the harness: the conda environment
is built from the committed recipe and the simulation runs inside it, so the
pins recorded in metadata.reproducibility are what actually produced the file.

Completes the environment.yml pin list empirically (dependency resolution is
off, so every transitive dependency is explicit) and adds the Tier 3 test with
baselines recorded from that first successful run.

The export is a new artifact rather than a regeneration: it pins
Bioindustrial-Park 5842328, whose corn DDGS section differs from the commit
behind the existing corn_ethanol.json, which is left untouched. The corpus is
now 19 files.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

## Verification (whole plan)

After Task 6:

```bash
& "C:\Users\saran\anaconda3\envs\HP_2024\python.exe" -c "import glob,os; from pisces_sff import validate_json_against_schema as v; s='pisces_sff/schema/sff_schema.json'; r=[(os.path.basename(f),)+v(f,s) for f in sorted(glob.glob('pisces_sff/exported_flowsheets/bioindustrial_park/*.json'))]; print('count:', len(r)); print('failures:', sum(1 for _,ok,_ in r if not ok))"
```

```bash
& "C:\Users\saran\anaconda3\envs\HP_2024\python.exe" -m pytest tests -q
```

Pass criteria: `count: 19`, `failures: 0`, all tests pass with Tiers 2 and 3 skipped. Both simulating tiers must have passed in their own runs (Task 5 Step 4, Task 6 Step 6) before the harness is considered complete.
