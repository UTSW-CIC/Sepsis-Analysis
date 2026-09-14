# Pulmonary Dysfunction Implementation (2026-09-14)

## Approved Decisions

The project owner approved the following pulmonary state behavior:

1. Ventilator-dependence diagnosis codes (`Z99.11`, `Z93.0`) or
   `$ Home Vent Used` exclude pulmonary dysfunction for the entire encounter.
   The pulmonary state is forced to `0`, while the exclusion reason and source
   evidence remain in the output.
2. Pulmonary state before the first start or termination transition is null,
   representing unknown rather than measured negative.
3. If start and termination evidence occur simultaneously, termination wins.
4. Each decision must be documented with an inline comment immediately above
   its implementation.

## Step 1 — Configuration and Input Contract

- Replaced the obsolete pulmonary configuration with explicit start,
  termination, exclusion, P/F evidence, transition, and output fields.
- Corrected the case-sensitive documentation grouper names to match the source
  data and clinical document.
- Added the documented `BiPAP` mechanical-support value.
- Defined required raw-event and P/F-evidence input columns.
- Added validation for nonpositive P/F thresholds and pairing windows and for
  overlapping Vent On/Off start/termination values.

No pulmonary clinical flags or state transitions are implemented in Step 1.

## Steps 2–3 — Start and Termination Strategies

- Added registry-selected pulmonary start strategies for vent documentation,
  Vent On/Off, mechanical oxygen delivery, and paired P/F ratio `< 200`.
- Added registry-selected termination strategies for vent documentation,
  Vent On/Off, non-mechanical oxygen delivery, and paired P/F ratio `> 200`.
- Exact P/F ratio `200` is neither a start nor a termination transition.
- Missing or unpaired P/F evidence remains null rather than becoming negative.

## Step 4 — Encounter Exclusions

- Added an auditable exclusion-evidence dataframe retaining every matching
  diagnosis/home-vent source row, reason, and timestamp.
- Implemented the approved encounter-wide forced-zero behavior without
  deleting the supporting evidence.

## Step 5 — State Reconstruction

- Reconstructs the nullable pulmonary state at encounter bounds and transition
  instants and exposes half-open state segments.
- Implements the approved termination-wins tie rule and retains every
  simultaneous transition type.
- Keeps state null before the first transition unless an encounter exclusion
  forces state zero.

## Step 6 — Temporal Wide-Table Attachment

- Added a backward as-of attachment that carries the latest pulmonary state
  and evidence to each aggregate instant.
- Rejects null/duplicate keys and pre-existing output columns.
- Verifies that row count, order, and all existing aggregate values remain
  unchanged.

## Step 7 — Organ Composition

- Registered pulmonary as the sixth organ-dysfunction strategy.
- The organ criterion maps the already reconstructed nullable pulmonary state
  to `pulmonary_failure_flag`; it does not recalculate clinical evidence.

## Step 8 — Active Composition

- Wired P/F evidence, pulmonary state/segments, wide-table attachment, baseline
  preparation, and six-organ composition into `main_strategy.py`.
- Uses only new `_v1.parquet` output names.
- Checks all output targets before saving and raises `FileExistsError` if any
  exists, preventing overwrites or partial updates caused by existing targets.

## Validation

- Pulmonary/P/F/organ focused suite: `74 passed`.
- Python compilation succeeded for `main_strategy.py` and all changed clinical
  modules.
- Maintained `tests/` suite: `165 passed`, with three unrelated existing
  failures: SIRS and BP episode-filter configs are enabled while their tests
  expect disabled defaults, and one suspected-infection pair-reduction test
  returns six rows instead of two.
- Unscoped repository discovery also encounters the legacy `main_test.py`,
  which imports the removed `src.configs.dataconfig.input_output_config`.

## Confirmed Runtime Configuration

- The project owner confirmed that the SIRS and blood-pressure episode filters
  are intentionally enabled. Their enabled state is therefore not a pulmonary
  implementation defect and must not be changed without a new request.

## Approved Next-Step Sequence

1. **Integrate pulmonary dysfunction with `main_strategy.py`.** The code is
   already wired into the active composition script; the remaining work is a
   controlled real-data run and validation of the new versioned outputs.
2. **Integrate pulmonary dysfunction with combined organ dysfunction.** The
   pulmonary strategy is already registered as the sixth organ and included in
   `organ_dysfunction_total`; the remaining work is real-data validation of the
   attached state, evidence columns, and total.
3. **Categorize Sepsis 2.** After the two integrations above are validated,
   implement the approved composition of suspected infection plus at least one
   organ dysfunction. Preserve onset/state evidence and timestamps for later
   POA/NPOA classification rather than reducing immediately to only an
   encounter-level boolean.

Do not start Sepsis 2 composition until pulmonary/organ integration is
validated and the existing suspected-infection cardinality failure is reviewed.
