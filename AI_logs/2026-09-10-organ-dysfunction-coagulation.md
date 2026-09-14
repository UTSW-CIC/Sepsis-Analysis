# Organ Dysfunction — Coagulation Slice (2026-09-10)

## Authorization and Clinical Decision

The project owner authorized the coagulation slice and confirmed proceeding
with the rules exactly as written in `docs/clinical_definitions 3.docx`.
Therefore, INR and aPTT qualify only when baseline platelet data is unavailable.

This increment does not join baseline data, modify `main_strategy.py`, or feed
Sepsis classification. The caller must provide the configured platelet, INR,
aPTT, and baseline-platelet columns.

## Clinical Rules

- Platelets are below 100, baseline platelets are above 100, and current
  platelets are strictly below half of baseline.
- With no baseline platelet value, current platelets are strictly below 100.
- With no baseline platelet value, INR is strictly greater than 1.5.
- With no baseline platelet value, aPTT is strictly greater than 60 seconds.
- Exact equality at any threshold does not qualify.

## Implementation

- Added `COAGULATION` to `OrganDysfunctionCriterionName` and registered
  `CoagulationCriterion`.
- Preserved separate platelet-drop, platelet-without-baseline, INR, and aPTT
  component flags plus the combined coagulation flag.
- The combined flag is `1` if any component is positive and `0` otherwise;
  unavailable components remain null.
- Missing required dataframe columns raise `ValueError`. Input feature,
  baseline, and provenance columns are preserved.

## Validation

- Focused organ configuration and strategy tests: 21 passed.
- Maintained suite excluding the three documented existing mismatches: 112
  passed and 3 deselected.
- Python compilation and focused whitespace/line-length checks passed.
- An aggregate-only in-memory smoke test left-joined the saved platelet
  baseline and processed all 8,029,837 aggregated rows. The output retained
  every row and all input/provenance columns; no patient-level output was
  displayed or saved.
