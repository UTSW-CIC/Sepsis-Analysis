# Organ Dysfunction — Hepatic Slice (2026-09-10)

## Authorization and Scope

The project owner authorized the hepatic slice. This increment implements only
hepatic dysfunction. It does not join baseline data, modify
`main_strategy.py`, or feed Sepsis classification. The caller must provide the
configured current bilirubin and baseline bilirubin columns.

## Clinical Rules

Source: `docs/clinical_definitions 3.docx`.

- With a baseline, most recent bilirubin must be strictly greater than 2.0
  mg/dL and strictly greater than two times baseline bilirubin.
- Without a baseline, most recent bilirubin must be strictly greater than 2.0
  mg/dL.
- Exact equality at either boundary does not qualify.

## Implementation

- Added `HEPATIC` to `OrganDysfunctionCriterionName` and registered
  `HepaticCriterion`.
- Added separate bilirubin-times-baseline and bilirubin-without-baseline flags
  plus the combined hepatic flag.
- The combined hepatic flag is `1` if either subcriterion is positive and `0`
  otherwise. Unavailable component evidence remains null.
- Missing required dataframe columns raise `ValueError`; null values within
  present columns remain auditable.
- Input feature, baseline, and provenance columns are preserved.

## Validation

- Focused organ configuration and strategy tests: 18 passed.
- Maintained suite excluding the three documented existing mismatches: 109
  passed and 3 deselected.
- Python compilation and focused whitespace/line-length checks passed.
- An aggregate-only in-memory smoke test left-joined the saved bilirubin
  baseline and processed all 8,029,837 aggregated rows. The output retained
  every row and all input/provenance columns; no patient-level output was
  displayed or saved.
