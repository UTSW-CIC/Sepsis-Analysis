# Organ Dysfunction — Baseline Composition (2026-09-11)

## Authorization and Scope

The project owner approved the pre-integration step after completion of the
five non-pulmonary organ criteria. This increment prepares encounter baselines
and validates their combined Strategy/Registry output. It does not modify
`main_strategy.py`, implement pulmonary dysfunction, or change any clinical
threshold.

## Implementation

- Added `prepare_organ_dysfunction_input()` as an explicit boundary between
  the temporal aggregate and encounter baseline tables.
- The function left-joins only the four baselines used by the current renal,
  hepatic, and coagulation strategies: creatinine, eGFR, bilirubin, and
  platelets.
- The aggregate timeline remains the authoritative row set. The join validates
  one encounter row per encounter and asserts that the aggregate row count is
  unchanged.
- Null encounter identifiers and duplicate encounter rows are rejected.
- Existing baseline columns or the availability marker are rejected before the
  join so no input column can be silently overwritten.
- `baseline_encounter_row_available` distinguishes a missing encounter row
  from an available encounter row whose baseline values are null.
- Exported the preparation function from the organ-dysfunction package.
- Added a combined test proving that the default registry evaluates all five
  implemented organs and sums their flags without removing input evidence.

## Validation

- Focused input-preparation and organ-strategy tests: 28 passed.
- Maintained suite: 120 passed and 3 known expectation mismatches deselected.
  The deselected tests are the two intentionally enabled episode-filter
  defaults and the previously documented suspected-infection earliest-pair
  expectation.
- Aggregate-only in-memory smoke test processed all 8,029,837 saved aggregate
  rows. Preparation and scoring retained all rows and every input/provenance
  column. There were 1,536 timeline rows without a matching encounter row;
  these were retained and marked unavailable. No patient-level output was
  printed or saved.

## Remaining Work

- Review and approve integration into `main_strategy.py`.
- Implement pulmonary dysfunction separately from the five non-pulmonary
  criteria because its support tiers, termination events, and exclusions
  require their own temporal logic.
