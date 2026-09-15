# Septic Shock Strategy/Registry Implementation (2026-09-14)

## Project-Owner Decision

Question: Should vasopressor medication orders qualify as septic-shock
evidence, and what constitutes a qualifying vasopressor event?

Answer: Exclude medication orders. A qualifying event is an actual Medication
Administration row for vasopressin, phenylephrine, norepinephrine, or
epinephrine with a recorded positive numeric dose. Zero and null doses do not
qualify. Nonqualifying vasopressor rows remain available for audit.

The approved implementation timestamps vasopressor shock evidence at the
administration instant and does not use the existing unapproved 24-hour
vasopressor carry-forward.

## Clinical Rules

Source: `docs/clinical_definitions 3_1.docx`.

- Most-recent valid SBP is strictly below 90 mmHg. This criterion is
  independent of baseline availability.
- `Baseline_SBP` minus most-recent valid SBP is strictly greater than 40 mmHg.
  `Baseline_SBP` remains the previously approved representation of average
  SBP.
- Most-recent valid measured MAP is strictly below 65 mmHg.
- Most-recent valid lactate is strictly greater than 4.0 mmol/L.
- A qualifying administered vasopressor dose occurs.
- Any positive component produces `septic_shock_flag = 1`; otherwise the final
  flag is `0`. Missing numeric evidence remains null in its component flag.
- SBP and MAP evidence expire at eight hours and lactate evidence at six
  hours. Evidence is cleared at the exact expiration instant.

## Implementation

- Added five selectable septic-shock criterion names and a registry-backed
  pipeline.
- Added nullable component strategies for SBP, SBP decline, measured MAP, and
  lactate, plus an exact-time vasopressor strategy.
- Added `AnyReducer` for boolean OR composition while retaining every component
  flag.
- Added an event-level vasopressor evidence table that retains orders, zero
  doses, null doses, and qualifying administrations with an explicit
  qualification flag.
- Added preparation that left-joins `Baseline_SBP`, marks whether an encounter
  baseline row was available, and attaches exact-time vasopressor counts
  without changing the timeline row set.
- Removed an obsolete hypotension-adapter check that expected the
  baseline-independent SBP `<90` configuration to contain a baseline field.
  The adapter's clinical calculations did not change.
- Wired vasopressor evidence and septic-shock scoring into `main_strategy.py`
  using new `df_vasopressor_evidence_v1.parquet` and
  `df_septic_shock_v1.parquet` outputs.
- No Sepsis 1/2/3 categorization was implemented in this increment.

## Validation

- Focused septic-shock suite: 10 passed.
- Septic-shock plus compatible BP-adapter tests: 24 passed and one known
  enabled-setting expectation deselected.
- Maintained `tests/` suite: 175 passed and three previously documented tests
  failed: SIRS and BP episode-filter configurations are intentionally enabled
  while their tests expect disabled defaults, and suspected-infection
  antibiotic/culture reduction retains six evidence rows while its test
  expects the earliest pair's two rows.
- Python compilation and Git whitespace validation passed.
- An in-memory real-data smoke test reconstructed the reviewed pulmonary and
  six-organ path, then scored all 8,029,837 timeline rows without saving
  patient-level output. It retained 65,619 vasopressor evidence rows, of which
  65,590 were qualifying administration rows. These mapped to 65,503 positive
  timeline instants because multiple administrations may share a timestamp.
  The final shock flag was positive on 1,227,916 timeline rows. No patient-level
  data were printed or saved.

## Required Reminder Before Sepsis 2

Before Sepsis 2 categorization, bring pulmonary dysfunction into full
four-tier alignment with `clinical_definitions 3_1.docx`. The current pulmonary
implementation uses a standalone P/F `<200` transition and does not implement
the high-flow or non-rebreather tiers. Also resolve the suspected-infection
episode-reduction output contract before any final severity composition.

## Superseding Hypotension-Filter Decision

Question: When `bp_episode_filter_config.enabled` is true, should the existing
BP duration filter affect the BP contribution to septic-shock classification?

Answer: Yes. This supersedes the earlier exploratory-only boundary for the BP
filter. Do not rebuild the filtration process; reuse `build_bp_state_segments`
and `run_episode_filter` from the existing main composition.

Approved mapping:

- Preserve the raw SBP `<90`, SBP-decline, and MAP `<65` component flags for
  audit.
- When the BP filter is disabled, the raw BP components contribute directly to
  septic shock.
- When it is enabled, only original positive BP episodes represented in the
  filter's retained source lineage contribute to shock.
- A removed short positive episode maps to effective hypotension `0`.
- A measured-negative gap absorbed during episode merging remains `0`; it is
  not relabeled as hypotension.
- An unknown gap absorbed during bridging remains null.
- A measurement at the encounter's final event has no observable interval and
  therefore does not establish effective hypotension when filtering is
  enabled.
- Lactate and administered-vasopressor shock pathways remain independent of BP
  duration filtering.

## Hypotension-Filter Integration

- Added a small adapter that consumes the existing `raw` and `filtered` episode
  outputs and uses `source_episode_ids` to mark retained original positive
  episodes. It does not rerun or duplicate any filtration logic.
- Added a backward as-of attachment of effective hypotension to the aggregate
  timeline using half-open episode intervals.
- Extended the pipeline criterion role contract with an evidence-only role so
  raw BP component flags remain visible without contributing twice when the
  effective filtered flag is active.
- Moved the existing BP reconstruction/filter calls before septic-shock
  calculation in `main_strategy.py`.
- Septic shock now uses the independent aggregate timeline rather than the
  organ-dysfunction output as its clinical input.
- Added `df_hypotension_episodes_effective_v1.parquet` to the common versioned,
  preflight-protected output set.

## Additional Validation

- Effective-hypotension, septic-shock, and compatible BP tests: 31 passed and
  one known enabled-setting expectation deselected.
- Maintained `tests/` suite: 182 passed with the same three documented failures.
- Python compilation and Git whitespace validation passed.
- An in-memory enabled-filter smoke test processed all 8,029,837 timeline rows.
  It reconstructed 6,083,436 BP segments and 419,831 raw BP episodes; 20,888
  merged positive episodes met the configured duration threshold. Raw shock
  was positive on 1,227,916 rows, while enabled filtered hypotension reduced
  that result to 1,222,418 rows. No patient-level data were printed or saved.
