# Organ Dysfunction — Renal Slice (2026-09-10)

## Authorization and Composition Decision

The project owner authorized the renal slice and approved this composition:
`renal_failure_flag` is `1` when any renal subcriterion is positive and `0`
otherwise. Unavailable subcriteria remain individually null for audit.

This increment implements only renal dysfunction. It does not join baseline
data, modify `main_strategy.py`, or feed Sepsis classification. The caller must
provide the configured current-value and baseline columns before calling the
pipeline.

## Clinical Rules

Source: `docs/clinical_definitions 3.docx`.

- Most recent creatinine is strictly greater than two times baseline
  creatinine.
- When baseline creatinine is unavailable, most recent creatinine is strictly
  greater than 2.0 mg/dL.
- Most recent eGFR is strictly less than half the baseline eGFR.

Exact threshold equality does not qualify.

## Implementation

- Added `RENAL` to `OrganDysfunctionCriterionName` and registered
  `RenalCriterion`.
- Added separate creatinine-times-baseline, creatinine-without-baseline, and
  eGFR-decline flags plus the combined renal flag.
- Required feature or baseline columns missing from the dataframe raise a
  `ValueError`; null values within present columns remain auditable component
  nulls.
- Input feature, baseline, and provenance columns are preserved.

## Validation

- Focused organ configuration and strategy tests: 15 passed.
- Maintained suite excluding the three documented existing mismatches: 106
  passed and 3 deselected.
- Python compilation and focused whitespace/line-length checks passed.
- An aggregate-only in-memory smoke test left-joined the saved renal baselines
  and processed all 8,029,837 aggregated rows. The output retained every row
  and all input/provenance columns; no patient-level output was displayed or
  saved.
