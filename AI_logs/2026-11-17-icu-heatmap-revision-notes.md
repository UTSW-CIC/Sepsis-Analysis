# ICU heatmap revision notes — 2026-11-17

## Review boundary

This note documents the current ICU heatmap changes using only:

- `src_strategy/analysis/category_figures.py`
- `src_strategy/analysis/figure_pipeline.py`

No analysis-table builders, configuration modules, tests, patient data,
generated figures, or other project files were inspected. The observations
below therefore describe the rendering and pipeline wiring visible in these
two files, not an end-to-end validation of the underlying counts.

## Summary of the change

The active figure pipeline now renders percentage-based versions of both ICU
computed-versus-billed heatmaps:

1. The six-category POA/NPOA heatmap.
2. The three-severity Sepsis 1/2/3 heatmap.

The prior renderers color cells by raw ICU encounter count and annotate each
cell and margin with counts. The new renderers color cells by each cell's share
of all ICU encounters represented in that crosstab and annotate cells and
margins with both a percentage and a count fraction.

## Category heatmap

The active category renderer is
`plot_icu_by_category_heatmap_claude_rate()`.

### Input contract used by the renderer

The function expects the following fields in `icu_by_category_crosstab`:

- `calculated_category`
- `billed_category`
- `encounter_count`
- `calculated_category_total`
- `billed_category_total`

Rows are placed into a square matrix using `config.category_order` for both
axes. A missing computed/billed combination remains zero in the initialized
matrix.

### Percentage and annotation semantics

- `grand_total` is the sum of every cell in the ICU count matrix.
- Each heatmap value is `cell_count / grand_total * 100`.
- Each cell label is `percentage` followed by `(cell_count/grand_total)`.
- Each row margin is `calculated_category_total / grand_total`.
- Each column margin is `billed_category_total / grand_total`.
- When the entire matrix is empty, the plotted matrix is `NaN` and annotations
  use `N/A (0/0)`.

This is a distribution of the ICU cohort across computed/billed category
pairs. It is not the ICU admission rate within each sepsis category.

### Presentation changes

- The color map changed from `Purples` to `Reds`.
- The color bar changed from `ICU encounter count` to
  `Share of ICU encounters (%)`.
- The color scale begins at zero and ends at the largest observed cell share,
  with a minimum upper bound of 1 percent.
- The title padding increased to make room for percentage-and-fraction column
  margins.
- The output filename remains
  `icu_encounter_count_computed_vs_billed_category_heatmap.png` even though the
  color encoding is now percentage-based.

## Severity heatmap

The active severity renderer is
`plot_icu_by_severity_heatmap_claude_rate()`.

### Input contract used by the renderer

The function expects the following fields in `icu_by_severity_crosstab`:

- `calculated_severity`
- `billed_severity`
- `icu_encounter_count`
- `calculated_severity_total`
- `billed_severity_total`

The axes are fixed to Sepsis 1, Sepsis 2, and Sepsis 3. Missing severity pairs
remain zero in the initialized 3-by-3 matrix.

### Percentage and annotation semantics

The severity heatmap uses the same denominator and label rules as the category
heatmap:

- cell color: `icu_encounter_count / grand_total * 100`;
- cell label: percentage plus `(cell_count/grand_total)`;
- row and column margins: their ICU totals divided by the same grand total;
- empty-matrix behavior: `NaN` colors and `N/A (0/0)` labels.

It also uses the `Reds` color map, an observed-maximum color scale, and a
`Share of ICU encounters (%)` color-bar label. Its output filename remains
`icu_encounter_count_computed_vs_billed_severity_heatmap.png`.

## Pipeline wiring

`Phase4FigurePipeline._render_category_figures()` now:

- imports and calls the two `_claude_rate` renderers;
- passes `icu_by_category_crosstab` to the category renderer;
- passes `icu_by_severity_crosstab` to the severity renderer; and
- leaves the imports and calls for the original count renderers commented out.

Because the old and new implementations use the same output filenames, only
one version of each heatmap can be published in a single figure bundle. The
current pipeline publishes the percentage-based versions.

## Points to decide during a future revision

1. **Final function names:** Replace the temporary `_claude_rate` suffix with
   audience-neutral names after the percentage design is approved.
2. **Count-renderer retention:** Either remove the old count functions and
   commented pipeline calls or publish count and percentage variants under
   distinct, explicit filenames.
3. **Filename semantics:** Rename the active files from `encounter_count` to a
   name that communicates `share` or `percentage`, unless downstream consumers
   require the existing filenames.
4. **Denominator wording:** Keep the color-bar and documentation explicit that
   percentages use all ICU encounters in the crosstab, not all encounters in a
   category and not the full encounter cohort.
5. **Color-scale comparability:** Decide whether each figure/run should retain
   its observed-maximum scale or use a fixed/shared upper limit. The current
   dynamic `vmax` makes color intensity unsuitable for direct comparison
   between the category and severity figures or between different runs.
6. **Sparse-input validation:** Consider validating exactly one row per matrix
   cell and checking that supplied row/column totals agree with the matrix.
   The current renderer treats missing cells as zero and relies on `.item()`
   for populated cells.
7. **Shared formatting helper:** The percentage annotation and empty-total
   logic are duplicated in both renderers. Consolidate only if both figures
   are expected to evolve together.
8. **Empty-cohort presentation:** Confirm whether an entirely empty heatmap
   should render as an all-`NaN` grid with repeated `N/A (0/0)` labels or show
   one explicit no-data message.
9. **Annotation density:** Recheck title padding, margin placement, and label
   readability whenever category labels, DPI, or figure dimensions change.

## Scope intentionally excluded

The ICU diverging barplots, shared y-axis limits, and Sepsis 3 pathway figure
also appear in these files but are outside this heatmap-specific note. Their
behavior was not documented here.
