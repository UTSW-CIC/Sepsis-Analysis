# Phase 4 pipeline presentation clarification — 2026-11-16

## Request

Draft a PowerPoint-style Markdown presentation that maps the workflow and
persisted output data models of the Phase 4 pipeline using only invoked Python
code and configuration under `src_strategy/`. Do not inspect data or notebook
outputs. Emphasize clinical implementation and explain the versioned output
tree separately.

## Clarification

The original request referred to both `main_analysis_phase4.py` and
`main_strategy_phase4.py`, which are different pipelines.

## Owner answer

Use `main_strategy_phase4.py` as the entry point.

## Completed work

Created the Marp-compatible draft:

`docs/ppts/phase4_pipeline_workflow_and_data_model.md`

The presentation was derived only from the entry point and its invoked
`src_strategy/` Python/configuration path. No patient data, notebook results,
or persisted output metadata were inspected. It covers the clinical workflow,
data grains, code-defined schemas, all 33 versioned clinical output filenames,
mutable caches and monitoring artifacts, the run directory tree, Git-backed
run identity, manifest structure, and publication validations.

## Validation

- Confirmed every Parquet filename declared in `clinical_outputs` appears in
  the presentation.
- Used empty, schema-only Polars frames to verify builder output contracts;
  no patient rows were loaded.
- Confirmed Markdown code fences are balanced.
- `git diff --check` passed for the new files.
