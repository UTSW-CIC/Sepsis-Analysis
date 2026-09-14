# Organ Dysfunction — Step 1 Configuration Repair (2026-09-10)

## Project-Owner Clarification

Question: Which clinical-definition document should guide this organ-
dysfunction implementation?

Answer: Use `docs/clinical_definitions 3.docx`. The previously provided
underscore filename was a typo.

## Approved Scope

Implement only Step 1 of the incremental plan: repair the current
`src_strategy` organ-dysfunction configuration so it imports successfully. Do
not implement clinical criteria yet.

## Technical Defect

`src_strategy/configs/organdysfunction.py` defined an obsolete, unused
`PulmonaryConfig` that referenced `FeatureColumn.VENT_STATUS_FLAG`. That enum
member is no longer registered, so importing the configuration raised an
`AttributeError`. Pulmonary dysfunction already has a separate configuration
module.

## Change

- Removed only the dead `PulmonaryConfig` class and its dead `VentConfig` and
  `vent_config` imports.
- Kept the active cardiovascular, renal, hepatic, coagulation, neurological,
  baseline, and top-level organ configuration unchanged.
- Added a focused regression test for successful configuration import and the
  intended absence of a nested pulmonary configuration.

## Validation

- Focused configuration test: 1 passed.
- Direct module import and Python compilation passed.
- Maintained suite excluding three known configuration/behavior mismatches:
  92 passed and 3 deselected. The additional deselection is the BP test that
  expects filtering to be disabled, while the project owner has enabled it in
  the current working tree for integration testing.
- The focused organ-configuration diff has no whitespace errors. A separate
  pre-existing trailing-space warning remains in the owner's modified
  `main_strategy.py`; it was not changed.

## Decisions Still Required Before Clinical Criteria

- Whether renal, hepatic, and coagulation sub-flags remain in output.
- Whether the INR and aPTT rules are conditioned on missing baseline platelets
  exactly as written in `docs/clinical_definitions 3.docx`.

## Approved Missingness Contract

Question: Should the cardiovascular criterion use `1` for abnormal lactate,
`0` for a measured normal lactate, and null for missing lactate evidence?

Project-owner answer: Yes.

## Cardiovascular Slice Authorization

The project owner explicitly requested implementation of the cardiovascular
organ-dysfunction slice.

The authorized rule from `docs/clinical_definitions 3.docx` is most-recent
valid lactate greater than 2.0 mmol/L. The implementation must use a strict
comparison and the approved `1/0/null` missingness contract. Other organ
criteria and final pipeline integration remain out of scope for this slice.

## Cardiovascular Slice Implementation

- Added `OrganDysfunctionCriterionName` and a validated `selected` list. Only
  the cardiovascular strategy is registered in this increment.
- Added `CardiovascularCriterion`, which consumes `last_lactate_6h` and emits
  `cardiovascular_failure_flag` as `1`, `0`, or null according to the approved
  contract.
- Added `ORGAN_DYSFUNCTION_CRITERION_REGISTRY` and
  `build_organ_dysfunction_pipeline()` using the shared `Pipeline` and
  `SumReducer`.
- `organ_dysfunction_total` is therefore `1` when cardiovascular dysfunction
  is present and `0` otherwise in this first slice. A null cardiovascular flag
  contributes zero to that classification total while remaining visible for
  evidence review.
- Input columns, including `last_lactate_6h_source_ts`, are preserved.
- No `main_strategy.py`, pulmonary, other-organ, or final Sepsis composition
  behavior was changed.

## Cardiovascular Slice Validation

- Focused organ configuration and cardiovascular suite: 8 passed.
- Maintained suite excluding the three documented existing mismatches: 99
  passed and 3 deselected.
- Python compilation and focused whitespace/line-length checks passed.
- An in-memory aggregate smoke test against the saved measured-MAP aggregation
  preserved all 8,029,837 input rows and all input columns. No patient-level
  output was displayed or saved.
