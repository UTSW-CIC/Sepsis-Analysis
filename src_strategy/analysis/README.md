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
| `outcome_tables.py` | Mortality, time-to-sepsis, LOS summaries, and patient-neutral LOS frequencies |
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
it never reads encounter-level clinical tables. It creates 33 figures:

- 24 figures corresponding to the legacy `CoreAnalysis` outputs.
- One mortality-rate heatmap crossing computed Sepsis severity 1/2/3 with
  billed Sepsis severity 1/2/3. Cells and margins show mortality with their
  death-count and encounter-count denominators.
- Two ICU encounter-count heatmaps crossing the primary Arrival + 48-hour
  computed classification with billing: one uses all six POA/NPOA categories
  and one collapses them to Sepsis severity 1/2/3. Cells and margins show ICU
  encounter counts.
- Four ICU-status diverging barplots for computed severity, billed severity,
  computed POA/NPOA category, and billed POA/NPOA category. ICU-positive counts
  point upward and ICU-negative counts point downward. Each nonzero bar is
  labeled with its encounter count and its percentage of encounters with a
  non-null ICU status in that classification.
- One Sepsis 3 ICU-status diverging barplot comparing computed and billed
  Sepsis 3. Each direction is stacked into Organ Dysfunction Pathway,
  Vasopressors Pathway, Both Pathways, and Neither Pathway using computed
  clinical evidence.
- One aggregate-native replacement for the patient-level arrival-to-sepsis
  strip/box plot. It shows the range as a thin line, IQR as a thick line, and
  median as a point.

The five legacy LOS stripplot-plus-boxplot figures are reconstructed from a
patient-neutral frequency table. Persisted analysis artifacts contain no
encounter identifiers; encounter-frequency rows are expanded only in memory
while rendering the figures.

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
