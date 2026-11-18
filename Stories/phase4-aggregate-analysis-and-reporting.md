Title: Deliver versioned aggregate Phase 4 analysis and figures

Description: As a clinical and billing review team member, I want reproducible aggregate tables and figures derived from a completed Phase 4 run, so that category agreement, outcomes, and ICU use can be reviewed without exposing patient identifiers.

Acceptance criteria:
- The analysis pipeline validates `_SUCCESS`, the clinical manifest, declared tables, hashes, schemas, and encounter uniqueness before analysis.
- The analysis cohort contains calculated-positive-sepsis encounters and excludes billed `UPOA-*` encounters before every denominator.
- Aggregate category, POA/NPOA, agreement, mortality, time-to-sepsis, length-of-stay, vasopressor, and ICU tables contain no encounter identifiers.
- The Template Method pipeline separates validation, loading, cohort preparation, table construction, output validation, and publication behind a small composition root.
- Analysis and figure bundles record source-run identity, parameters, schemas, row counts, and hashes, and publish `_SUCCESS` only after all outputs validate.
- The mortality output includes a complete calculated-versus-billed 3x3 severity grid with cell and marginal deaths, encounters, and rates; empty cells display as unavailable.
- LOS distributions are persisted as patient-neutral frequency tables and expanded only in memory for the five jittered stripplot-plus-boxplot figures.
- ICU outputs include six-category and collapsed-severity heatmaps, computed/billed diverging status bars, within-category percentages, shared paired scales, and mutually exclusive Sepsis 3 pathway groups.
- The figure pipeline renders only from completed aggregate analysis tables and produces a complete, hash-validated bundle.
- Focused tests, golden table comparisons, smoke runs, and visual inspection validate that refactoring and reporting changes preserve aggregate results.

Story hours: 36

title: Build the completed-run analysis pipeline

Description: Validate versioned clinical inputs, construct the approved analysis cohort, and generate the active patient-neutral aggregate table inventory.

working hours: 7

Priority: 1

title: Refactor analysis with Template Method

Description: Move the stable workflow into `AnalysisPipeline.run()` and separate cohort, category, outcome, vasopressor, configuration, and I/O responsibilities behind a small entry point.

working hours: 5

Priority: 2

title: Build aggregate-only figure publication

Description: Render the configured figure inventory from validated aggregate tables and publish a versioned bundle with manifests, hashes, and completion validation.

working hours: 6

Priority: 1

title: Add mortality and LOS reporting

Description: Create the mortality severity grid, patient-neutral LOS frequency table, mortality heatmap, and restored LOS jittered stripplot-plus-boxplot figures.

working hours: 6

Priority: 2

title: Add ICU category and pathway reporting

Description: Create ICU heatmaps and diverging bars with percentages, paired scales, and mutually exclusive Organ Dysfunction, Vasopressors, Both, and Neither pathway segments.

working hours: 7

Priority: 2

title: Validate aggregate results and figures

Description: Add synthetic and regression tests, compare refactored tables against golden outputs, run complete smoke bundles, and visually inspect representative charts.

working hours: 5

Priority: 2
