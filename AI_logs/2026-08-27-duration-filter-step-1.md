# Duration Filter — Steps 1–3 (2026-08-27, updated 2026-09-01)

## Approved Direction

- Build SIRS and hypotension duration filtering incrementally, with project-owner
  testing and review after each step.
- Keep duration processing separate from row-wise Criterion/Reducer calculation.
- Preserve raw and transformed episode outputs for audit.
- Do not change the primary clinical classification while thresholds and
  remaining clinical semantics are unapproved.

## Implemented in Step 1

- Added `src_strategy/events/episode_filter.py`.
- Added a shared `build_state_episodes()` helper operating on explicit half-open
  `[segment_start, segment_end)` intervals.
- Standardized its clinical-neutral state input as `1` positive, `0` measured
  negative, and `-1` unknown.
- The helper sorts input, validates non-null keys and boundaries, rejects invalid
  states and non-positive intervals, and rejects timeline gaps/overlaps. Missing
  time must be represented explicitly as an unknown segment.
- Contiguous equal-state segments collapse into episodes; unknown episodes remain
  present for the separately reviewed bridging step.
- Episode IDs restart at one per encounter. Output retains duration and the count
  of contributing source segments.

## Validation

`conda run -n ED python -m pytest tests/test_episode_filter.py -q`

Result: 8 tests passed. Cases cover equal-state collapse, three-state retention,
unsorted multi-encounter input, encounter-local IDs, gaps, overlaps, invalid
states, non-positive intervals, and empty input.

## Implemented in Step 2

- Added `bridge_equal_states_across_unknown()` to the shared episode module.
- An internal unknown episode is bridged only when its immediately adjacent
  known episodes have the same state.
- Connected same-state/unknown chains collapse into one episode.
- Leading, trailing, and differently bounded unknown episodes remain explicit
  and are not assigned to either known state.
- Output episode IDs restart per encounter. `source_episode_ids`,
  `source_episode_count`, and `bridged_unknown_gap_count` preserve auditability.
- The helper rejects duplicate episode IDs, discontinuous timelines, invalid
  states, and input that has not already collapsed adjacent equal states.

Focused validation now reports 14 passing tests. New cases cover positive and
negative bridging, different surrounding states, encounter boundaries,
connected unknown chains, and independent multi-encounter grouping.

## Implemented in Step 3

- Added `merge_positive_across_short_negative_gaps()` to the shared episode
  module.
- A measured-negative episode is merged only when it is directly bounded by
  positive episodes and its duration is strictly less than the required
  `threshold_minutes` argument. Equality remains separate.
- Connected positive/short-negative chains collapse into one positive episode.
- Unmerged positive, negative, and explicit unknown episodes remain in the
  transformed timeline.
- Source episode IDs, episode and segment counts, and prior unknown-gap counts
  remain available. `bridged_negative_gap_count` records the measured-negative
  episodes absorbed by each output episode.
- The helper validates its threshold, required lineage, unique episode IDs,
  positive interval lengths, timeline continuity, and collapsed input states.
- No duration configuration, clinical adapter, pipeline activation, or
  classification change was added.

Focused validation now reports 29 passing tests. Step 3 cases cover strict
threshold boundaries, one and multiple connected gaps, retained leading,
trailing, negative, and unknown states, encounter-local grouping, combined
unknown/negative lineage, zero and invalid thresholds, empty input, and a
discontinuous input timeline.

The broader maintained `tests/` run reported 59 passing tests and one unrelated
existing failure: the antibiotic/culture test expects earliest-pair reduction,
while the current committed strategy retains all qualifying pairs. Collecting
the repository root also remains blocked by legacy `main_test.py` importing the
removed `src.configs.dataconfig.input_output_config` name.

## Not Yet Implemented

- Minimum positive-duration filtering or configuration.
- Exact SIRS measurement/expiry timeline reconstruction.
- Hypotension criteria or measurement/expiry timeline reconstruction.
- Infection/Sepsis 2 association or encounter classification integration.

## Questions Requiring Owner Decisions Before Relevant Steps

1. Whether filtered results remain a billing-review sensitivity analysis or may
   eventually replace the primary classification.
2. Whether insufficient SIRS evidence is an ordinary negative interval or a
   distinct unknown interval.
3. Whether an episode exactly equal to the minimum positive-duration threshold
   is retained or removed.
4. Which encounter timestamp clips a final episode when feature validity extends
   beyond discharge.
5. Whether hypotension threshold validation uses suspected-infection windows or
   only hypotension episodes overlapping Sepsis 2.

## Decision Confirmed 2026-09-01

- A measured-negative gap qualifies for short-gap merging only when its duration
  is strictly less than the configured threshold.
- A gap exactly equal to the threshold remains separate.

## Next Step After Owner Testing

Review Step 3 before selecting the next increment. Minimum positive-duration
filtering still requires the documented equality decision before implementation.
