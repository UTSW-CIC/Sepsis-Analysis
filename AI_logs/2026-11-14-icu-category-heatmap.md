# ICU category heatmap

## Requirement

Add a Phase 4 analysis counting encounters with `ICU_YN == 1` across billed
and calculated sepsis categorizations, and render the result as a heatmap.

## Implemented interpretation

- Use the primary calculated categorization based on Arrival + 48 hours.
- Use the full six categories: NPOA-1/2/3 and POA-1/2/3.
- Each heatmap cell is the number of ICU encounters in one calculated/billed
  category pairing; it is not an ICU admission rate.
- Display calculated-category row totals and billed-category column totals.
- Treat `ICU_YN == 1` as ICU, `ICU_YN == 0` as not ICU, and a null flag as not
  counted as ICU.
- Apply the existing Phase 4 analysis-cohort scope before counting: calculated
  positive-sepsis encounters with billed UPOA encounters excluded.

## Implementation

- Carried `ICU_YN` from the encounter table into
  `df_sepsis_encounters.parquet`.
- Added validation allowing only `0`, `1`, or null in the analysis cohort.
- Added the patient-neutral 6x6 aggregate table
  `icu_by_category_crosstab.parquet`.
- Added
  `icu_encounter_count_computed_vs_billed_category_heatmap.png`.
- Advanced the analysis and figure bundle schema versions from 2 to 3.
- Recorded ICU semantics and the calculated timing reference in the analysis
  manifest parameters.

## Validation

- Encounter categorization and analysis tests: 8 passed.
- Analysis, manifest, and run-versioning tests: 44 passed.
- The generated ICU heatmap was visually inspected.
- A scoped `git diff --check` passed. A repository-wide check remains affected
  by pre-existing trailing whitespace in the owner's modified
  `scripts/sbatch.sh`, which was not changed for this task.

## Additional ICU analyses requested

The owner requested five additional figures:

1. A 3x3 ICU encounter-count heatmap with POA/NPOA collapsed, using computed
   Sepsis 1/2/3 as rows and billed Sepsis 1/2/3 as columns.
2. Diverging ICU-status bars for computed Sepsis 1/2/3.
3. Diverging ICU-status bars for billed Sepsis 1/2/3.
4. Diverging ICU-status bars for the six computed POA/NPOA categories.
5. Diverging ICU-status bars for the six billed POA/NPOA categories.

For each diverging plot, `ICU_YN == 1` is plotted upward and `ICU_YN == 0`
downward. The downward direction is a visual encoding; annotations remain
positive counts. Null ICU flags are omitted from both bars.

## Additional ICU analyses completed

- Added `icu_by_severity_crosstab.parquet`, a complete 3x3 ICU-positive count
  grid with computed and billed marginal totals.
- Added `icu_status_counts.parquet`, a complete patient-neutral count table for
  ICU statuses 0 and 1 across computed/billed severity and computed/billed
  POA/NPOA category.
- Added the collapsed severity heatmap and all four requested diverging
  barplots while retaining the original six-category ICU heatmap.
- Advanced the analysis and figure bundle schema versions from 3 to 4. The
  configured figure inventory now contains 32 figures.
- Analysis, manifest, and versioning suite: 44 passed.
- Final focused render suite after visual refinements: 4 passed.
- All five new figures were visually inspected. The barplot count axes use
  absolute integer tick labels, and zero-height bars are not annotated.

## ICU bar-label percentage decision

The owner requested percentages next to the counts on all four ICU-status
diverging barplots. The denominator is the non-null ICU-status total within the
same sepsis classification, so the ICU and non-ICU percentages for a category
sum to 100%. Labels use the format `count (percentage)` with one decimal place;
zero-height bars remain unannotated.

## ICU bar-label percentage implementation

- Updated the shared diverging-bar renderer, so all four ICU barplots now use
  labels such as `4,694 (81.2%)`.
- Advanced the figure bundle schema version from 4 to 5.
- Added a focused regression test covering the within-classification
  denominator and exact upward/downward label text.
- Focused analysis/figure suite: 5 passed.
- Regenerated a complete 32-figure bundle from the latest aggregate analysis;
  `_SUCCESS` is present and the manifest reports figure schema version 5.
- Visually inspected representative severity and six-category ICU barplots.
