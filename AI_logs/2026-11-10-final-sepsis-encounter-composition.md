# Final encounter-level sepsis composition — 2026-11-10

## Requested processing step

Add an encounter-level output that combines the Sepsis 1, Sepsis 2, and
Sepsis 3 encounter summaries and supports comparison with the billed
`Sepsis_Category` column from `df_encounters`.

## Confirmed rules

- Calculated severity is the highest positive severity over the encounter:
  Sepsis 3, otherwise Sepsis 2, otherwise Sepsis 1, otherwise 0.
- The first calculated sepsis onset is the minimum of `sepsis_1_dt`,
  `sepsis_2_dt`, and `sepsis_3_dt`, considering only positive criteria.
- The Arrival + 48-hour boundary is inclusive: onset at exactly
  `Arrival_Instant + 48 hours` is POA.
- A later onset is NPOA.
- Encounters without calculated sepsis receive severity 0, a null onset, and
  the category `No Sepsis`.
- Preserve the existing billed `Sepsis_Category` column unchanged and compare
  the calculated category against it.
- Join the encounter columns needed by the downstream analysis from
  `df_encounters`.

## Approved encounter columns

The owner approved the minimal projection used by the current analysis code:

- `EncounterEpicCsn`
- `Arrival_Instant`
- `InpatientAdmissionInstant`
- `LengthOfStayInDays`
- `Death_Flag`
- `Sepsis_Category`

## Implementation completed

- Added `build_final_sepsis_encounter_summary()` under
  `src_strategy/events/sepsis/encounter_categorization.py`.
- Preserved every column from the three severity encounter summaries.
- Added calculated severity, first onset, POA/NPOA status, calculated category,
  and comparison with the unchanged billed category.
- Added `df_sepsis_encounters.parquet` to the Phase 4 versioned clinical bundle.
- Added a publish-time one-row-per-encounter validation.
- Added focused tests for maximum severity, first onset, the inclusive 48-hour
  boundary, independent Sepsis 3, no sepsis, missing arrival, and invalid
  flag/onset pairs.

## Validation

- Focused Sepsis and run-validation tests: **33 passed**.
- Read-only smoke calculation on the completed 15,133-encounter run produced
  15,133 unique encounter rows, 687 `No Sepsis` rows, and exactly 687 null
  onset timestamps.
- Run lifecycle/configuration tests: **47 passed, 1 failed**. The failure is a
  stale expectation that `dataset_version` remains `phase3_2026-06-05`; the
  working tree already contains an owner change to `phase4_2026-06-05`, which
  this implementation did not modify.
