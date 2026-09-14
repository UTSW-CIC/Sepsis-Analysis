# Organ Dysfunction — Neurological Slice (2026-09-10)

## Authorization and Scope

The project owner approved adding the remaining non-pulmonary organ strategies
one at a time. This increment implements only neurological dysfunction and
does not integrate organ dysfunction into `main_strategy.py` or Sepsis
classification.

## Clinical Rule

Source: `docs/clinical_definitions 3.docx`.

- Neurological dysfunction is present when the most recent valid Glasgow Coma
  Score is strictly less than 15.
- The shared evidence contract is `1` for abnormal, `0` for measured normal,
  and null for missing evidence.
- A GCS exactly equal to 15 is normal.

## Implementation

- Added `NEUROLOGICAL` to `OrganDysfunctionCriterionName`.
- Added `NeurologicalCriterion` to the organ criteria module and registry.
- The default organ pipeline now runs the implemented cardiovascular and
  neurological strategies and sums their organ-level flags.
- Neurological input and provenance columns remain unchanged in the output.
- Cardiovascular tests now select only the cardiovascular strategy so each
  criterion remains independently reviewable as the registry grows.

## Validation

- Focused organ configuration and strategy tests: 12 passed.
- Maintained suite excluding the three documented existing mismatches: 103
  passed and 3 deselected.
- Python compilation and focused whitespace/line-length checks passed.
- An aggregate-only in-memory smoke test ran the cardiovascular and
  neurological strategies over all 8,029,837 saved aggregated rows. The output
  retained every row and all input/provenance columns; no patient-level output
  was displayed or saved.
