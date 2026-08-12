# Design: Quantity Units for the SFF Schema (v0.0.7)

**Date:** 2026-08-11
**Status:** Approved (design) — pending implementation plan
**Schema version:** 0.0.6 → **0.0.7** (breaking)

---

## 1. Problem

SFF attaches units only to flows, temperature, pressure, and prices — as
`{value, units}` pairs. Many numeric quantities carry **no machine-readable
unit** at all: `design_results` (areas, duties, volumes, weights, power…),
`design_input_specs`, `purchase_costs`/`installed_costs`, and `molar_mass` are
bare numbers whose units live, at best, in a prose description. Where units *are*
reported, the vocabulary is ad hoc (`$/kg`, `kg/h`) and the field name `units`
collides conceptually with the schema's use of "units" for **unit operations**.

We want one clean, consistent, machine-readable way to define the units of every
numerical quantity in an SFF file, defaulting to BioSTEAM's conventions, without
ever overloading the word "units" (which stays reserved for unit operations).

## 2. Goals

- Call unit-of-measure information **"quantity units"** everywhere; never "units".
- A single global registry of quantity units for widely-used scalar quantities,
  carrying both the canonical unit and the aliases a quantity is known by.
- Every previously unit-less numeric quantity becomes resolvable to a unit.
- BioSTEAM-native unit strings as defaults (`kg/hr`, `K`, `Pa`, `USD`, …).
- Additive where possible; the one unavoidable breaking part (field renames) is
  contained behind a schema version bump.

## 3. Decisions (settled)

| Decision | Choice |
| --- | --- |
| Version | **Bump to 0.0.7** — full three-part change (schema `version`, new `export_biosteam_flowsheet_sff_0_0_7`, docs permalink to 0.0.6). |
| Corpus | **Re-export only `corn_dry_grind_ethanol.json`** to 0.0.7 (via the harness; numbers unchanged). The other 18 stay untouched and **will not validate against 0.0.7** — a known-stale state pending the upcoming corpus refresh. |
| `quantity_units_global` placement | **Top-level** sibling of `metadata`/`units`/`streams`/`chemicals`/`utilities`. |
| Unit-string convention | **BioSTEAM-native**: `kg/hr`, `kmol/hr`, `m3/hr`, `K`, `Pa`, `g/mol`, `USD`, `USD/kg`, `USD/kWh`, `USD/kmol`, `USD/kJ`, `kW`, `kJ/hr`. Existing `/h`→`/hr`, `$`→`USD`. |
| Per-value scalar units on streams/utilities | **Dropped.** Those scalars become bare numbers; their units come from `quantity_units_global`. |
| Price quantity units | **Also in `quantity_units_global`.** Price values become bare numbers too. |

**Consequence recorded on purpose:** after this change the canonical validation
(`failures: 0` across all corpus files) will report **18 failures** until the
corpus is refreshed. This is expected and will be noted in the repo's "Known
issues" list, not treated as a regression.

## 4. Schema changes (`pisces_sff/schema/sff_schema.json`)

### 4.1 `version`
`"0.0.6"` → `"0.0.7"`. `pisces_sff.__version__` follows automatically.

### 4.2 New top-level `quantity_units_global` (optional)

A registry keyed by canonical quantity name; each entry has `aliases`
(the names the quantity appears under, so a consumer can map e.g. `"T"` or
`"total_mass_flow"` back to a canonical quantity) and `quantity_units` (its
BioSTEAM-default unit string). Optional at the top level: a producer that omits
it leaves consumers to fall back to the documented defaults, but the reference
exporter always emits it.

```json
"quantity_units_global": {
  "description": "Global default quantity units for widely-used quantities, keyed by canonical quantity name. 'aliases' lists the field names each quantity appears under across this flowsheet (so a consumer can resolve, e.g., 'T' or 'total_mass_flow' to its quantity units); 'quantity_units' is the unit string. Values of these quantities appear as bare numbers elsewhere in the flowsheet and take their units from here. Note: 'units' in this schema always means unit operations; unit-of-measure information is always called 'quantity units'.",
  "type": "object",
  "properties": {
    "temperature":            { "$ref": "#/definitions/quantity_unit_entry" },
    "pressure":               { "$ref": "#/definitions/quantity_unit_entry" },
    "mass_flow":              { "$ref": "#/definitions/quantity_unit_entry" },
    "molar_flow":             { "$ref": "#/definitions/quantity_unit_entry" },
    "volumetric_flow":        { "$ref": "#/definitions/quantity_unit_entry" },
    "molar_mass":             { "$ref": "#/definitions/quantity_unit_entry" },
    "price":                  { "$ref": "#/definitions/quantity_unit_entry" },
    "electrical_energy_price":{ "$ref": "#/definitions/quantity_unit_entry" },
    "regeneration_price":     { "$ref": "#/definitions/quantity_unit_entry" },
    "heat_transfer_price":    { "$ref": "#/definitions/quantity_unit_entry" }
  },
  "additionalProperties": { "$ref": "#/definitions/quantity_unit_entry" }
}
```

with a reusable definition:

```json
"definitions": {
  "quantity_unit_entry": {
    "type": "object",
    "properties": {
      "aliases": {
        "type": "array",
        "items": { "type": "string" },
        "minItems": 1,
        "description": "Field names this quantity appears under in the flowsheet."
      },
      "quantity_units": {
        "type": "string",
        "description": "Unit string for this quantity (BioSTEAM default)."
      }
    },
    "required": ["aliases", "quantity_units"]
  }
}
```

Canonical content the exporter emits (aliases chosen to cover every field name
these quantities appear under, including BioSTEAM attribute names):

| Canonical key | aliases | quantity_units |
| --- | --- | --- |
| `temperature` | `temperature`, `T`, `temperature_limit` | `K` |
| `pressure` | `pressure`, `P` | `Pa` |
| `mass_flow` | `mass_flow`, `total_mass_flow`, `F_mass` | `kg/hr` |
| `molar_flow` | `molar_flow`, `total_molar_flow`, `F_mol` | `kmol/hr` |
| `volumetric_flow` | `volumetric_flow`, `total_volumetric_flow`, `F_vol` | `m3/hr` |
| `molar_mass` | `molar_mass`, `MW` | `g/mol` |
| `price` | `price` | `USD/kg` |
| `electrical_energy_price` | `electrical_energy_price` | `USD/kWh` |
| `regeneration_price` | `regeneration_price` | `USD/kmol` |
| `heat_transfer_price` | `heat_transfer_price` | `USD/kJ` |

### 4.3 Renamed / restructured fields (the breaking part)

| Location | 0.0.6 | 0.0.7 |
| --- | --- | --- |
| stream | `price: {value, units}` | `price: <number>` (units via global `price`) |
| stream `stream_properties` | `total_mass_flow/total_molar_flow/total_volumetric_flow/temperature/pressure: {value, units}` | each a bare `<number>` (units via global) |
| heat utility | `temperature/pressure/regeneration_price/heat_transfer_price/temperature_limit: {value, units}` | each a bare `<number>` |
| heat utility | `units_for_utility_results` | `quantity_units_for_utility_results` |
| power utility | `price: {value, units: "$/kWh"}` | `electrical_energy_price: <number>` |
| power utility | `units_for_utility_results` | `quantity_units_for_utility_results` |
| other utility | `temperature/pressure/price: {value, units}` | each a bare `<number>` |
| other utility | `units_for_utility_results` | `quantity_units_for_utility_results` |
| chemical | `molar_mass: <number>` | unchanged shape; units now declared in global |

`quantity_units_for_utility_results` keeps its convention (a single string naming
the units of that utility's per-unit-operation result values) — its only changes
are the rename and BioSTEAM-native strings (`kJ/hr`, `kW`, `kg/hr`).

`stream_properties.required` (`total_molar_flow`, `temperature`, `pressure`)
stays, now as bare numbers. `temperature` keeps `minimum: 0`.

### 4.4 New `quantity_units_for_design_results` (per unit operation, optional)

A parallel object to `design_results`, mapping the **same keys** to their unit
strings, sourced from the BioSTEAM unit's `_units` attribute. Keys present in
`design_results` but absent from `_units` map to `""` (dimensionless or
unspecified). Additive and optional; `additionalProperties: {type: string}`.

```json
"quantity_units_for_design_results": {
  "type": "object",
  "additionalProperties": { "type": "string" },
  "description": "Quantity units for each key in 'design_results', by the same key. Sourced from the simulator's per-design-result unit strings (BioSTEAM '_units'). A key mapped to '' is dimensionless or has no declared unit."
}
```

No `quantity_units_for_design_input_specs`: those parameters are either global
scalars (temperature, pressure), dimensionless (recoveries), or qualitative
(key pairs), per the request.

## 5. Exporter changes (`pisces_sff/_export.py`)

The shared `_build_sff_dict` becomes **version-aware** rather than being copied.
0.0.5/0.0.6 output must remain byte-stable (older exporters exist so historical
exports stay reproducible), so the new behavior is gated behind a style flag.

- Derive a style once: `inline = version < (0, 0, 7)` (parse the `sff_version`
  string). `inline=True` reproduces today's `{value, units}` / `$` / `/h` /
  `units_for_utility_results` output exactly; `inline=False` produces the 0.0.7
  shape.
- Route every scalar through one helper:
  ```python
  def _scalar(value, units, inline):
      """Format a scalar quantity: {'value','units'} for <0.0.7, else the bare value."""
      return {"value": value, "units": units} if inline else value
  ```
  Applied at every stream/utility scalar and price site. This keeps the shape
  divergence in one place instead of scattered conditionals.
- Version-gate the utility-results key name and the unit strings
  (`units_for_utility_results`/`$`/`/h` vs
  `quantity_units_for_utility_results`/`USD`/`/hr`).
- When `inline=False`, add `quantity_units_global` (a module-level constant
  registry) to the returned document, and add
  `quantity_units_for_design_results` to each unit via a new helper:
  ```python
  def get_quantity_units_for_design_results(unit):
      units_map = getattr(unit, "_units", {}) or {}
      return {k: units_map.get(k, "") for k in (getattr(unit, "design_results", {}) or {})}
  ```
- Add a thin `export_biosteam_flowsheet_sff_0_0_7` wrapper mirroring the 0.0.6
  one (default `sff_version='0.0.7'`, forwards `reproducibility`).

`DEFAULT_SFF_VERSION` in `_harness.py` and the `sff_version` default in
`_runner.py` move to `'0.0.7'`.

## 6. Corpus

Re-export **`pisces_sff/exported_flowsheets/bioindustrial_park/corn_dry_grind_ethanol.json`**
to 0.0.7 via the reproducible harness (`pisces_sff.export_model`), preserving the
reproducibility contract. Numbers are unchanged; only quantity-unit shape and the
`sff_version` label move. The other 18 files are left as-is.

## 7. Tests

- `tests/test_export_corn_dry_grind_ethanol.py`: bump the two `"0.0.6"` literals
  to `"0.0.7"`.
- `tests/test_end_to_end_export.py`: bump version references; baselines
  (`n_units`, installed-cost sum) are unaffected by unit-shape changes and stay.
- `tests/test_version_sync.py`: satisfied by adding
  `export_biosteam_flowsheet_sff_0_0_7` with a matching default.
- New import-light schema test (follows `tests/test_schema_microorganisms.py`):
  pins `quantity_units_global` shape (entry has `aliases` + `quantity_units`),
  the canonical keys/units, and the `quantity_units_for_design_results` parallel
  shape — explaining *why* each is pinned.
- Optional guard: a test asserting the 0.0.6 exporter still emits the inline
  shape (`units_for_utility_results`, `{value, units}`), so the version gate
  can't silently regress older output. Feasible only with a simulation or a
  lightweight fake system; flagged for the plan to size.

## 8. Docs

Same commit as the schema change:
- `docs/schema_reference.md`: mirror the new/renamed fields and
  `quantity_units_global`.
- `docs/full_schema.md`: add a commit-pinned permalink to the 0.0.6 schema under
  "Previous versions".

## 9. Out of scope

- Regenerating the other 18 corpus flowsheets (deferred to the corpus refresh).
- `quantity_units_for_design_input_specs`.
- Fixing unrelated known issues (`breakpoint()` calls, dead `composition_units`,
  docs layout drift), except where directly touched.

## 10. Open questions

None — all forks resolved during brainstorming.
