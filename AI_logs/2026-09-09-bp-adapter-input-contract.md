# Blood-Pressure Adapter Input Contract — 2026-09-09

## Clarification and Answer

Question: Should `build_bp_state_segments()` use normalized raw-event `sys` and
`map` columns, or the temporally aggregated `last_sbp_8h` and `last_map_8h`
features with their source timestamps?

Project-owner answer: Approved use of the aggregated features and their source
timestamps.

## Implementation Boundary

- The encounter table supplies the separately approved `Baseline_SBP` value.
- A missing encounter-table row is retained as missing baseline evidence rather
  than silently dropping the aggregated encounter. The segment output includes
  `baseline_encounter_row_available` to distinguish that condition from an
  encounter row whose baseline value is null.
- MAP is the measured-only aggregated MAP established by the upstream ingestion
  and aggregation workflow; the adapter does not read or calculate raw MAP.
- The adapter reconstructs measurement and eight-hour expiration change points,
  clipped at the encounter's final aggregated event.
- Hypotension episode filtering has independent exploratory settings and remains
  disabled. It does not feed encounter classification.

## Validation Finding

The adapter was checked in memory against the saved measured-MAP aggregation
and encounter artifacts without writing patient-level outputs. Eighteen
aggregated encounters had no matching encounter-table row; these were retained
with the availability flag described above. One of those encounters had no
observable positive-duration interval because its timeline ended at its sole
event.

At eligible backbone timestamps, comparison with the documented three-state
hypotension rules found 5,202 differences across 8,014,905 rows. Every
difference occurred exactly eight hours after an SBP or MAP source measurement.
The saved aggregator still carries evidence at that exact boundary, whereas
the clinical-definition document says the flag clears when the validity period
elapses and the existing SIRS interval adapter also uses half-open validity.
The BP adapter therefore clears the measurement at exactly eight hours. No
aggregator behavior was changed in this increment.

Notebook 27's direct nullable Boolean `|` expression also does not implement the
approved rule that any positive component establishes combined hypotension when
another component is unknown. The adapter uses an explicit three-state OR:
positive if either component is positive, negative only if both are measured
negative, and unknown otherwise. The notebook was not modified.

## Files and Test Results

- Added `src_strategy/events/hypotension/episode_adapter.py` and its package
  export.
- Added an independent, disabled `bp_episode_filter_config`.
- Added `tests/test_bp_episode_adapter.py` with synthetic coverage of component
  drivers, strict thresholds, driver changes, missing evidence, expiration,
  final-event clipping, multiple encounters, input validation, and the shared
  episode-filter contract.
- Focused BP and shared episode tests: 57 passed.
- Maintained suite excluding two documented pre-existing failures: 92 passed.
- The complete maintained suite: 92 passed and two pre-existing tests failed
  (SIRS enabled-setting mismatch and suspected-infection earliest-pair
  reduction mismatch).
- Python compilation and Git whitespace checks passed.
