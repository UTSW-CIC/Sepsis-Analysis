# Analysis redesign decisions — 2026-11-11

## Current implementation boundary

The first analysis-redesign implementation will reproduce the distinct active
analyses in legacy `CoreAnalysis` using the completed Phase 4 versioned clinical
run.

- Preserve the legacy positive-calculated-sepsis cohort for now. Encounters
  whose calculated category is `No Sepsis` are excluded from this first slice.
- Exclude encounters with a billed `UPOA-*` category before calculating any
  analysis denominator or result.
- Initially write aggregate Parquet tables. Figures will be added afterward.
- Organ-dysfunction attribution is not part of the first implementation.

## Deferred analyses

### Calculated `No Sepsis` encounters

Add a future analysis of encounters classified as `No Sepsis` by the algorithm,
with particular attention to billed sepsis encounters that the algorithm may
have missed. The denominator, comparison groups, and evidence/missingness
breakdown must be designed before implementation.

### Organ-dysfunction attribution

Add a future Sepsis 2 organ-type analysis with two clearly labeled views:

1. organ types represented by the earliest qualifying Sepsis 2 association;
2. organ types represented by any qualifying Sepsis 2 association.

Repeated infection-anchor associations must not inflate encounter prevalence.
The current classifier selects the earliest positive organ-dysfunction episode
per organ type across the encounter before applying suspected-infection-window
association. A later episode of the same organ type cannot replace an earlier
episode that fails to overlap an infection window.

## Implementation authorization

These are design decisions only. No analysis implementation was authorized in
this discussion.

## Dopamine vasopressor correction

The owner confirmed that Dopamine was unintentionally omitted from the Phase 4
vasopressor `grouper_values` registry and should have been included. The exact
source value `Event_Grouper == "Dopamine"` exists in the Phase 4 event data.

Dopamine will follow the same existing qualification rule as the other
configured vasopressors: a `Medication Administration` row qualifies when
`NumericValue` is non-null and greater than zero. No Dopamine-specific dose or
unit threshold will be added.

This correction requires regeneration of the Phase 4 clinical pipeline and a
new immutable versioned clinical run before downstream analysis. The owner
stated that they will add Dopamine to the registry; no registry code was changed
while recording this decision.

## Phase 4 CoreAnalysis refactor decisions

The owner authorized implementation of the Phase 4 analysis refactor and
confirmed:

1. Write one aggregate Parquet table for each distinct active legacy
   `CoreAnalysis` analysis, collapsing duplicated figure calls that use the
   same underlying result.
2. Use the Phase 4 qualifying vasopressor-administration evidence rather than
   recreating the legacy raw-event pressor scan.
3. Keep the implementation in `main_analysis_phase4.py`; do not add a separate
   `src_strategy/analysis/` module in this initial version. The script retains
   explicit clinical-run and output-directory command-line arguments so paths
   are not hard-coded.

## Phase 4 analysis implementation

`main_analysis_phase4.py` now:

- validates `_SUCCESS`, `manifest.json`, required table declarations, hashes,
  and schemas for a completed clinical run;
- constructs the positive-calculated-sepsis cohort and removes billed
  `UPOA-*` encounters before every denominator;
- produces ten aggregate, patient-neutral Parquet tables covering the distinct
  active legacy category, POA, crosstab, mortality, time-to-sepsis, LOS, and
  vasopressor-window analyses;
- uses qualifying Phase 4 vasopressor administrations and the first qualifying
  administration time per encounter;
- records clinical-run identity and analysis parameters in
  `analysis_manifest.json`; and
- writes `_SUCCESS` only after all outputs and provenance are complete.

Focused synthetic tests cover cohort exclusions, aggregate-only output grain,
the active analysis inventory, and qualifying vasopressor-window behavior. A
read-only smoke run against the prior completed Phase 4 bundle produced all ten
aggregate tables without encounter identifiers. Figures, calculated
`No Sepsis` investigation, and organ-type attribution remain deferred.

## Analysis Template Method refactor

The owner subsequently superseded decision 3 above after reviewing the initial
approximately 900-line `main_analysis_phase4.py`. The owner requested a smaller
entry point and a comprehensible Template Method design under
`src_strategy/analysis/`.

The refactor now has:

- a 36-line `main_analysis_phase4.py` composition root;
- `AnalysisPipeline.run()` as the stable Template Method covering validation,
  loading, cohort preparation, table construction, output validation, and
  publication;
- `Phase4CoreAnalysisPipeline` as the concrete implementation;
- focused modules for configuration, cohort construction, category tables,
  outcome tables, vasopressor tables, and I/O; and
- a package README explaining the workflow and module responsibilities.

All focused tests still pass. A table-by-table golden comparison against the
pre-refactor smoke bundle found all ten aggregate Parquet tables exactly equal,
so the change is structural and does not alter the analysis results.

## Phase 4 aggregate figure implementation

The owner authorized creation of the legacy figure inventory from the
aggregate Parquet tables. The 19 figures supported directly by those tables are
retained. The six legacy patient-level strip/box plots are replaced with
aggregate-native range/IQR/median interval figures:

- one arrival-to-sepsis interval figure; and
- five length-of-stay agreement figures for Sepsis 1, Sepsis 2, Sepsis 3,
  POA-3, and NPOA-3.

The six replacements use `iqr_median_range` in their filenames so they cannot
be mistaken for the legacy patient-level plots. A thin line represents the
observed range after the analysis table's existing upper-tail filter, a thick
line represents the IQR, and a point represents the median.

`main_analysis_figures_phase4.py` and `Phase4FigurePipeline` now generate all
25 PNGs exclusively from a completed aggregate analysis bundle. The pipeline
validates the source manifest, table hashes, schemas, and row counts; it does
not load encounter identifiers. The new figure bundle contains a manifest with
hashes and is marked complete with `_SUCCESS` only after all configured figures
exist. A full smoke run against a completed prior clinical bundle generated all
25 non-empty figures, and representative charts were visually inspected.
