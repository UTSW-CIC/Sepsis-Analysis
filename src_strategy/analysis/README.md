# Phase 4 analysis design

The analysis pipeline uses **Template Method** to keep the stable workflow in
one place while allowing future analyses to supply different cohorts and
tables.

```text
main_analysis_phase4.py
        |
        v
Phase4CoreAnalysisPipeline
        |
        v
AnalysisPipeline.run()
  1. validate completed clinical run
  2. load required clinical tables
  3. prepare the analysis cohort
  4. build aggregate tables
  5. validate patient-neutral outputs
  6. publish Parquet tables and manifest
```

## Module responsibilities

| Module | Responsibility |
|---|---|
| `pipeline.py` | Stable Template Method workflow |
| `phase4.py` | Phase 4 inputs and table composition |
| `config.py` | Categories, windows, filenames, and shared column names |
| `cohort.py` | Positive-sepsis cohort validation and preparation |
| `category_tables.py` | Category counts, POA counts, and crosstabs |
| `outcome_tables.py` | Mortality, time-to-sepsis, and LOS summaries |
| `vasopressor_tables.py` | Qualifying vasopressor-window analyses |
| `io.py` | Clinical-run validation and analysis-bundle publication |
| `category_figures.py` | Category, POA, mortality, and heatmap figures |
| `outcome_figures.py` | Time-to-sepsis, LOS, and mortality figures |
| `figure_config.py` | Stable figure inventory and presentation settings |
| `figure_io.py` | Analysis-bundle validation and figure publication |
| `figure_pipeline.py` | Composition of figures from aggregate tables |

`main_analysis_phase4.py` is only the composition root and command-line entry
point. It does not contain clinical or analytical transformations.

## Figures

`main_analysis_figures_phase4.py` reads a completed aggregate analysis bundle;
it never reads encounter-level clinical tables. It creates 25 figures:

- 19 figures corresponding to the legacy `CoreAnalysis` outputs.
- Six aggregate-native replacements for patient-level strip/box plots. These
  show the range as a thin line, IQR as a thick line, and median as a point,
  and use `iqr_median_range` in their filenames to prevent confusion with the
  legacy plots.

The figure directory is published only after all configured PNGs exist. Its
`figure_manifest.json` records their hashes and `_SUCCESS` marks completion.

```bash
python main_analysis_figures_phase4.py \
  --analysis-dir /path/to/completed-analysis \
  --output-dir /path/to/new-figure-directory
```

## Future extensions

The planned calculated-`No Sepsis` investigation and organ-type attribution
can reuse `AnalysisPipeline.run()` while providing their own cohort and table
builders. They should not be added to the current positive-sepsis table set
until their denominators and evidence-grain contracts are approved.
