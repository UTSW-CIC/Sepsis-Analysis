# Session handoff — analysis redesign — 2026-11-10

## Session close

The Phase 4 clinical pipeline now composes Sepsis 1, Sepsis 2, and Sepsis 3
encounter summaries into `df_sepsis_encounters.parquet`. Commit `b8c2427`
contains that implementation. The combined table retains the component
summary fields and adds:

- maximum calculated sepsis severity over the encounter;
- first sepsis onset across all positive severities;
- Arrival + 48-hour POA/NPOA classification, inclusive at the boundary;
- `No Sepsis` for severity 0 with null onset and POA status;
- the unchanged billed `Sepsis_Category` and a direct match indicator; and
- the approved encounter-level outcome/timing columns needed by analysis.

The run identity is now configured as dataset `phase4_2026-06-05` and clinical
definition `4`. A new versioned Phase 4 run is still required before an output
bundle will contain `df_sepsis_encounters.parquet`; finalized prior bundles
remain immutable.

## Next-session objective

The next session is **design and brainstorming only**. Review and agree on the
analysis contract before refactoring or implementing `main_analysis.py`.

Redesign `main_analysis.py` to accept a completed versioned output folder from
`main_strategy_phase4.py`. Preserve useful analyses from the current legacy
pipeline and add criterion-attribution analyses explaining the distributions
behind calculated sepsis categories.

The first new analysis requested by the owner is an encounter-level account of
which organ-dysfunction criteria are most common among encounters categorized
as Sepsis 2. The broader design should consider analogous distributions for:

- suspected-infection criteria;
- individual SIRS criteria and qualifying SIRS episodes;
- organ-dysfunction types and combinations;
- Sepsis 3 pathways and their hypotension, lactate, Sepsis 2, and vasopressor
  evidence;
- POA versus NPOA calculated categories;
- billed versus calculated categories; and
- mortality and length-of-stay outcomes by category and evidence pattern.

These analyses are descriptive attribution/co-occurrence unless the owner
explicitly approves a causal interpretation.

## Proposed analysis data flow for discussion

1. Treat `df_sepsis_encounters.parquet` as the one-row-per-encounter cohort
   spine.
2. Validate `_SUCCESS`, `manifest.json`, required filenames, schemas, and
   encounter uniqueness before analysis.
3. Load detailed evidence tables only for the selected analysis. Avoid eagerly
   loading the full bundle.
4. Reduce evidence to an explicitly approved encounter-level grain before
   calculating prevalence or distributions.
5. Produce aggregate tables and figures without exporting patient identifiers
   or raw patient-level records.
6. Record the clinical-run identity/configuration hash and analysis parameters
   with the analysis outputs.

## Important evidence-grain warning

The association outputs retain every qualifying association in every
independent infection-anchor window; they are not one row per encounter or one
row per window:

- Sepsis 1 grain: encounter + infection anchor + SIRS episode.
- Sepsis 2 grain: encounter + infection anchor + selected first organ episode
  per organ type.
- Sepsis 3 grain: encounter + infection anchor + pathway + shock-evidence key.

Overlapping infection windows can reuse the same evidence. Counting association
rows directly would therefore over-weight encounters with many anchors or
events. All criterion-distribution analyses must first define their denominator
and deduplicate to the approved encounter/evidence grain.

The reviewed Phase 4 run contained 9,274,379 Sepsis 3 association rows and a
25.97 GB association file. The redesigned analysis must use lazy/selective
column reads or smaller normalized evidence tables; it should not eagerly load
that table merely to obtain encounter classifications.

## Design decisions required before implementation

1. For “organ dysfunction resulting in Sepsis 2,” should the denominator be:
   all `sepsis_2_flag == 1` encounters, only encounters whose final maximum
   severity is 2, or both as separate views?
2. When one encounter has multiple qualifying organ types, should each organ
   receive one encounter-level count, should organ combinations be analyzed,
   or should one primary/earliest organ be selected?
3. Should criterion distributions represent the first qualifying association,
   evidence supporting the final category, or any qualifying evidence during
   the encounter?
4. Which legacy `main_analysis.py` tables and figures remain required, and
   which duplicated or obsolete outputs should be retired?
5. How should billed `UPOA-*` categories be displayed in comparisons? They
   should not be silently discarded.
6. Which analysis artifacts are required: aggregate Parquet/CSV tables,
   figures, a notebook, or a generated report?

## Recommended initial implementation boundary after design approval

Implement the smallest analysis slice first:

- completed-run loader and schema validation;
- canonical encounter cohort from `df_sepsis_encounters.parquet`;
- calculated-versus-billed category counts;
- POA/NPOA counts using Arrival + 48 hours; and
- encounter-level organ-dysfunction prevalence for the approved Sepsis 2
  denominator.

Validate this slice with synthetic grain/denominator tests and aggregate golden
outputs before migrating mortality, LOS, vasopressor, ventilation, or
two-experiment comparisons.

## Session-start reading order

1. This handoff.
2. `AI_logs/2026-11-10-final-sepsis-encounter-composition.md`.
3. `main_analysis.py` and the legacy modules under `src/analysis/`.
4. The manifest and schemas from the newly regenerated Phase 4 clinical run.

Do not begin implementation until the owner reviews the proposed analysis
denominators, evidence grain, retained legacy outputs, and artifact format.
