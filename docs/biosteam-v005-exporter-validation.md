# BioSTEAM v0.0.5 exporter validation record

This document holds the technical evidence for pull request #9.

## Why this exists

Project PISCES needs to regenerate 32 public BioSTEAM flowsheets in SFF v0.0.5. Fourteen older files have no chemicals catalog or molecular weights, so the website cannot reliably convert mole fractions to mass fractions.

On `main`, the canonical v0.0.5 exporter labels its output as v0.0.3. Full-corpus testing also shows that some real BioSTEAM values can produce invalid JSON, fractions above one, or unstable reaction output. This PR fixes those boundaries so an export is valid and repeatable or fails with a useful exception.

## What the PR changes

`CURRENT_SFF_VERSION` is now the single version authority for both the package and exported metadata. This lets us update the version in one place when the standard advances.

The exporter also:

- normalizes only positive stream components included in the document;
- converts NumPy and `deque` values to ordinary JSON values;
- omits undefined optional numbers and rejects any remaining `NaN` or infinity;
- raises exceptions instead of opening an interactive debugger;
- emits each top-level reaction once, in unit attribute order.

## What development testing found

| Evidence | Finding and result |
| --- | --- |
| `bffccf70` | The v0.0.5 entry point stamped `0.0.3`. The first regression test caught the mismatch. |
| `05f6c4b2`, `22220e99` | Corpus testing found negative solver residue and NumPy values at the JSON boundary. The fixes normalize exported components and convert NumPy values. |
| `f57d3296` | The cellulosic acTAG model exposed a `collections.deque`; the exporter now converts it to a list. |
| Build `e3158dd6` | All 32 models ran, but strict parsing found two `NaN` vessel-cost values in `bfg_oleochemical`. |
| `22914bab`, build `e2af8f33` | The exporter began omitting undefined optional numbers and rejecting non-standard JSON. The next 32-model run passed. |
| `a786c311` | Comparing successful runs exposed hash-order-dependent reaction output. Reaction discovery now preserves attribute order. |
| Build `e8994df8-b48b-4875-8533-d8b4bc2e5b58` | The final exporter-code run completed 32/32 models with zero failures. Every file passed the v0.0.5 schema, strict JSON parsing, and positive finite molecular-weight checks. |

## Current proof

Six dependency-isolated tests cover the central version authority, metadata stamp, composition normalization, JSON conversion, finite-number enforcement, and reaction ordering.

Build `e8994df8-b48b-4875-8533-d8b4bc2e5b58` tests the exporter behavior at `a786c311`. The later version-authority refactor changes where the same `0.0.5` value comes from and is covered by the sixth unit test.

Project PISCES frontend pull request [#4671](https://github.com/sustainability-software-lab/project-pisces-frontend/pull/4671) contains the regenerated corpus, schema support, data migration, and website regression tests. After this PR merges, that branch pins the merge SHA and reruns all 32 exports before landing.

## Review focus

1. Does one constant control both package and export versions?
2. Do composition fractions use only exported components?
3. Does the JSON boundary convert known containers and reject unknown ones?
4. Are undefined optional numbers omitted while other non-finite values fail?
5. Does reaction discovery preserve order and remove only nested duplicates?
