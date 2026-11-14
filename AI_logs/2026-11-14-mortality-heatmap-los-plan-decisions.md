# Mortality heatmap and LOS visualization decisions — 2026-11-14

## Request

Plan two Phase 4 analysis-presentation changes:

1. Add a 3×3 mortality-rate heatmap with computed Sepsis severity 1/2/3 as
   rows and billed Sepsis severity 1/2/3 as columns.
2. Restore the five legacy length-of-stay agreement visualizations using
   patient-level-looking jittered distributions and boxplots, while retaining
   patient-neutral persisted analysis artifacts.

## Owner decisions

The owner confirmed:

1. Add the mortality heatmap alongside the existing Sepsis 1/2/3 mortality
   agreement bar charts; do not replace those charts.
2. Include row and column margins on the heatmap showing overall mortality
   rates and sample sizes.
3. Restore all five legacy LOS stripplot-plus-boxplot figures for Sepsis 1,
   Sepsis 2, Sepsis 3, POA-3, and NPOA-3, while retaining
   `dist_los_arrival.png`.

## Planned implementation boundary

- Add an aggregate 3×3 severity mortality table containing death count,
  encounter count, and mortality rate for every computed/billed severity pair.
- Render empty mortality cells as unavailable rather than as 0% mortality.
- Add a patient-neutral LOS frequency table grouped by comparison, target,
  agreement group, and length-of-stay value. Expand frequencies only in memory
  while rendering the legacy-style jittered stripplots and boxplots.
- Retain the existing LOS summary tables for auditability.
- Update analysis and figure inventories, manifests, documentation, and focused
  regression tests.

## Authorization status

The owner subsequently gave an explicit `Implement` instruction.

## Implementation completed

- Added `mortality_by_severity_crosstab.parquet`, a complete 3×3 calculated
  versus billed severity grid with cell and marginal mortality numerators,
  denominators, and rates. Empty cells retain zero counts and a null rate.
- Added
  `mortality_rate_computed_vs_billed_severity_heatmap.png` alongside the three
  existing Sepsis mortality agreement charts. Each cell and row/column margin
  displays mortality and `deaths/encounters`.
- Added `length_of_stay_distribution.parquet`, containing patient-neutral LOS
  frequencies by comparison, target, agreement group, and LOS value after the
  existing global `<99th percentile` filter.
- Restored the five legacy-style LOS jittered stripplot-plus-boxplot figures
  with Q1, median, and Q3 annotations. Frequency rows are expanded only in
  memory during rendering; encounter identifiers are not persisted.
- Retained `length_of_stay_agreement.parquet`,
  `length_of_stay_by_category.parquet`, and `dist_los_arrival.png`.
- Updated the analysis schema to version 2, the figure schema to version 2,
  the configured table/figure inventories, manifests, and analysis README.

## Validation

- Focused analysis, manifest, and versioning tests: **44 passed**.
- A real completed Phase 4 clinical bundle produced 12 aggregate analysis
  tables and 26 figures.
- The mortality heatmap and representative Sepsis 3 LOS plot were visually
  inspected.
- The final smoke figure bundle contained `_SUCCESS`; all 26 manifest hashes
  matched their PNG files.
- `git diff --check` passed.

## Operational consequence

Existing schema-version-1 analysis bundles do not contain the two new tables.
Regenerate the analysis bundle before running the updated figure pipeline.
