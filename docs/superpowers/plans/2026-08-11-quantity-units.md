# Quantity Units for the SFF Schema (v0.0.7) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every numeric quantity in an SFF file a clean, consistent, machine-readable "quantity unit" — a top-level `quantity_units_global` registry plus per-unit-operation `quantity_units_for_design_results` — using BioSTEAM-native unit strings, behind a v0.0.7 schema bump.

**Architecture:** The single-file JSON Schema gains an additive global registry first, then the breaking field renames/retypings land together with the version bump and a new versioned exporter. The reference exporter's shared assembler (`_build_sff_dict`) becomes version-aware: a new import-light helper module (`_quantity_units.py`) routes every scalar through one formatter so pre-0.0.7 output stays byte-identical while 0.0.7 emits bare numbers plus the registry. Only `corn_dry_grind_ethanol.json` is re-exported; the other 18 corpus files are knowingly left stale.

**Tech Stack:** Python 3.9.25 (conda env `HP_2024`), JSON Schema draft-07, `jsonschema` 4.25.0, BioSTEAM 2.46.1 / thermosteam 0.45.0 (export source), stdlib `unittest` (pytest collects it).

## Global Constraints

Copied verbatim from the spec and CLAUDE.md. Every task's steps implicitly include these.

- **Python invocation:** never rely on `conda activate`; always call the env's interpreter directly: `& "C:\Users\saran\anaconda3\envs\HP_2024\python.exe" ...`. The bare `python` hits a Windows Store stub and fails.
- **`pisces_sff` is a live editable clone** in `HP_2024` — edits take effect with no reinstall.
- **Import-light tests:** schema/helper tests must NOT `import pisces_sff` (that pulls in biosteam via `_export`). Validate against the committed schema file with `jsonschema` directly, and load private modules by file path (see `tests/test_version_sync.py`).
- **Never run two simulation/export processes concurrently** — one sim in flight at a time, in a single tool call, never `run_in_background`. Concurrent sims corrupt the shared numba cache. On `ReferenceError: ... underlying object has vanished`, clear `*.PYC`/`*.nbc`/`*.nbi` per CLAUDE.md "Numba cache recovery", then re-run.
- **Out-of-repo files are read-only** (Bioindustrial-Park, biosteam, thermosteam). Only regenerable numba/`.pyc` caches may be deleted outside the repo.
- **New Python files start with the MIT copyright header** (see any existing module, e.g. `pisces_sff/_runner.py:1-7`).
- **Unit-string convention is BioSTEAM-native:** `kg/hr`, `kmol/hr`, `m3/hr`, `K`, `Pa`, `g/mol`, `USD`, `USD/kg`, `USD/kWh`, `USD/kmol`, `USD/kJ`, `kW`, `kJ/hr`. Pre-0.0.7 output keeps its exact legacy strings (`$/kg`, `kg/h`, `$/kmol`, `$/kJ`, `$/kWh`) — byte-stability of historical exporters is mandatory.
- **"units" always means unit operations.** Unit-of-measure information is always called "quantity units". Never introduce a field named `units` for measures.
- **Commit onto `dev`** (current branch), never `main`. Group logically. Last line of each commit message:
  `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`
- **Version bump is deliberate and user-approved** (0.0.6 → 0.0.7). `pisces_sff.__version__` follows the schema `version` field automatically — never hardcode it.
- **Run canonical validation before committing** any schema/exporter/flowsheet change. Its pass criterion changes mid-plan — see each task.

### Canonical validation commands (referenced throughout)

Corpus validation (fast, no sim):
```powershell
& "C:\Users\saran\anaconda3\envs\HP_2024\python.exe" -c "import glob,os; from pisces_sff import validate_json_against_schema as v; s='pisces_sff/schema/sff_schema.json'; r=[(os.path.basename(f),)+v(f,s) for f in sorted(glob.glob('pisces_sff/exported_flowsheets/bioindustrial_park/*.json'))]; [print(n,'OK' if ok else 'FAIL') for n,ok,e in r]; print('failures:', sum(1 for _,ok,_ in r if not ok))"
```

Fast test suite:
```powershell
& "C:\Users\saran\anaconda3\envs\HP_2024\python.exe" -m pytest tests -q
```

**Baseline before starting:** corpus `failures: 0` (19 files), fast suite `88 passed, 18 skipped`.

---

## File Structure

**New files**
- `pisces_sff/_quantity_units.py` — pure, import-light helpers: the `QUANTITY_UNITS_GLOBAL` registry constant, the `scalar()` formatter, version-style predicate, and `quantity_units_for_design_results()`. No biosteam import. One responsibility: the quantity-unit vocabulary and the version-gated scalar shape.
- `tests/test_quantity_units_helpers.py` — import-light unit tests for the helper module (loaded by file path).
- `tests/test_schema_quantity_units_global.py` — import-light schema-shape tests for the additive registry (Task 1).
- `tests/test_schema_quantity_units_0_0_7.py` — import-light schema-shape tests for the breaking 0.0.7 fields (Task 3).

**Modified files**
- `pisces_sff/schema/sff_schema.json` — additive registry (Task 1); breaking retypings/renames + version bump + `quantity_units_for_design_results` (Task 3).
- `pisces_sff/_export.py` — import helpers, make `_build_sff_dict` version-aware, add the `export_biosteam_flowsheet_sff_0_0_7` wrapper (Task 3).
- `pisces_sff/_harness.py` — `DEFAULT_SFF_VERSION` → `'0.0.7'` (Task 5).
- `pisces_sff/_runner.py` — `run_model_export` default, CLI default, docstring version → 0.0.7 (Task 5).
- `pisces_sff/exported_flowsheets/bioindustrial_park/corn_dry_grind_ethanol.json` — re-exported to 0.0.7 (Task 5).
- `tests/test_export_corn_dry_grind_ethanol.py` — version literals → 0.0.7, 0.0.7-shape assertions, 0.0.6 byte-stability guard (Task 5).
- `tests/test_end_to_end_export.py` — bare-number stream read, version references (Task 5).
- `docs/schema_reference.md`, `docs/full_schema.md` — mirror the schema change + 0.0.6 permalink (Task 3).
- `CLAUDE.md` (local, gitignored — not committed) — Known issues note about the stale corpus (Task 6).

---

## Task 1: Additive `quantity_units_global` registry in the schema

Purely additive: adds a top-level optional `quantity_units_global` property and a `definitions/quantity_unit_entry`. Schema stays at version 0.0.6; the corpus keeps validating. Independently reviewable — a reviewer can reject the registry shape without touching anything breaking.

**Files:**
- Modify: `pisces_sff/schema/sff_schema.json`
- Create: `tests/test_schema_quantity_units_global.py`

**Interfaces:**
- Produces: schema path `properties.quantity_units_global` and `definitions.quantity_unit_entry`, each `quantity_unit_entry` requiring `aliases` (non-empty string array) and `quantity_units` (string). Later tasks and the exporter emit values against this shape.

- [ ] **Step 1: Write the failing schema-shape test**

Create `tests/test_schema_quantity_units_global.py`:

```python
# -*- coding: utf-8 -*-
# Pins the additive `quantity_units_global` registry and its reusable
# `definitions/quantity_unit_entry`. Import-light: validates against the
# committed schema file with jsonschema directly, never importing pisces_sff
# (which would drag in biosteam via _export). See tests/test_schema_microorganisms.py
# for the same rationale.
#
# Why pinned: quantity_units_global is the single machine-readable source of
# units for every bare-number quantity in a v0.0.7 file. A consumer resolves a
# field (e.g. "T", "total_mass_flow") to a unit through the entry's `aliases`
# and `quantity_units`; if either is dropped or retyped, resolution breaks
# silently. The field is optional at the top level (a producer may omit it and
# fall back to documented defaults), so this suite proves the *shape*, not its
# presence in any particular file.

import json
import unittest
from pathlib import Path

from jsonschema import Draft7Validator

SCHEMA_PATH = (
    Path(__file__).resolve().parents[1]
    / "pisces_sff" / "schema" / "sff_schema.json"
)


def load_schema():
    with SCHEMA_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


class TestQuantityUnitsGlobalShape(unittest.TestCase):
    def setUp(self):
        self.schema = load_schema()

    def test_registry_is_an_optional_top_level_object(self):
        self.assertIn("quantity_units_global", self.schema["properties"])
        self.assertEqual(
            self.schema["properties"]["quantity_units_global"]["type"], "object"
        )
        # Optional: adding it must not force every existing file to carry it.
        self.assertNotIn("quantity_units_global", self.schema.get("required", []))

    def test_entry_definition_requires_aliases_and_quantity_units(self):
        entry = self.schema["definitions"]["quantity_unit_entry"]
        self.assertEqual(entry["type"], "object")
        self.assertEqual(sorted(entry["required"]), ["aliases", "quantity_units"])
        self.assertEqual(entry["properties"]["aliases"]["type"], "array")
        self.assertEqual(entry["properties"]["aliases"]["minItems"], 1)
        self.assertEqual(
            entry["properties"]["aliases"]["items"]["type"], "string"
        )
        self.assertEqual(entry["properties"]["quantity_units"]["type"], "string")

    def test_canonical_quantities_reference_the_entry_definition(self):
        # Every widely-used scalar and price the exporter emits must be declared.
        props = self.schema["properties"]["quantity_units_global"]["properties"]
        for key in ("temperature", "pressure", "mass_flow", "molar_flow",
                    "volumetric_flow", "molar_mass", "price",
                    "electrical_energy_price", "regeneration_price",
                    "heat_transfer_price"):
            with self.subTest(quantity=key):
                self.assertEqual(
                    props[key]["$ref"], "#/definitions/quantity_unit_entry"
                )

    def test_additional_quantities_also_use_the_entry_definition(self):
        # A producer may declare quantities beyond the canonical set.
        reg = self.schema["properties"]["quantity_units_global"]
        self.assertEqual(
            reg["additionalProperties"]["$ref"], "#/definitions/quantity_unit_entry"
        )


class TestQuantityUnitEntryValidation(unittest.TestCase):
    def setUp(self):
        schema = load_schema()
        # Resolve the $ref by validating against the whole schema's definition.
        self.validator = Draft7Validator(
            {"definitions": schema["definitions"],
             "$ref": "#/definitions/quantity_unit_entry"}
        )

    def assertValid(self, value):
        errors = list(self.validator.iter_errors(value))
        self.assertEqual(errors, [], msg=f"expected {value!r} to validate; got {errors}")

    def assertInvalid(self, value):
        self.assertNotEqual(list(self.validator.iter_errors(value)), [])

    def test_full_entry_validates(self):
        self.assertValid({"aliases": ["temperature", "T"], "quantity_units": "K"})

    def test_entry_without_aliases_is_rejected(self):
        self.assertInvalid({"quantity_units": "K"})

    def test_entry_with_empty_aliases_is_rejected(self):
        self.assertInvalid({"aliases": [], "quantity_units": "K"})

    def test_entry_without_quantity_units_is_rejected(self):
        self.assertInvalid({"aliases": ["temperature"]})


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test to verify it fails**

Run:
```powershell
& "C:\Users\saran\anaconda3\envs\HP_2024\python.exe" -m pytest tests/test_schema_quantity_units_global.py -q
```
Expected: FAIL — `KeyError: 'quantity_units_global'` / `KeyError: 'definitions'` (the schema has neither yet).

- [ ] **Step 3: Add `definitions` and `quantity_units_global` to the schema**

In `pisces_sff/schema/sff_schema.json`, add a top-level `"definitions"` block and a `"quantity_units_global"` property. Insert `quantity_units_global` inside the top-level `"properties"` object (e.g. immediately before `"metadata"`), and add `"definitions"` as a top-level sibling of `"properties"` (e.g. immediately before `"properties"`).

Top-level `definitions` (new sibling of `properties`):
```json
  "definitions": {
    "quantity_unit_entry": {
      "type": "object",
      "description": "A quantity-unit registry entry: the field names a quantity appears under, and its unit string.",
      "properties": {
        "aliases": {
          "type": "array",
          "items": { "type": "string" },
          "minItems": 1,
          "description": "Field names this quantity appears under in the flowsheet (so a consumer can resolve, e.g., 'T' or 'total_mass_flow' to this quantity)."
        },
        "quantity_units": {
          "type": "string",
          "description": "Unit string for this quantity (BioSTEAM default)."
        }
      },
      "required": ["aliases", "quantity_units"]
    }
  },
```

`quantity_units_global` (new entry inside `properties`):
```json
    "quantity_units_global": {
      "description": "Global default quantity units for widely-used quantities, keyed by canonical quantity name. 'aliases' lists the field names each quantity appears under across this flowsheet (so a consumer can resolve, e.g., 'T' or 'total_mass_flow' to its quantity units); 'quantity_units' is the unit string. Values of these quantities appear as bare numbers elsewhere in the flowsheet and take their units from here. Note: 'units' in this schema always means unit operations; unit-of-measure information is always called 'quantity units'.",
      "type": "object",
      "properties": {
        "temperature":             { "$ref": "#/definitions/quantity_unit_entry" },
        "pressure":                { "$ref": "#/definitions/quantity_unit_entry" },
        "mass_flow":               { "$ref": "#/definitions/quantity_unit_entry" },
        "molar_flow":              { "$ref": "#/definitions/quantity_unit_entry" },
        "volumetric_flow":         { "$ref": "#/definitions/quantity_unit_entry" },
        "molar_mass":              { "$ref": "#/definitions/quantity_unit_entry" },
        "price":                   { "$ref": "#/definitions/quantity_unit_entry" },
        "electrical_energy_price": { "$ref": "#/definitions/quantity_unit_entry" },
        "regeneration_price":      { "$ref": "#/definitions/quantity_unit_entry" },
        "heat_transfer_price":     { "$ref": "#/definitions/quantity_unit_entry" }
      },
      "additionalProperties": { "$ref": "#/definitions/quantity_unit_entry" }
    },
```

- [ ] **Step 4: Run the test to verify it passes**

Run:
```powershell
& "C:\Users\saran\anaconda3\envs\HP_2024\python.exe" -m pytest tests/test_schema_quantity_units_global.py -q
```
Expected: PASS.

- [ ] **Step 5: Run canonical validation — must still be green (additive change)**

Run the corpus-validation command and the fast suite (both under "Canonical validation commands" above).
Expected: corpus `failures: 0` (still 19 files); fast suite `89 passed, 18 skipped` (the +1 is this new test file's classes collapsed into pytest's count — confirm it rose and nothing regressed).

- [ ] **Step 6: Commit**

```bash
git add pisces_sff/schema/sff_schema.json tests/test_schema_quantity_units_global.py
git commit -m "schema: add additive quantity_units_global registry

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: Import-light `_quantity_units.py` helper module

The pure, biosteam-free helpers the exporter will use: the registry constant, the version-gated `scalar()` formatter, the version-style predicate, and `quantity_units_for_design_results()`. Isolating them in their own module keeps them unit-testable at fast-suite speed (a test that imported `_export` would drag in biosteam). Independently reviewable: the vocabulary and the scalar-shape decision live here and nowhere else.

**Files:**
- Create: `pisces_sff/_quantity_units.py`
- Create: `tests/test_quantity_units_helpers.py`

**Interfaces:**
- Produces (imported by `_export.py` in Task 3):
  - `QUANTITY_UNITS_GLOBAL: dict[str, dict]` — canonical quantity → `{"aliases": list[str], "quantity_units": str}`.
  - `scalar(value, units, inline)` → `{"value": value, "units": units}` when `inline` else `value`.
  - `version_tuple(version: str)` → `tuple[int, ...]` (e.g. `"0.0.7"` → `(0, 0, 7)`).
  - `uses_inline_scalar_style(version: str)` → `bool` — `True` iff `version_tuple(version) < (0, 0, 7)`.
  - `quantity_units_for_design_results(unit)` → `dict[str, str]` mapping each `design_results` key to its `_units` string (or `""`).

- [ ] **Step 1: Write the failing helper tests**

Create `tests/test_quantity_units_helpers.py`:

```python
# -*- coding: utf-8 -*-
# Unit tests for pisces_sff/_quantity_units.py — the pure quantity-unit helpers.
#
# Import-light by construction: the module under test imports no biosteam, and
# we load it by file path (like tests/test_version_sync.py loads _version.py) so
# that importing the pisces_sff package — and thus _export/biosteam — never
# happens here.

import importlib.util
import unittest
from pathlib import Path

MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "pisces_sff" / "_quantity_units.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location(
        "pisces_sff_quantity_units_under_test", MODULE_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Fake:
    """Stand-in for a BioSTEAM unit: only the attributes the helper reads."""
    def __init__(self, design_results=None, units=None):
        if design_results is not None:
            self.design_results = design_results
        if units is not None:
            self._units = units


class TestScalar(unittest.TestCase):
    def setUp(self):
        self.m = load_module()

    def test_inline_returns_value_units_pair(self):
        self.assertEqual(self.m.scalar(5.0, "K", True),
                         {"value": 5.0, "units": "K"})

    def test_non_inline_returns_bare_value(self):
        self.assertEqual(self.m.scalar(5.0, "K", False), 5.0)


class TestVersionStyle(unittest.TestCase):
    def setUp(self):
        self.m = load_module()

    def test_version_tuple_parses_semver(self):
        self.assertEqual(self.m.version_tuple("0.0.7"), (0, 0, 7))

    def test_pre_0_0_7_is_inline(self):
        self.assertTrue(self.m.uses_inline_scalar_style("0.0.5"))
        self.assertTrue(self.m.uses_inline_scalar_style("0.0.6"))

    def test_0_0_7_and_later_are_not_inline(self):
        self.assertFalse(self.m.uses_inline_scalar_style("0.0.7"))
        self.assertFalse(self.m.uses_inline_scalar_style("0.1.0"))


class TestRegistry(unittest.TestCase):
    def setUp(self):
        self.m = load_module()

    def test_every_entry_has_nonempty_aliases_and_a_unit_string(self):
        for key, entry in self.m.QUANTITY_UNITS_GLOBAL.items():
            with self.subTest(quantity=key):
                self.assertIsInstance(entry["aliases"], list)
                self.assertTrue(entry["aliases"])
                self.assertTrue(all(isinstance(a, str) for a in entry["aliases"]))
                self.assertIsInstance(entry["quantity_units"], str)
                self.assertTrue(entry["quantity_units"])

    def test_canonical_units_are_biosteam_native(self):
        reg = self.m.QUANTITY_UNITS_GLOBAL
        self.assertEqual(reg["temperature"]["quantity_units"], "K")
        self.assertEqual(reg["pressure"]["quantity_units"], "Pa")
        self.assertEqual(reg["mass_flow"]["quantity_units"], "kg/hr")
        self.assertEqual(reg["molar_flow"]["quantity_units"], "kmol/hr")
        self.assertEqual(reg["volumetric_flow"]["quantity_units"], "m3/hr")
        self.assertEqual(reg["molar_mass"]["quantity_units"], "g/mol")
        self.assertEqual(reg["price"]["quantity_units"], "USD/kg")
        self.assertEqual(reg["electrical_energy_price"]["quantity_units"], "USD/kWh")
        self.assertEqual(reg["regeneration_price"]["quantity_units"], "USD/kmol")
        self.assertEqual(reg["heat_transfer_price"]["quantity_units"], "USD/kJ")

    def test_aliases_cover_biosteam_attribute_names(self):
        reg = self.m.QUANTITY_UNITS_GLOBAL
        self.assertIn("T", reg["temperature"]["aliases"])
        self.assertIn("temperature_limit", reg["temperature"]["aliases"])
        self.assertIn("total_mass_flow", reg["mass_flow"]["aliases"])
        self.assertIn("F_mass", reg["mass_flow"]["aliases"])
        self.assertIn("total_molar_flow", reg["molar_flow"]["aliases"])
        self.assertIn("total_volumetric_flow", reg["volumetric_flow"]["aliases"])
        self.assertIn("MW", reg["molar_mass"]["aliases"])


class TestDesignResultUnits(unittest.TestCase):
    def setUp(self):
        self.m = load_module()

    def test_maps_each_design_key_to_its_unit_or_empty_string(self):
        unit = _Fake(design_results={"Area": 10.0, "Duty": 5.0},
                     units={"Area": "m^2"})
        self.assertEqual(
            self.m.quantity_units_for_design_results(unit),
            {"Area": "m^2", "Duty": ""},
        )

    def test_unit_without_design_results_yields_empty_dict(self):
        self.assertEqual(self.m.quantity_units_for_design_results(_Fake()), {})


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:
```powershell
& "C:\Users\saran\anaconda3\envs\HP_2024\python.exe" -m pytest tests/test_quantity_units_helpers.py -q
```
Expected: FAIL — `FileNotFoundError` / import error (the module does not exist yet).

- [ ] **Step 3: Create the helper module**

Create `pisces_sff/_quantity_units.py`:

```python
# -*- coding: utf-8 -*-
# Code to export flowsheets from multiple tools into a standardized JSON format.
# Copyright (C) 2025-, Sarang S. Bhagwat <sarangbhagwat.developer@gmail.com>
#
# This module is under the MIT open-source license. See
# https://github.com/sustainability-software-lab/pisces-standard-flowsheet-format/blob/main/LICENSE
# for license details.

"""
Quantity-unit vocabulary and version-gated scalar shape for the SFF exporter.

Deliberately import-light — no biosteam/thermosteam — so schema-level tests and
the exporter share one source of truth for units without paying the simulator
import cost. 'units' in SFF always means unit operations; unit-of-measure
information is always called 'quantity units'.
"""

__all__ = (
    "QUANTITY_UNITS_GLOBAL",
    "scalar",
    "version_tuple",
    "uses_inline_scalar_style",
    "quantity_units_for_design_results",
)

#: First schema version that reports scalars as bare numbers (units resolved via
#: QUANTITY_UNITS_GLOBAL) instead of inline {"value", "units"} pairs.
_BARE_SCALAR_SINCE = (0, 0, 7)

#: Global default quantity units, keyed by canonical quantity name. `aliases`
#: lists every field name the quantity appears under across a flowsheet (so a
#: consumer can resolve, e.g., 'T' or 'total_mass_flow' to its unit); values are
#: BioSTEAM-native unit strings.
QUANTITY_UNITS_GLOBAL = {
    "temperature":             {"aliases": ["temperature", "T", "temperature_limit"], "quantity_units": "K"},
    "pressure":                {"aliases": ["pressure", "P"], "quantity_units": "Pa"},
    "mass_flow":               {"aliases": ["mass_flow", "total_mass_flow", "F_mass"], "quantity_units": "kg/hr"},
    "molar_flow":              {"aliases": ["molar_flow", "total_molar_flow", "F_mol"], "quantity_units": "kmol/hr"},
    "volumetric_flow":         {"aliases": ["volumetric_flow", "total_volumetric_flow", "F_vol"], "quantity_units": "m3/hr"},
    "molar_mass":              {"aliases": ["molar_mass", "MW"], "quantity_units": "g/mol"},
    "price":                   {"aliases": ["price"], "quantity_units": "USD/kg"},
    "electrical_energy_price": {"aliases": ["electrical_energy_price"], "quantity_units": "USD/kWh"},
    "regeneration_price":      {"aliases": ["regeneration_price"], "quantity_units": "USD/kmol"},
    "heat_transfer_price":     {"aliases": ["heat_transfer_price"], "quantity_units": "USD/kJ"},
}


def scalar(value, units, inline):
    """
    Format a scalar quantity for an SFF document.

    Parameters
    ----------
    value : number
        The scalar value.
    units : str
        Unit string, used only in the inline shape.
    inline : bool
        If True, return the pre-0.0.7 ``{"value", "units"}`` pair; otherwise
        return the bare ``value`` (its units come from ``QUANTITY_UNITS_GLOBAL``).

    Returns
    -------
    dict or number
    """
    return {"value": value, "units": units} if inline else value


def version_tuple(version):
    """
    Parse a semantic-version string into a tuple of ints; e.g. ``'0.0.7'`` ->
    ``(0, 0, 7)``.
    """
    return tuple(int(part) for part in str(version).split("."))


def uses_inline_scalar_style(version):
    """
    Return True if `version` predates the bare-number scalar shape (i.e. is
    older than 0.0.7 and must emit inline ``{"value", "units"}`` pairs).
    """
    return version_tuple(version) < _BARE_SCALAR_SINCE


def quantity_units_for_design_results(unit):
    """
    Map each of a unit operation's ``design_results`` keys to its unit string.

    Sourced from the simulator's per-design-result units (BioSTEAM ``_units``).
    A key present in ``design_results`` but absent from ``_units`` maps to ``''``
    (dimensionless or unspecified).

    Parameters
    ----------
    unit : object
        A unit operation exposing ``design_results`` and ``_units`` mappings.

    Returns
    -------
    dict of str -> str
    """
    units_map = getattr(unit, "_units", {}) or {}
    design = getattr(unit, "design_results", {}) or {}
    return {key: units_map.get(key, "") for key in design}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:
```powershell
& "C:\Users\saran\anaconda3\envs\HP_2024\python.exe" -m pytest tests/test_quantity_units_helpers.py -q
```
Expected: PASS (all classes green).

- [ ] **Step 5: Run the fast suite — nothing else regresses**

Run:
```powershell
& "C:\Users\saran\anaconda3\envs\HP_2024\python.exe" -m pytest tests -q
```
Expected: PASS; count risen from Task 1 by the new tests, still `18 skipped`.

- [ ] **Step 6: Commit**

```bash
git add pisces_sff/_quantity_units.py tests/test_quantity_units_helpers.py
git commit -m "exporter: add import-light quantity-unit helpers

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: Breaking 0.0.7 schema + version bump + exporter + docs (one commit)

The atomic version-bump commit. Per the version protocol this bundles the three parts (schema `version`, a new `export_biosteam_flowsheet_sff_0_0_7`, and a docs permalink to 0.0.6) with the breaking field retypings/renames, the new per-unit `quantity_units_for_design_results`, the version-aware exporter wiring, and the human-readable docs mirror.

**This task intentionally makes the corpus stale.** After it, corpus validation reports **19 failures** (all committed files are old-shape against the 0.0.7 schema); Task 5 re-exports corn to bring it to 18. This is the recorded, expected consequence — not a regression.

**Files:**
- Modify: `pisces_sff/schema/sff_schema.json`
- Modify: `pisces_sff/_export.py`
- Modify: `docs/schema_reference.md`, `docs/full_schema.md`
- Create: `tests/test_schema_quantity_units_0_0_7.py`

**Interfaces:**
- Consumes: `pisces_sff._quantity_units.{QUANTITY_UNITS_GLOBAL, scalar, uses_inline_scalar_style, quantity_units_for_design_results}` (Task 2); `definitions.quantity_unit_entry` (Task 1).
- Produces: `export_biosteam_flowsheet_sff_0_0_7(sys, filepath, tea=None, stoichiometry="dict", composition_units="both", microorganisms=None, reproducibility=None, sff_version='0.0.7')`; schema `version == "0.0.7"`; the 0.0.7 document shape (bare-number scalars, `quantity_units_global`, per-unit `quantity_units_for_design_results`, renamed utility-results key, `electrical_energy_price`).

### Part A — the version-aware exporter (no behavior change until 0.0.7 is dispatched)

- [ ] **Step 1: Import the helpers in `_export.py`**

In `pisces_sff/_export.py`, after the existing imports (around line 22, after `import biosteam as bst`), add:

```python
from ._quantity_units import (
    QUANTITY_UNITS_GLOBAL,
    scalar,
    uses_inline_scalar_style,
    quantity_units_for_design_results,
)
```

- [ ] **Step 2: Compute the scalar style once in `_build_sff_dict`**

In `_build_sff_dict`, immediately after `if tea is None: tea = sys.TEA` (currently `_export.py:150-151`), add:

```python
    # Pre-0.0.7 emits inline {"value","units"} scalars and the legacy field
    # names; 0.0.7+ emits bare numbers whose units live in quantity_units_global.
    # Older exporters must stay byte-stable so historical exports reproduce, so
    # every version-dependent shape below is gated on this one flag.
    inline = uses_inline_scalar_style(sff_version)
    results_key = "units_for_utility_results" if inline else "quantity_units_for_utility_results"
```

- [ ] **Step 3: Route the unit block's design-result units (0.0.7 only)**

Replace the unit-dict append (currently `_export.py:216-228`) so the new parallel field is added only when not inline. Change:

```python
        unit = {"id": ru.ID,
                "unit_type": get_unit_type(ru),
                "design_input_specs": get_design_input_specs(ru),
                "design_simulation_method": get_design_simulation_method(ru),
                "thermo_property_package": get_thermo(ru),
                "reactions": get_reactions(ru, stoichiometry=stoichiometry),
                "design_results": ru.design_results if hasattr(ru, 'design_results') else {},
                "installed_costs": ru.installed_costs if hasattr(ru, 'installed_costs') else {},
                "purchase_costs": ru.purchase_costs if hasattr(ru, 'purchase_costs') else {},
                "utility_consumption_results": u_cons,
                "utility_production_results": u_prod,
                }
        units.append(unit)
```
to:
```python
        unit = {"id": ru.ID,
                "unit_type": get_unit_type(ru),
                "design_input_specs": get_design_input_specs(ru),
                "design_simulation_method": get_design_simulation_method(ru),
                "thermo_property_package": get_thermo(ru),
                "reactions": get_reactions(ru, stoichiometry=stoichiometry),
                "design_results": ru.design_results if hasattr(ru, 'design_results') else {},
                "installed_costs": ru.installed_costs if hasattr(ru, 'installed_costs') else {},
                "purchase_costs": ru.purchase_costs if hasattr(ru, 'purchase_costs') else {},
                "utility_consumption_results": u_cons,
                "utility_production_results": u_prod,
                }
        if not inline:
            unit["quantity_units_for_design_results"] = quantity_units_for_design_results(ru)
        units.append(unit)
```

- [ ] **Step 4: Route stream scalars through `scalar()`**

Replace the stream block (currently `_export.py:235-254`). Change:

```python
        stream = {"id": rs.ID,
                  "source_unit_id": rs.source.ID if rs.source is not None else "None",
                  "sink_unit_id": rs.sink.ID if rs.sink is not None else "None",
                  "price": {"value": rs.price, "units": "$/kg"},
                  "stream_properties": {
                      "total_mass_flow": {"value": rs.F_mass, "units": "kg/h"},
                      "total_molar_flow": {"value": rs.F_mol, "units": "kmol/h"},
                      "temperature": {"value": rs.T, "units": "K"},
                      "pressure": {"value": rs.P, "units": "Pa"},
                      "composition": get_composition(rs),
                      }
                  }
        try:
            stream["stream_properties"]["total_volumetric_flow"] = {"value": rs.F_vol, "units": "m3/h"}
        except Exception as e:
            if 'liquid molar volume method' in str(e).lower():
                pass
            else:
                breakpoint()
        streams.append(stream)
```
to:
```python
        stream = {"id": rs.ID,
                  "source_unit_id": rs.source.ID if rs.source is not None else "None",
                  "sink_unit_id": rs.sink.ID if rs.sink is not None else "None",
                  "price": scalar(rs.price, "$/kg", inline),
                  "stream_properties": {
                      "total_mass_flow": scalar(rs.F_mass, "kg/h", inline),
                      "total_molar_flow": scalar(rs.F_mol, "kmol/h", inline),
                      "temperature": scalar(rs.T, "K", inline),
                      "pressure": scalar(rs.P, "Pa", inline),
                      "composition": get_composition(rs),
                      }
                  }
        try:
            stream["stream_properties"]["total_volumetric_flow"] = scalar(rs.F_vol, "m3/h", inline)
        except Exception as e:
            if 'liquid molar volume method' in str(e).lower():
                pass
            else:
                breakpoint()
        streams.append(stream)
```

> Note: the legacy unit strings (`"$/kg"`, `"kg/h"`, …) are passed to `scalar()` but only surface in the `inline=True` branch, so pre-0.0.7 output stays byte-identical; in the 0.0.7 branch the value is bare and the string is discarded. Key insertion order is unchanged, preserving byte-stability.

- [ ] **Step 5: Route heat-utility scalars and rename the results key**

Replace the heat-utility loop body (currently `_export.py:278-289`). Change:

```python
    for hu_agent in all_hu_agents:
        hu = {
              "id": hu_agent.ID,
              "temperature": {"value": hu_agent.T, "units": "K"},
              "pressure": {"value": hu_agent.P, "units": "Pa"},
              "regeneration_price": {"value": hu_agent.regeneration_price, "units": "$/kmol"},
              "heat_transfer_price": {"value": hu_agent.heat_transfer_price, "units": "$/kJ"},
              "heat_transfer_efficiency": hu_agent.heat_transfer_efficiency if hu_agent.heat_transfer_efficiency is not None else 1.0,
              "composition": get_composition(hu_agent),
              "units_for_utility_results": "kJ/h",
              }
        heat_utilities.append(hu)
```
to:
```python
    for hu_agent in all_hu_agents:
        hu = {
              "id": hu_agent.ID,
              "temperature": scalar(hu_agent.T, "K", inline),
              "pressure": scalar(hu_agent.P, "Pa", inline),
              "regeneration_price": scalar(hu_agent.regeneration_price, "$/kmol", inline),
              "heat_transfer_price": scalar(hu_agent.heat_transfer_price, "$/kJ", inline),
              "heat_transfer_efficiency": hu_agent.heat_transfer_efficiency if hu_agent.heat_transfer_efficiency is not None else 1.0,
              "composition": get_composition(hu_agent),
              }
        hu[results_key] = "kJ/h" if inline else "kJ/hr"
        heat_utilities.append(hu)
```

- [ ] **Step 6: Route the power-utility price rename and results key**

Replace the power-utility loop body (currently `_export.py:292-297`). Change:

```python
    for pu_agent in all_pu_agents:
        pu = {"id": "Marginal grid electricity",
              "price": {"value": pu_agent.price, "units": "$/kWh"},
              "units_for_utility_results": "kW",
              }
        power_utilities.append(pu)
```
to:
```python
    for pu_agent in all_pu_agents:
        pu = {"id": "Marginal grid electricity"}
        if inline:
            pu["price"] = {"value": pu_agent.price, "units": "$/kWh"}
        else:
            pu["electrical_energy_price"] = pu_agent.price
        pu[results_key] = "kW"
        power_utilities.append(pu)
```

- [ ] **Step 7: Route other-utility scalars and results key (preserving key order)**

Replace the other-utility loop body (currently `_export.py:300-309`). Note the legacy order places the results key **before** `composition`; preserve it. Change:

```python
    for ou_agent in all_ou_agents:
        ou = {
              "id": ou_agent.ID,
              "temperature": {"value": ou_agent.T, "units": "K"},
              "pressure": {"value": ou_agent.P, "units": "Pa"},
              "price": {"value": ou_agent.price or ng_price, "units": "$/kg"},
              "units_for_utility_results": "kg/h",
              "composition": get_composition(ou_agent),
              }
        other_utilities.append(ou)
```
to:
```python
    for ou_agent in all_ou_agents:
        ou = {
              "id": ou_agent.ID,
              "temperature": scalar(ou_agent.T, "K", inline),
              "pressure": scalar(ou_agent.P, "Pa", inline),
              "price": scalar(ou_agent.price or ng_price, "$/kg", inline),
              }
        ou[results_key] = "kg/h" if inline else "kg/hr"
        ou["composition"] = get_composition(ou_agent)
        other_utilities.append(ou)
```

- [ ] **Step 8: Add `quantity_units_global` to the returned document (0.0.7 only)**

Replace the return statement (currently `_export.py:311-318`). Change:

```python
    return {"metadata": metadata,
            "units": units,
            "streams": streams,
            "chemicals": chemicals,
            "utilities": {"heat_utilities": heat_utilities,
                          "power_utilities": power_utilities,
                          "other_utilities": other_utilities},
            }
```
to:
```python
    document = {"metadata": metadata,
                "units": units,
                "streams": streams,
                "chemicals": chemicals,
                "utilities": {"heat_utilities": heat_utilities,
                              "power_utilities": power_utilities,
                              "other_utilities": other_utilities},
                }
    if not inline:
        document["quantity_units_global"] = QUANTITY_UNITS_GLOBAL
    return document
```

- [ ] **Step 9: Add the `export_biosteam_flowsheet_sff_0_0_7` wrapper**

In `pisces_sff/_export.py`, after `export_biosteam_flowsheet_sff_0_0_6` (ends `_export.py:391`) and before `#%% Helper functions`, add:

```python
#%% Export function for SFF schema v0.0.7
def export_biosteam_flowsheet_sff_0_0_7(sys, filepath, tea=None,
                                        stoichiometry="dict", # must be one of (None, "vector", "dict")
                                        composition_units="both", # "mol%", "mass%", or "both"
                                        microorganisms=None, # optional list of microbial hosts
                                        reproducibility=None, # optional recipe block; see pisces_sff._runner
                                        sff_version='0.0.7', # must match this function's name suffix
                                        ):
    """
    Export a simulated BioSTEAM system against SFF schema v0.0.7.

    Identical to the v0.0.6 exporter except for the quantity-unit shape the
    shared builder emits at this version: scalars and prices are bare numbers
    whose units are declared once in the top-level ``quantity_units_global``
    registry, each unit operation carries ``quantity_units_for_design_results``,
    the power-utility price is ``electrical_energy_price``, and the utility
    results-unit key is ``quantity_units_for_utility_results``.

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
        Recipe block written to ``metadata['reproducibility']``. Built by
        :func:`pisces_sff._runner.build_reproducibility`. Omitted when falsy.
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

- [ ] **Step 10: Confirm the exporter refactor didn't break the fast suite (schema still 0.0.6)**

Run:
```powershell
& "C:\Users\saran\anaconda3\envs\HP_2024\python.exe" -m pytest tests -q
```
Expected: PASS. `tests/test_version_sync.py` stays green — schema is still 0.0.6, the 0_0_6 exporter still exists, and the new 0_0_7 exporter defaults to `'0.0.7'` (matching its name). Corpus validation is still `failures: 0` (0.0.5/0.0.6 output byte-stable, corpus untouched, schema still 0.0.6). Do **not** commit yet — the version bump lands atomically in Part C.

### Part B — the breaking schema edits

- [ ] **Step 11: Write the failing 0.0.7 schema-shape test**

Create `tests/test_schema_quantity_units_0_0_7.py`:

```python
# -*- coding: utf-8 -*-
# Pins the breaking v0.0.7 quantity-unit shape in the committed schema.
#
# Import-light (jsonschema on the committed file, never importing pisces_sff).
# Why pinned: v0.0.7 drops inline {"value","units"} scalars in favour of bare
# numbers resolved through quantity_units_global, renames the utility results-
# unit key, renames the power-utility price, and adds a per-unit-operation
# quantity_units_for_design_results. Each is a public-contract change a consumer
# parses against; a silent revert here would desynchronise producers and readers.

import json
import unittest
from pathlib import Path

from jsonschema import Draft7Validator

SCHEMA_PATH = (
    Path(__file__).resolve().parents[1]
    / "pisces_sff" / "schema" / "sff_schema.json"
)


def load_schema():
    with SCHEMA_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


class TestSchemaVersion(unittest.TestCase):
    def test_version_is_0_0_7(self):
        self.assertEqual(load_schema()["version"], "0.0.7")


class TestScalarsAreBareNumbers(unittest.TestCase):
    def setUp(self):
        self.schema = load_schema()

    def test_stream_price_is_a_number(self):
        price = self.schema["properties"]["streams"]["items"]["properties"]["price"]
        self.assertEqual(price["type"], "number")

    def test_stream_properties_scalars_are_numbers(self):
        props = (self.schema["properties"]["streams"]["items"]
                 ["properties"]["stream_properties"]["properties"])
        for key in ("total_mass_flow", "total_molar_flow",
                    "total_volumetric_flow", "temperature", "pressure"):
            with self.subTest(field=key):
                self.assertEqual(props[key]["type"], "number")
        # temperature keeps its physical floor.
        self.assertEqual(props["temperature"]["minimum"], 0)

    def test_stream_properties_required_is_preserved(self):
        sp = (self.schema["properties"]["streams"]["items"]
              ["properties"]["stream_properties"])
        self.assertEqual(
            sorted(sp["required"]),
            ["pressure", "temperature", "total_molar_flow"],
        )

    def test_heat_utility_scalars_are_numbers(self):
        props = (self.schema["properties"]["utilities"]["properties"]
                 ["heat_utilities"]["items"]["properties"])
        for key in ("temperature", "pressure", "regeneration_price",
                    "heat_transfer_price", "temperature_limit"):
            with self.subTest(field=key):
                self.assertEqual(props[key]["type"], "number")


class TestRenamedUtilityKeys(unittest.TestCase):
    def setUp(self):
        self.util = load_schema()["properties"]["utilities"]["properties"]

    def test_heat_utility_uses_quantity_units_key(self):
        items = self.util["heat_utilities"]["items"]
        self.assertIn("quantity_units_for_utility_results", items["properties"])
        self.assertNotIn("units_for_utility_results", items["properties"])
        self.assertIn("quantity_units_for_utility_results", items["required"])
        self.assertNotIn("units_for_utility_results", items["required"])

    def test_power_utility_price_is_renamed_electrical_energy_price(self):
        items = self.util["power_utilities"]["items"]
        self.assertIn("electrical_energy_price", items["properties"])
        self.assertNotIn("price", items["properties"])
        self.assertEqual(
            items["properties"]["electrical_energy_price"]["type"], "number"
        )
        self.assertIn("quantity_units_for_utility_results", items["properties"])

    def test_other_utility_uses_quantity_units_key(self):
        items = self.util["other_utilities"]["items"]
        self.assertIn("quantity_units_for_utility_results", items["properties"])
        self.assertNotIn("units_for_utility_results", items["properties"])
        self.assertIn("quantity_units_for_utility_results", items["required"])


class TestDesignResultUnitsField(unittest.TestCase):
    def test_units_declare_quantity_units_for_design_results(self):
        unit = load_schema()["properties"]["units"]["items"]["properties"]
        field = unit["quantity_units_for_design_results"]
        self.assertEqual(field["type"], "object")
        self.assertEqual(field["additionalProperties"]["type"], "string")


class TestOldShapeIsRejected(unittest.TestCase):
    """A whole-document validator proves the retypings actually bite."""

    def setUp(self):
        self.validator = Draft7Validator(load_schema())

    def _minimal(self):
        # A minimal-but-valid v0.0.7 document; individual tests corrupt one field.
        return {
            "metadata": {
                "sff_version": "0.0.7", "TEA_year": 2020,
                "process_simulator": {"name": "BioSTEAM", "version": "2.46.1"},
                "feedstocks": [{"stream_id": "corn"}],
                "products": [{"stream_id": "ethanol"}],
            },
            "units": [{"id": "U1", "unit_type": "Mixer",
                       "quantity_units_for_design_results": {"Area": "m^2"}}],
            "streams": [{"id": "s1", "source_unit_id": "U1", "sink_unit_id": "None",
                         "price": 0.1,
                         "stream_properties": {
                             "total_molar_flow": 1.0, "temperature": 300.0,
                             "pressure": 101325.0}}],
            "utilities": {"heat_utilities": [], "power_utilities": [],
                          "other_utilities": []},
        }

    def test_minimal_v0_0_7_document_validates(self):
        self.assertEqual(list(self.validator.iter_errors(self._minimal())), [])

    def test_inline_price_pair_is_rejected(self):
        doc = self._minimal()
        doc["streams"][0]["price"] = {"value": 0.1, "units": "$/kg"}
        self.assertNotEqual(list(self.validator.iter_errors(doc)), [])

    def test_legacy_utility_results_key_is_rejected(self):
        doc = self._minimal()
        doc["utilities"]["heat_utilities"] = [{
            "id": "hps", "temperature": 500.0, "pressure": 101325.0,
            "composition": [], "units_for_utility_results": "kJ/h"}]
        self.assertNotEqual(list(self.validator.iter_errors(doc)), [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 12: Run the 0.0.7 schema test to verify it fails**

Run:
```powershell
& "C:\Users\saran\anaconda3\envs\HP_2024\python.exe" -m pytest tests/test_schema_quantity_units_0_0_7.py -q
```
Expected: FAIL — version is still `0.0.6`, scalars are still objects, keys not yet renamed.

- [ ] **Step 13: Bump the schema version**

In `pisces_sff/schema/sff_schema.json`, change `"version": "0.0.6"` to `"version": "0.0.7"` (line 4).

- [ ] **Step 14: Retype stream `price` and `stream_properties` scalars to bare numbers**

In the `streams.items.properties` block, replace the `price` object schema (currently `_export`… i.e. schema `_export` lines 355-366) with:
```json
          "price": {
            "type": "number",
            "description": "Price per unit mass of the stream material. Quantity units are declared in the top-level 'quantity_units_global' under 'price' (default 'USD/kg')."
          },
```
Then, inside `stream_properties.properties`, replace each of the five scalar objects with bare-number schemas:
```json
              "total_mass_flow": {
                "type": "number",
                "description": "Total mass flow rate. Quantity units: quantity_units_global 'mass_flow' (default 'kg/hr')."
              },
              "total_volumetric_flow": {
                "type": "number",
                "description": "Total volumetric flow rate. Quantity units: quantity_units_global 'volumetric_flow' (default 'm3/hr')."
              },
              "total_molar_flow": {
                "type": "number",
                "description": "Total molar flow rate. Quantity units: quantity_units_global 'molar_flow' (default 'kmol/hr')."
              },
              "temperature": {
                "type": "number",
                "minimum": 0,
                "description": "Temperature. Quantity units: quantity_units_global 'temperature' (default 'K')."
              },
              "pressure": {
                "type": "number",
                "description": "Pressure. Quantity units: quantity_units_global 'pressure' (default 'Pa')."
              },
```
Leave `composition` and the `stream_properties.required` list (`total_molar_flow`, `temperature`, `pressure`) unchanged.

- [ ] **Step 15: Add `quantity_units_for_design_results` to the unit schema**

In `units.items.properties`, immediately after the `design_results` property (schema block ending at line 296), add:
```json
          "quantity_units_for_design_results": {
            "type": "object",
            "additionalProperties": { "type": "string" },
            "description": "Quantity units for each key in 'design_results', by the same key. Sourced from the simulator's per-design-result unit strings (BioSTEAM '_units'). A key mapped to '' is dimensionless or has no declared unit."
          },
```
`units.items.additionalProperties` stays `false`, so this declaration is what lets the exporter emit the field.

- [ ] **Step 16: Retype heat-utility scalars and rename the results key**

In `utilities.properties.heat_utilities.items.properties`, replace the `temperature`, `pressure`, `regeneration_price`, `heat_transfer_price`, and `temperature_limit` objects with bare-number schemas, and rename `units_for_utility_results` → `quantity_units_for_utility_results`:
```json
                  "temperature": {
                    "type": "number",
                    "description": "Temperature. Quantity units: quantity_units_global 'temperature' (default 'K')."
                  },
                  "pressure": {
                    "type": "number",
                    "description": "Pressure. Quantity units: quantity_units_global 'pressure' (default 'Pa')."
                  },
                  "regeneration_price": {
                    "type": "number",
                    "default": 0,
                    "description": "Regeneration price. Quantity units: quantity_units_global 'regeneration_price' (default 'USD/kmol')."
                  },
                  "heat_transfer_price": {
                    "type": "number",
                    "default": 0,
                    "description": "Heat-transfer price. Quantity units: quantity_units_global 'heat_transfer_price' (default 'USD/kJ')."
                  },
                  "heat_transfer_efficiency": {
                    "type": "number",
                    "default": 1
                  },
                  "temperature_limit": {
                    "type": "number",
                    "description": "Temperature limit. Quantity units: quantity_units_global 'temperature' (default 'K')."
                  },
```
(Leave `composition` unchanged, positioned as before.) Rename the results-unit property:
```json
                  "quantity_units_for_utility_results": {
                    "type": "string",
                    "description": "Quantity units (e.g., 'kJ/hr') for this utility's per-unit-operation values in 'utility_consumption_results'/'utility_production_results'."
                  }
```
Update this items' `required` list from `["id","temperature","pressure","composition","units_for_utility_results"]` to `["id","temperature","pressure","composition","quantity_units_for_utility_results"]`. `additionalProperties` stays `false`.

- [ ] **Step 17: Rename the power-utility price and results key**

In `utilities.properties.power_utilities.items.properties`, replace the `price` object with:
```json
                  "electrical_energy_price": {
                    "type": "number",
                    "default": 0,
                    "description": "Electrical energy price. Quantity units: quantity_units_global 'electrical_energy_price' (default 'USD/kWh')."
                  },
```
and rename `units_for_utility_results` → `quantity_units_for_utility_results`:
```json
                  "quantity_units_for_utility_results": {
                    "type": "string",
                    "description": "Quantity units (e.g., 'kW') for this utility's per-unit-operation values in 'utility_consumption_results'/'utility_production_results'."
                  }
```
Update `required` from `["id","units_for_utility_results"]` to `["id","quantity_units_for_utility_results"]`. `additionalProperties` stays `{ "type": "number" }`.

- [ ] **Step 18: Retype other-utility scalars and rename the results key**

In `utilities.properties.other_utilities.items.properties`, replace `temperature`, `pressure`, and `price` with bare-number schemas and rename the results key:
```json
                  "temperature": {
                    "type": "number",
                    "description": "Temperature. Quantity units: quantity_units_global 'temperature' (default 'K')."
                  },
                  "pressure": {
                    "type": "number",
                    "description": "Pressure. Quantity units: quantity_units_global 'pressure' (default 'Pa')."
                  },
                  "price": {
                    "type": "number",
                    "default": 0,
                    "description": "Price per unit mass. Quantity units: quantity_units_global 'price' (default 'USD/kg')."
                  },
```
(Leave `composition` unchanged.) Rename:
```json
                  "quantity_units_for_utility_results": {
                    "type": "string",
                    "description": "Quantity units (e.g., 'kg/hr') for this utility's per-unit-operation values in 'utility_consumption_results'/'utility_production_results'."
                  }
```
Update `required` from `["id","temperature","pressure","composition","units_for_utility_results"]` to `["id","temperature","pressure","composition","quantity_units_for_utility_results"]`. `additionalProperties` stays `false`.

- [ ] **Step 19: Run the 0.0.7 schema test to verify it passes**

Run:
```powershell
& "C:\Users\saran\anaconda3\envs\HP_2024\python.exe" -m pytest tests/test_schema_quantity_units_0_0_7.py tests/test_schema_quantity_units_global.py tests/test_version_sync.py -q
```
Expected: PASS. `test_version_sync` now sees schema `0.0.7` and the `export_biosteam_flowsheet_sff_0_0_7` function (added in Part A), so `test_current_schema_version_has_an_exporter` and `test_each_exporter_defaults_to_the_version_in_its_name` are green.

### Part C — docs + validation + commit

- [ ] **Step 20: Add the 0.0.6 permalink to `docs/full_schema.md`**

Under `## Previous versions`, add a new first bullet (the 0.0.6 schema lives at commit `ec5d2be`, the last commit before this bump):
```markdown
* [v0.0.6](https://github.com/sustainability-software-lab/pisces-standard-flowsheet-format/blob/ec5d2be2dc0da403d42306cfe0520fc2da13c91f/pisces_sff/schema/sff_schema.json)
```

- [ ] **Step 21: Mirror the change in `docs/schema_reference.md`**

Update the human-readable mirror:
- Add a new bullet to the "Core Properties" list (and a short section) for `quantity_units_global`: "A registry of default quantity units for widely-used quantities and prices, keyed by canonical name; each entry carries the `aliases` a quantity appears under and its `quantity_units` string. Bare numeric quantities elsewhere in the file resolve their units here."
- Under **Units (Nodes)**, add: "**quantity_units_for_design_results**: Quantity units for each key in `design_results`, by the same key (from the simulator's `_units`)."
- Under **Utilities**, change "results unit" / "electricity price" wording to name `quantity_units_for_utility_results` and `electrical_energy_price`.
- Under **Streams (Edges)**, change **price** and the `stream_properties` bullets to note the values are bare numbers whose units come from `quantity_units_global` (BioSTEAM-native `USD/kg`, `kg/hr`, `K`, `Pa`, `kmol/hr`, `m3/hr`).

- [ ] **Step 22: Run the full fast suite**

Run:
```powershell
& "C:\Users\saran\anaconda3\envs\HP_2024\python.exe" -m pytest tests -q
```
Expected: PASS, `18 skipped`. All schema/version/helper tests green.

- [ ] **Step 23: Run corpus validation — expect the recorded 19 failures**

Run the corpus-validation command.
Expected: `failures: 19`. This is the intended known-stale state: every committed corpus file is old-shape against the 0.0.7 schema. Task 5 re-exports `corn_dry_grind_ethanol.json` to bring this to 18. **Do not** "fix" the other 18 or edit the schema to make them pass.

- [ ] **Step 24: Commit the atomic version bump**

```bash
git add pisces_sff/schema/sff_schema.json pisces_sff/_export.py \
        docs/full_schema.md docs/schema_reference.md \
        tests/test_schema_quantity_units_0_0_7.py
git commit -m "schema: quantity units + bump to v0.0.7 (breaking)

Retype stream/utility scalars and prices to bare numbers resolved via the
new top-level quantity_units_global registry; add per-unit-operation
quantity_units_for_design_results (from BioSTEAM _units); rename
units_for_utility_results -> quantity_units_for_utility_results and the
power-utility price -> electrical_energy_price. Add
export_biosteam_flowsheet_sff_0_0_7 and a permalink to the 0.0.6 schema.
Pre-0.0.7 exporter output stays byte-stable via the version gate.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: (folded into Task 5)

Harness/runner default bumps are a prerequisite of re-exporting corn to 0.0.7, so they live in Task 5.

---

## Task 5: Bump defaults, re-export corn to 0.0.7, update simulating tiers

Bumps the harness/runner export defaults to 0.0.7, re-exports the single corpus file the spec approves (`corn_dry_grind_ethanol.json`) through the reproducible harness, and updates the two simulating test tiers — including a Tier-2 byte-stability guard proving the 0.0.6 exporter still emits the inline shape. **Simulates — keep strictly sequential, one process at a time, never in the background.**

**Files:**
- Modify: `pisces_sff/_harness.py:46`, `pisces_sff/_runner.py` (lines 169, 265, docstring 138)
- Modify: `pisces_sff/exported_flowsheets/bioindustrial_park/corn_dry_grind_ethanol.json`
- Modify: `tests/test_export_corn_dry_grind_ethanol.py`, `tests/test_end_to_end_export.py`

**Interfaces:**
- Consumes: `export_biosteam_flowsheet_sff_0_0_7` (Task 3), the 0.0.7 schema (Task 3).
- Produces: a committed 0.0.7 `corn_dry_grind_ethanol.json` that validates; `DEFAULT_SFF_VERSION == '0.0.7'`.

- [ ] **Step 1: Bump the harness and runner defaults**

- `pisces_sff/_harness.py:46`: `DEFAULT_SFF_VERSION = '0.0.6'` → `DEFAULT_SFF_VERSION = '0.0.7'`.
- `pisces_sff/_runner.py:169`: `def run_model_export(model_dir, output_path, sff_version='0.0.6', env_key=None):` → `sff_version='0.0.7'`.
- `pisces_sff/_runner.py:265`: `parser.add_argument('--sff-version', default='0.0.6',` → `default='0.0.7'`.
- `pisces_sff/_runner.py:138` (docstring): `Conforming to metadata.reproducibility in SFF v0.0.6.` → `... in SFF v0.0.7.`

- [ ] **Step 2: Update the Tier 2 test — version literals, 0.0.7-shape assertions, and the 0.0.6 guard**

In `tests/test_export_corn_dry_grind_ethanol.py`:

Change `setUpClass` (currently line 55) to load the system once and export **both** versions from it, so the 0.0.6 guard costs no extra simulation. Replace lines 48-57:
```python
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
```
with:
```python
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
```
Change the version assertion (currently line 68):
```python
        self.assertEqual(self.flowsheet["metadata"]["sff_version"], "0.0.6")
```
to:
```python
        self.assertEqual(self.flowsheet["metadata"]["sff_version"], "0.0.7")
```
Add these methods to the class (0.0.7-shape assertions plus the 0.0.6 byte-stability guard):
```python
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
```

- [ ] **Step 3: Update the Tier 3 test — bare-number stream read**

In `tests/test_end_to_end_export.py`, change the mass-flow read (line 95) from:
```python
        flows = {s["id"]: s["stream_properties"]["total_mass_flow"]["value"]
                 for s in self.flowsheet["streams"]}
```
to:
```python
        flows = {s["id"]: s["stream_properties"]["total_mass_flow"]
                 for s in self.flowsheet["streams"]}
```
The numeric baselines (`n_units`, `stream_mass_flows` values, `total_installed_cost`) are unaffected by the shape change and stay as-is; `test_total_installed_cost_matches_the_baseline` reads `installed_costs.values()`, which is unchanged.

- [ ] **Step 4: Re-export the corn corpus file to 0.0.7 (single simulation)**

Re-export through the reproducible harness so the `reproducibility` block stays faithful (this is how the committed file was produced). Run exactly one process, in the foreground:
```powershell
& "C:\Users\saran\anaconda3\envs\HP_2024\python.exe" -c "from pathlib import Path; from pisces_sff import export_model; md=Path('pisces_sff/models/biosteam_models/corn_dry_grind_ethanol'); out=Path('pisces_sff/exported_flowsheets/bioindustrial_park/corn_dry_grind_ethanol.json'); export_model(md, out); print('re-exported', out)"
```
If this raises `ReferenceError: ... underlying object has vanished`, clear the numba caches per CLAUDE.md "Numba cache recovery", then re-run this one command. Expect it to be slow on a cold cache (env provision + simulate + numba compile).

- [ ] **Step 5: Verify the re-exported file is 0.0.7 and validates**

Run:
```powershell
& "C:\Users\saran\anaconda3\envs\HP_2024\python.exe" -c "import json; from pisces_sff import validate_json_against_schema as v; f='pisces_sff/exported_flowsheets/bioindustrial_park/corn_dry_grind_ethanol.json'; s='pisces_sff/schema/sff_schema.json'; d=json.load(open(f)); print('version', d['metadata']['sff_version']); print('has registry', 'quantity_units_global' in d); ok,e=v(f,s); print('valid', ok, e[:3])"
```
Expected: `version 0.0.7`, `has registry True`, `valid True []`.

- [ ] **Step 6: Corpus validation — now 18 failures (only the untouched files)**

Run the corpus-validation command.
Expected: `failures: 18` — `corn_dry_grind_ethanol.json` now passes; the other 18 remain knowingly stale. Confirm `corn_dry_grind_ethanol.json` prints `OK`.

- [ ] **Step 7: Run the Tier 2 simulating test**

Run (one simulating process, foreground):
```powershell
$env:SFF_TEST_BIOSTEAM = "1"; & "C:\Users\saran\anaconda3\envs\HP_2024\python.exe" -m pytest tests/test_export_corn_dry_grind_ethanol.py -q; $env:SFF_TEST_BIOSTEAM = $null
```
Expected: all Tier 2 tests PASS, including the new 0.0.7-shape assertions and the 0.0.6 byte-stability guard.

- [ ] **Step 8: Confirm the fast suite is still green**

Run:
```powershell
& "C:\Users\saran\anaconda3\envs\HP_2024\python.exe" -m pytest tests -q
```
Expected: PASS, `18 skipped`.

- [ ] **Step 9: Commit**

```bash
git add pisces_sff/_harness.py pisces_sff/_runner.py \
        pisces_sff/exported_flowsheets/bioindustrial_park/corn_dry_grind_ethanol.json \
        tests/test_export_corn_dry_grind_ethanol.py tests/test_end_to_end_export.py
git commit -m "corpus: re-export corn to v0.0.7; bump export defaults; update tiers

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

> **Optional (only if the user asks to lock the pinned pins):** run Tier 3 to re-record baselines against the pinned environment. This provisions a conda env (tens of minutes). Do **not** run it as part of the default flow.
> ```powershell
> $env:SFF_TEST_E2E = "1"; & "C:\Users\saran\anaconda3\envs\HP_2024\python.exe" -m pytest tests/test_end_to_end_export.py -q; $env:SFF_TEST_E2E = $null
> ```

---

## Task 6: Record the known-stale corpus in the local working doc

The spec requires noting the deliberate 18-file staleness so a future session doesn't "discover" it as a regression. The repo's Known-issues list lives in `CLAUDE.md`, which is `.gitignore`d — this is a **local, uncommitted** edit.

**Files:**
- Modify: `CLAUDE.md` (local only — not committed)

- [ ] **Step 1: Update the Known issues list**

In `CLAUDE.md`, under "Known issues", update issue #1 (the `sff_version` note) to record: as of the v0.0.7 bump, `corn_dry_grind_ethanol.json` reports `sff_version: "0.0.7"` and uses the new bare-number quantity-unit shape; the other 18 files remain old-shape (`sff_version: "0.0.3"`, inline `{value, units}`) and therefore **fail** validation against the 0.0.7 schema. Canonical corpus validation now expects `failures: 18` (not 0) until the deferred corpus refresh — this is intended, not a regression.

- [ ] **Step 2: Update the canonical-validation pass criterion note**

In `CLAUDE.md`, under "Canonical validation" → check 1, note that the current expected result is `failures: 18` (18 stale pre-0.0.7 corpus files), with only `corn_dry_grind_ethanol.json` passing, until the corpus is refreshed.

- [ ] **Step 3: No commit**

`CLAUDE.md` is `.gitignore`d; leave it uncommitted. This task has no git step.

---

## Self-Review

**Spec coverage** (spec §-by-§):
- §4.1 version bump → Task 3 Step 13. ✓
- §4.2 `quantity_units_global` + `quantity_unit_entry` (additive, top-level, canonical content) → Task 1 (schema) + Task 2 (`QUANTITY_UNITS_GLOBAL` content) + exporter emits it Task 3 Step 8. ✓
- §4.3 renamed/retyped fields (streams, heat/power/other utilities, results-key rename, `electrical_energy_price`) → Task 3 Steps 14, 16, 17, 18. ✓
- §4.3 `stream_properties.required` preserved, temperature `minimum: 0` kept → Task 3 Step 14 + test Step 11. ✓
- §4.4 `quantity_units_for_design_results` (schema + `_units` sourcing, `""` fallback) → Task 3 Step 15 (schema) + Task 2 helper + Task 3 Step 3 (exporter). ✓
- §5 version-aware `_build_sff_dict` via `scalar()`, `inline = version < (0,0,7)`, gated key names/strings, module constant, `get_quantity_units_for_design_results`, 0_0_7 wrapper → Task 2 + Task 3 Part A. ✓
- §5 harness/runner default bumps → Task 5 Step 1. ✓
- §6 re-export only corn via harness → Task 5 Step 4. ✓
- §7 test updates (version literals, version-sync, new schema tests, optional 0.0.6 guard sized) → Tasks 1, 2, 3, 5. The optional guard is implemented as a Tier-2 dual-export reusing one simulation (Task 5 Step 2), the cheapest faithful option (a fake System would have to satisfy dozens of biosteam methods; a second sim would double Tier-2 cost). ✓
- §8 docs (`schema_reference.md`, `full_schema.md` permalink) in the schema commit → Task 3 Steps 20-21. ✓
- §2 known-stale corpus recorded → Task 6. ✓
- §9 out-of-scope (other 18 files, `quantity_units_for_design_input_specs`, unrelated known issues) → untouched. ✓

**Placeholder scan:** no TBD/TODO/"handle edge cases"/"similar to Task N" — every code and schema step carries literal content. ✓

**Type consistency:** helper names are identical across Task 2 (definitions), Task 3 Step 1 (import), and their call sites (Steps 3-8): `QUANTITY_UNITS_GLOBAL`, `scalar`, `uses_inline_scalar_style`, `quantity_units_for_design_results`. `results_key` is defined once (Step 2) and used in Steps 5-7. The 0_0_7 exporter signature in Task 3 Step 9 matches how `export_biosteam_flowsheet` dispatches (name-based) and how Task 5 Step 2/4 invoke it (via `export_biosteam_flowsheet(..., sff_version=...)` and `export_model`). Byte-stability of the `inline=True` branch is asserted by Task 5 Step 2's guard. ✓

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-08-11-quantity-units.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration. Note: Tasks 1-3 and 6 are non-simulating; Task 5 simulates and must run sequentially (no concurrent sims — numba-cache constraint), so its steps run in one foreground pass.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints for review.

**Which approach?**
