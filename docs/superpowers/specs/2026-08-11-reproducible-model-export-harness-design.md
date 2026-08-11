# Reproducible model export harness + SFF v0.0.6 reproducibility block

**Date:** 2026-08-11
**Status:** Design approved; implementation not started
**Scope:** `pisces_sff/models/`, `pisces_sff/_harness.py`, `pisces_sff/_runner.py`,
`pisces_sff/_export.py`, `pisces_sff/schema/sff_schema.json`, `tests/`, `docs/`

---

## 1. Problem

Exported SFF flowsheets today are not reproducible by anyone but the machine that
produced them, and the SFF file itself records nothing about how it was made
beyond `metadata.process_simulator`.

Four concrete gaps were confirmed while exploring the current setup:

1. **The environment is not captured by the environment.** `biosteam` and
   `biorefineries` resolve to local clones only because of a user-level
   `PYTHONPATH`:

   ```
   PYTHONPATH=...\fermentation_insights;...\biosteam;...\nskinetics;...\Bioindustrial-Park;
   ```

   `conda env export` captures none of this. Neither package appears in
   `pip list`. A trailing `;` yields an empty entry, which resolves to the
   current working directory — this is also how `pisces_sff` itself is imported.

2. **There is no recorded load procedure.** The only precedent is
   `_superseded/.../examples_for_export.py`, a scratch file of per-system cells,
   which is not part of this repository and is not referenced by any export.

3. **`PYTHONPATH` bypasses pip's dependency resolution**, so declared package
   requirements have never been enforced on this machine. `Bioindustrial-Park`
   declares `install_requires=['biosteam>=2.53.0', 'scikit-learn', 'SALib',
   'seaborn']`, yet the working HP_2024 environment has **biosteam 2.46.1** and
   has **neither SALib nor seaborn installed at all**. The declaration overstates
   real requirements and cannot be trusted as input to an installer.

4. **The exported corpus cannot be regenerated on demand.** The 18 committed
   flowsheets have no recorded provenance tying them to simulator versions or to
   a load script.

## 2. Goals

- A committed, per-model recipe (pinned environment spec + load script) that
  reconstructs the environment and re-runs the simulation from scratch.
- Export execution physically constrained to the pinned environment, so a
  recipe cannot claim pins it did not use.
- The SFF file carries the recipe inline, so a consumer holding only the JSON can
  rebuild and re-run.
- Architecture open to non-BioSTEAM simulators without rework.
- First model delivered end to end: **`corn_dry_grind_ethanol`**.

## 3. Non-goals

- Regenerating the 18 committed flowsheets. Out of scope; requires separate
  explicit sign-off per CLAUDE.md.
- Fixing the three `breakpoint()` calls in `_export.py` (known issue #2). The
  harness neutralizes them at runtime instead; see §8.
- Reconciling the other documented known issues (dead `composition_units`
  parameter, stale docs, `mkdocs.yml` URLs).
- Containerization. Conda environments are the chosen boundary.

## 4. Decisions

| # | Decision | Rationale |
|---|---|---|
| D1 | Curated minimal `environment.yml`, every dependency pinned | A `conda env export` of HP_2024 carries Windows-specific build strings and ~300 lines of unrelated tooling (spyder, qt, jupyterlab); it will not install on Linux CI |
| D2 | Recipe embedded inline in the SFF, with `sha256` and repo-relative path | A JSON pulled into the PISCES database in isolation stays reproducible; the hash detects drift against the committed file |
| D3 | `load.py` exposes `load() -> (system, tea)`; a shared runner performs the export | Export policy lives in one place instead of being copy-pasted across 18+ models |
| D4 | Pin `biosteam@e2d3942…`, `Bioindustrial-Park@5842328…` | Both reachable on public remotes; `5842328` is on `master` history, so it cannot rot the way a feature branch can |
| D5 | Fresh conda env per unique dependency set, keyed by content hash | Models with identical pins share one env; the YAML is proven by being used |
| D6 | Bump schema to **v0.0.6** | Additive optional property; without a bump, consumers cannot tell whether reproducibility data was even expressible |
| D7 | `--no-deps` in the pip block, all transitive deps pinned explicitly | Prevents BIP's `biosteam>=2.53.0` from silently replacing the biosteam pin (see §1.3) |
| D8 | Tests import biosteam, including a full end-to-end run | Explicitly requested; tiered and gated so the default suite stays fast |

### 4.1 Rejected alternatives

- **Exact freeze of HP_2024** — maximum fidelity, but Windows-only build strings
  make it uninstallable elsewhere.
- **Reference recipe files by path only, no inline content** — leaner SFF files,
  but a JSON on its own stops being reproducible.
- **Run exports in HP_2024 and treat the YAML as declared** — would be provably
  false here: HP_2024 has BIP `6c22326`, not the pin.
- **Pin BIP to `temp_isobutanol`** — a feature branch; upstream deletion would
  make the SHA unfetchable.
- **`definitions`/`$ref` for the repeated package shape** — the schema uses no
  `$ref` anywhere today; naive downstream parsers should not have to resolve
  references.

## 5. Architecture

```
pisces_sff/
├── _harness.py                          # parent: resolve/create env, launch child
├── _runner.py                           # child: load → export → embed → validate
└── models/
    ├── __init__.py
    └── biosteam_models/
        ├── __init__.py
        └── corn_dry_grind_ethanol/
            ├── environment.yml
            └── load.py
```

`models/biosteam_models/` is organizational. Dispatch is driven by the `SIMULATOR`
declaration inside `load.py`, not by directory name, so `models/superpro_models/…`
requires no runner change (relevant to the unmerged `feat/superpro-local-export`
branch).

### 5.1 `load.py` contract

```python
SIMULATOR = 'biosteam'                    # selects the export entry point
SIMULATOR_PACKAGE = 'biosteam'            # → metadata.reproducibility.simulator_package
FLOWSHEET_MODEL_PACKAGE = 'biorefineries' # → metadata.reproducibility.flowsheet_model_package
MODEL_NAME = 'corn_dry_grind_ethanol'
EXPORT_KWARGS = {
    'microorganisms': [{'name': 'Saccharomyces cerevisiae', 'label': 'ethanologen'}],
    'stoichiometry': 'dict',
}

def load():
    """Return (system, tea), simulated and ready to export."""
```

The dry-grind process ferments via simultaneous saccharification and fermentation
(`units.SSF`), whose reaction is `Glucose -> 2 Ethanol + 2 CO2` with a `Yeast`
growth reaction — hence the single yeast host above.

For corn the body is `br = corn.Biorefinery()` returning `(br.corn_sys,
br.corn_tea)`; `Biorefinery.__new__` already simulates and solves IRR. An
`if __name__ == '__main__':` block makes the file runnable standalone, so the
embedded copy is self-sufficient and debugging needs no harness.

### 5.2 `_harness.py` (parent; runs in any environment)

Public entry point `export_model(model_dir, output_path, *, recreate_env=False)`:

1. Read `environment.yml` bytes. Canonicalize (parse YAML, drop `name`/`prefix`,
   dump with sorted keys), sha256 → `env_key`. Env name is `sff-<env_key[:12]>`.
2. If that env does not exist, `conda env create -n sff-<key12> -f <yml>`.
   **On failure, remove the partial env** — otherwise a broken env matches the
   hash and is reused indefinitely.
3. Launch the child:
   `<env_prefix>/python.exe -m pisces_sff._runner --model-dir … --output …`
   with a scrubbed environment: `PYTHONPATH` set to **exactly the repo root**,
   `CONDA_PREFIX`/`CONDA_DEFAULT_ENV` cleared, `PYTHONBREAKPOINT=0` set.
4. Stream child stdout/stderr; raise on non-zero exit.

Setting `PYTHONPATH` to the repo root alone is what stops the clones from
shadowing the pinned installs, while keeping `pisces_sff` live-editable rather
than pinning the exporter against itself.

Environment provisioning is the one deliberately conda-shaped component, kept
behind a narrow interface so another simulator can supply a different
provisioner without touching the runner or the schema.

### 5.3 `_runner.py` (child; runs inside the pinned environment)

1. Import `load.py` by file path via `importlib`.
2. Resolve the export entry point by name from `SIMULATOR`
   (`export_{SIMULATOR}_flowsheet`), mirroring the existing name-based version
   dispatch in `_export.py`.
3. `system, tea = load()` — this performs the simulation.
4. Assemble the reproducibility payload (§6).
5. Call the exporter **once**, passing `sff_version='0.0.6'`, `tea=tea`,
   `reproducibility=<payload>`, `**EXPORT_KWARGS`. The exporter remains the sole
   writer of the JSON.
6. Validate the written file against the schema. On failure, leave the file in
   place for inspection and exit non-zero.

## 6. Schema change (v0.0.6)

One new **optional** property, `metadata.reproducibility`. Optional and additive,
so all 18 committed flowsheets continue to validate unchanged.

Placement under `metadata` is deliberate: it is provenance, alongside `source_doi`
and `process_simulator`. Note that `metadata` declares
`"additionalProperties": {"type": "string"}`, so an object-valued property
**must** be explicitly declared — it cannot be added implicitly.

```jsonc
"reproducibility": {
  "type": "object",
  "description": "Everything needed to rebuild the environment and re-run the model that produced this flowsheet.",
  "properties": {
    "environment": {
      "type": "object",
      "properties": {
        "format":   { "type": "string", "description": "Spec format, e.g. 'conda-environment-yaml'." },
        "filename": { "type": "string" },
        "path":     { "type": "string", "description": "Repo-relative path of the source file." },
        "sha256":   { "type": "string", "description": "SHA-256 of the verbatim file bytes." },
        "content":  { "type": "string", "description": "Full text of the environment specification." }
      },
      "required": ["format", "filename", "sha256", "content"]
    },
    "load_script": {
      "type": "object",
      "properties": {
        "format":      { "type": "string", "description": "e.g. 'python'." },
        "filename":    { "type": "string" },
        "path":        { "type": "string" },
        "sha256":      { "type": "string" },
        "content":     { "type": "string" },
        "entry_point": { "type": "string", "description": "Callable returning the simulated model, e.g. 'load'." }
      },
      "required": ["format", "filename", "sha256", "content"]
    },
    "simulator_package":      { /* package shape, see below */ },
    "flowsheet_model_package": { /* package shape, see below */ },
    "resolved": {
      "type": "object",
      "description": "Observed at export time inside the pinned environment; distinguishes what ran from what was declared.",
      "properties": {
        "python_version":   { "type": "string" },
        "platform":         { "type": "string" },
        "env_key":          { "type": "string" },
        "exported_at":      { "type": "string", "description": "UTC ISO-8601 timestamp." },
        "package_versions": { "type": "object", "additionalProperties": { "type": "string" } }
      }
    }
  },
  "required": ["environment", "load_script"]
}
```

**Package shape** — written out inline twice (no `$ref`, per §4.1). Accepts a VCS
commit **or** a PyPI version; a URL is required only when pinning a commit:

```jsonc
{
  "type": "object",
  "properties": {
    "name":    { "type": "string" },
    "url":     { "type": "string", "description": "Repository URL; required when 'commit' is given." },
    "commit":  { "type": "string", "description": "Full VCS commit SHA." },
    "branch":  { "type": "string", "description": "Branch the commit is reachable from, when known." },
    "version": { "type": "string", "description": "PyPI release version, when installed from PyPI." }
  },
  "required": ["name"],
  "anyOf": [ { "required": ["commit"] }, { "required": ["version"] } ],
  "allOf": [ { "if": { "required": ["commit"] }, "then": { "required": ["url"] } } ]
}
```

`simulator_package` and `flowsheet_model_package` restate pins that also appear in
the embedded YAML text. This duplication is intentional: it lets PISCES index and
query provenance without parsing embedded YAML. The runner **derives** both from
the YAML's pip entries (`git+URL@sha` → `commit`+`url`; `pkg==x` → `version`), so
the two representations cannot disagree.

### 6.1 Version bump (three parts, one commit)

1. `"version": "0.0.6"` in `sff_schema.json`.
2. New `export_biosteam_flowsheet_sff_0_0_6` in `_export.py`, `sff_version`
   defaulting to `'0.0.6'`, plus a `reproducibility=None` kwarg that omits the
   block entirely when absent (so hand exports still validate).
   `tests/test_version_sync.py` enforces the naming/default match with no
   changes needed.
3. A v0.0.5 permalink added to `docs/full_schema.md`. **The missing v0.0.4
   permalink is added at the same time** — the 0.0.4 → 0.0.5 bump skipped it.

`docs/schema_reference.md` is updated in the same commit.

## 7. `environment.yml` for `corn_dry_grind_ethanol`

```yaml
name: sff-corn-dry-grind-ethanol   # overridden by the harness via `conda env create -n`
channels:
  - defaults
dependencies:
  - python=3.9.25
  - pip
  - pip:
      - --no-deps
      # … every runtime dependency pinned with == …
      - thermosteam==0.45.0
      - numpy==1.26.4
      - numba==0.60.0
      - llvmlite==0.43.0
      - git+https://github.com/BioSTEAMDevelopmentGroup/biosteam@e2d3942dd1076a4516efc91ae194f9e558428551
      - git+https://github.com/BioSTEAMDevelopmentGroup/Bioindustrial-Park@584232846c999986f108cbd14d53437cd06c8f3d
```

**`--no-deps` is mandatory, not stylistic.** Without it, pip honours BIP's
`install_requires=['biosteam>=2.53.0', …]` and replaces the pinned biosteam
2.46.1 with a PyPI 2.53+ build, defeating the entire design.

Because `--no-deps` suppresses all resolution, every transitive dependency must be
listed explicitly. Known-needed pins observed in HP_2024:

```
thermosteam==0.45.0   chemicals==1.2.0     thermo==0.2.27      fluids==1.0.26
flexsolve==0.5.7      free-properties==0.3.6                   colorpalette==0.3.3
numpy==1.26.4         scipy==1.13.1        pandas==2.2.2       numba==0.60.0
llvmlite==0.43.0      matplotlib==3.5.2    Pint==0.23          graphviz==0.20.3
xlrd==2.0.1           openpyxl==3.1.2      xlsxwriter==3.2.9   jsonschema==4.25.0
PyYAML==6.0.1         ipython==8.15.0      chaospy==4.3.15     scikit-learn==1.6.1
```

`SALib` and `seaborn` are **excluded**: BIP declares them, but neither is
installed in the working HP_2024 environment, so neither is required to load and
simulate this model.

**Completion procedure for the pin list** (this is a defined loop, not an open
question): build the env, run the Tier 3 export, and add any pin named by a
resulting `ModuleNotFoundError`, pinned to the version present in HP_2024.
Repeat until the export succeeds. The list is complete when a Tier 3 run passes
from a freshly created environment. The final list is committed in
`environment.yml`.

### 7.1 Primary implementation risk

`biosteam@e2d3942` is v2.46.1, while `BIP@5842328` declares `biosteam>=2.53.0`.
That declaration is demonstrably unreliable (§1.3), and the corn code at
`5842328` uses the older `V=` / no-`RH` API matching biosteam 2.46.1 — so the
pair is expected to work. It has nonetheless **never been executed**: the working
local environment pairs biosteam 2.46.1 with BIP `6c22326`, not `5842328`.

The first Tier 3 run is the test of this pairing. **If it fails, the fallback
(bumping the biosteam pin to the oldest release satisfying BIP's declaration)
changes what gets exported, and therefore returns to the user for a decision
rather than being applied unilaterally.**

### 7.2 Expected difference from the committed corpus

`5842328` and the local BIP HEAD differ materially in the corn DDGS section:
`DDGSCentrifuge` changes base class (`bst.Splitter` → `bst.SolidsCentrifuge`),
with an inverted split, swapped outlet ports, an added `moisture_content=0.40`,
and a removed `Water` split entry.

The new export will therefore **not** match the committed `corn_ethanol.json` in
that area. It is written as a **new artifact**
(`corn_dry_grind_ethanol.json`); the committed `corn_ethanol.json` is left
untouched. Replacing it is a separate decision requiring explicit sign-off.

### 7.3 Effect on the corpus and its pass criterion

The new file is committed to
`pisces_sff/exported_flowsheets/bioindustrial_park/corn_dry_grind_ethanol.json`,
making it the **19th** corpus file. This is purely additive — no existing file is
regenerated — but it changes the canonical validation pass criterion from
"`failures: 0` across all **18** flowsheets" to **19**, so CLAUDE.md's
"Canonical validation" section is updated accordingly in the same commit.

It also makes `corn_dry_grind_ethanol.json` the first corpus file to report
`sff_version: "0.0.6"`; the other 18 continue to report `"0.0.3"` (known issue
#1), which remains unaddressed here.

## 8. Failure modes

| Failure | Handling |
|---|---|
| `breakpoint()` at `_export.py:225`, `:296`, `:606` | Child runs with `PYTHONBREAKPOINT=0`, making them no-ops. Avoids an unkillable hang in a TTY-less subprocess without editing known-issue lines |
| Concurrent simulations corrupting the numba cache | Harness takes a lock file and refuses a second concurrent export rather than trusting the caller. Batch runs keep the documented 5 s settle pause |
| `conda env create` fails midway | Partial env removed, so a broken env is never reused under a matching hash |
| `conda` not on PATH | Explicit error naming the executable searched for; `conda_exe` is overridable |
| `load()` raises | Propagated with the model name attached |
| Output fails schema validation | JSON left on disk for inspection; non-zero exit |
| Embedded `sha256` disagrees with the file on disk | Surfaced by the Tier 2 test, which recomputes it |

## 9. Testing

Three tiers. Gating uses `unittest.skipUnless` on environment variables rather
than pytest markers, so `python -m unittest discover -s tests` keeps working as
CLAUDE.md documents and no `pytest.ini` is needed to suppress unknown-marker
warnings.

**Tier 1 — always runs. No biosteam import.**

- `tests/test_schema_reproducibility.py` — pins the block shape; asserts
  commit-form and version-form packages both validate, that a package with
  neither is rejected, that `commit` without `url` is rejected, and that
  `reproducibility` stays absent from `metadata.required`.
- `tests/test_harness.py` — pure functions only: `env_key` determinism (stable
  across `name`/`prefix` edits, changes with any dependency edit), pip-entry →
  package-record parsing for both forms, sha256 of verbatim file bytes.
- Corpus revalidation: all 18 flowsheets, `failures: 0`.

**Tier 2 — `SFF_TEST_BIOSTEAM=1`. Imports biosteam.**

Calls `load()` from `corn_dry_grind_ethanol/load.py` in the *current*
environment, exports to a temp directory, and validates against the schema.
Asserts **structural** properties only: output validates; `metadata.reproducibility`
present; embedded `sha256` matches the on-disk file bytes; feedstock resolves to
corn; units and streams non-empty. Numeric assertions are deliberately excluded —
run from HP_2024 this exercises BIP `6c22326`, not the pin.

**Tier 3 — `SFF_TEST_E2E=1`. Full `export_model()` including env creation.**

The only tier in which the pins are what actually ran, and therefore the only
tier permitted to assert **numeric baselines** with an explicit tolerance.
Baseline values are recorded from the first successful run rather than invented
in advance.

**Tests must not run in parallel.** Tiers 2 and 3 both simulate, and concurrent
simulations corrupt the numba cache; `pytest-xdist` must not be used. The harness
lock enforces this at runtime.

### 9.1 Documentation updates

CLAUDE.md's "Canonical validation" section currently states that smoke tests are
planned and that their baselines should be recorded there once they land. Tier 3
is that check. The same commit therefore updates that section with the gated
commands and the recorded baseline numbers and tolerance, and corrects the stale
"currently 10 passed" count.

## 10. Verification

Before committing:

```powershell
& "C:\Users\saran\anaconda3\envs\HP_2024\python.exe" -c "import glob,os; from pisces_sff import validate_json_against_schema as v; s='pisces_sff/schema/sff_schema.json'; r=[(os.path.basename(f),)+v(f,s) for f in sorted(glob.glob('pisces_sff/exported_flowsheets/bioindustrial_park/*.json'))]; [print(n,'OK' if ok else ('FAIL '+str(e[:2]))) for n,ok,e in r]; print('failures:', sum(1 for _,ok,_ in r if not ok))"
```

```powershell
& "C:\Users\saran\anaconda3\envs\HP_2024\python.exe" -m pytest tests -q
```

Pass criteria: `failures: 0` across all 18 flowsheets; all tests pass. Tiers 2
and 3 are run explicitly via their environment variables and must pass before the
harness is considered complete.

## 11. Deliverables

1. `pisces_sff/models/{__init__.py,biosteam_models/__init__.py}`
2. `pisces_sff/models/biosteam_models/corn_dry_grind_ethanol/environment.yml`
3. `pisces_sff/models/biosteam_models/corn_dry_grind_ethanol/load.py`
4. `pisces_sff/_harness.py`, `pisces_sff/_runner.py` (both `__all__`-driven,
   MIT header, `#%%` cell delimiters, NumPy-style docstrings)
5. Schema v0.0.6 with `metadata.reproducibility`
6. `export_biosteam_flowsheet_sff_0_0_6` in `_export.py`
7. `tests/test_schema_reproducibility.py`, `tests/test_harness.py`, and the
   Tier 2 / Tier 3 tests
8. `docs/full_schema.md` (v0.0.5 **and** missing v0.0.4 permalinks),
   `docs/schema_reference.md`, CLAUDE.md canonical-validation section
9. `corn_dry_grind_ethanol.json` produced by a Tier 3 run
