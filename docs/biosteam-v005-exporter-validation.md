# BioSTEAM v0.0.5 exporter validation record

This document records the investigation and live corpus testing behind pull request #9. It preserves the detailed history that was previously spread across the pull request comments.

## Why the change grew beyond a version stamp

The immediate bug was small: the v0.0.5 BioSTEAM exporter wrote `0.0.3` into `metadata.sff_version`. Correcting that line was necessary, but it was not enough to trust the exporter with the Project PISCES public corpus.

Project PISCES needed to regenerate all 32 public BioSTEAM flowsheets because 14 older files did not include a chemicals catalog or molecular weights. Those missing values made the website fall back to mole fractions where users expected mass fractions. The re-export therefore became a useful full-scale test of the canonical exporter.

Running real models found several cases that the original one-line regression test could not expose. Each problem was fixed here, then tested again against the full corpus. No scientific value was guessed or replaced with a convenient default.

## What changed

The exporter now:

- stamps v0.0.5 documents as `0.0.5`;
- ignores negative floating-point residuals in stream composition and normalizes the positive components that are actually exported;
- converts NumPy scalars, NumPy arrays, and `collections.deque` values into ordinary JSON values;
- omits undefined optional numeric results instead of writing non-standard `NaN` tokens;
- rejects any remaining `NaN` or infinity during JSON serialization;
- raises real exceptions instead of dropping into interactive `breakpoint()` calls;
- discovers top-level reactions without mutating a set during iteration, preserving the unit's attribute order and producing deterministic output.

The tests in `tests/test_export.py` cover the version stamp, composition normalization, JSON conversion, strict finite-number handling, and deterministic reaction discovery without requiring a local BioSTEAM installation.

## Investigation and validation timeline

### 1. Correct the version stamp

Commit `bffccf70c7f4644de962a1fe1743d9a111b387bb` changed the v0.0.5 exporter stamp from `0.0.3` to `0.0.5` and added a regression test through the public exporter entry point.

That test passed, but the real 32-model export uncovered more work.

### 2. Make stream composition valid

Some BioSTEAM streams contain tiny negative values left by numerical solvers. The exporter skipped those components but still divided the remaining positive values by a total that included the negative residuals. That could produce exported fractions whose sum exceeded one.

Commit `05f6c4b227059cc1e5af41754174a1f3dabe8c1a` changed the calculation to normalize only the positive components included in the document. This fixed the conventional acTAG schema failures.

### 3. Keep BioSTEAM values inside standard JSON

The next corpus pass reached values represented as NumPy scalars and arrays. Commit `22220e99ffb7ef504f09710cf738c0e50510ec62` converts them to native Python numbers and lists. It also removed three interactive debugger fallbacks, which could otherwise hang an unattended export.

The cellulosic acTAG model then produced a `collections.deque` in its design results. Commit `f57d3296e4b4d9d73ef9b9848d2de2eaf2a15c56` converts that value to a JSON list.

### 4. Reject undefined numeric output

Cloud Build `e3158dd6-7fc1-4330-aec8-60cd329b277c` completed all 32 models. A stricter downstream parser then found two `NaN` values in optional vessel-cost fields for `bfg_oleochemical`.

Commit `22914bab90d0c7e344b942303e8e9e0076980b01` omits optional numeric results when the simulator reports them as undefined and writes JSON with `allow_nan=False`. This makes any remaining non-finite value a hard export error rather than a non-standard token hidden in an otherwise successful run.

Cloud Build `e2af8f33-c3dd-4f60-95f1-1407b9a69b0d` then exported all 32 models with zero failures and standards-compliant JSON.

### 5. Make reaction output deterministic

Comparing repeated successful runs exposed a final problem. Reaction discovery built a set and mutated it while resolving parent reactions. Python hash order could therefore change reaction membership and ordering from one run to another.

Commit `a786c31147120b6ded00039834995e0b623125fe` collects reactions in unit attribute order, identifies nested reactions against an immutable snapshot, and emits each top-level reaction once.

## Final exact-head result

Cloud Build `e8994df8-b48b-4875-8533-d8b4bc2e5b58` tested commit `a786c31147120b6ded00039834995e0b623125fe` against all 32 registered public BioSTEAM models.

The result was 32 successful exports and zero failures. Every file passed:

- the canonical SFF v0.0.5 schema;
- strict JSON parsing that rejects `NaN` and infinity;
- a non-empty chemicals catalog;
- positive, finite molecular weights for every chemical.

The dependency-isolated unit suite also passes all five exporter tests:

```text
Ran 5 tests in 0.010s
OK
```

## Downstream use

Project PISCES frontend pull request [#4671](https://github.com/sustainability-software-lab/project-pisces-frontend/pull/4671) contains the regenerated corpus, v0.0.5 schema support, importer migration, and website regression tests.

That pull request currently pins this branch head for review. After this pull request merges, the frontend dependency will be changed to the merge commit and the 32-model export will run once more against that exact SHA before the corpus lands.

## Reviewer guide

The production changes are confined to `pisces_sff/_export.py`. A reviewer should focus on five questions:

1. Does the v0.0.5 entry point stamp the correct version?
2. Are composition fractions based only on components included in the export?
3. Does the JSON boundary convert supported container types while failing on unknown ones?
4. Are undefined optional numbers omitted while all other non-finite numbers fail loudly?
5. Does reaction discovery preserve order and remove only nested duplicates?

The unit tests map directly to those questions. The full-corpus builds provide the integration evidence that the same code works on the 32 models it is intended to export.
