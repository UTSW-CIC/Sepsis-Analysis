# Minimum Positive-Duration Filter — 2026-09-08

## Project-Owner Decision

Question: Should a positive episode exactly equal to the configured minimum-
duration threshold be retained or removed?

Answer: Retain it. The approved comparison is:

```text
episode_duration_minutes >= threshold_minutes
```

## Implementation Scope

- Add minimum positive-duration filtering as a separate episode
  transformation.
- Return only positive episodes meeting the configured threshold.
- Preserve their existing episode IDs, source lineage, and all other columns.
- Keep the unfiltered input available to the caller for audit comparison.
- Do not select a clinical threshold, activate pipeline filtering, or change
  encounter classification.

## Implementation Completed

- Added `filter_short_positive_episodes()` to
  `src_strategy/events/episode_filter.py`.
- The helper validates a finite, non-negative threshold and valid episode
  states/durations.
- Retained rows keep their existing episode IDs, source-event lineage, and all
  input columns.
- Added focused tests for below/equal/above-threshold behavior, exclusion of
  negative and unknown episodes, a zero threshold, invalid thresholds, empty
  input, and lineage preservation.

## Validation

- `conda run -n ED python -m pytest tests/test_episode_filter.py -q`
  completed with 36 passing tests.
- The broader `tests/` suite could not be collected in the current `ED`
  environment because `pydantic` is not installed. Six existing test modules
  failed during import; no broader test cases ran.
- Git's focused diff check reported no whitespace errors.

## Next Work

1. Project-owner review of this isolated transformation.
2. Reconstruct exact SIRS measurement/expiry intervals.
3. Before that adapter is implemented, confirm how insufficient SIRS evidence
   is represented and which encounter timestamp clips a final interval.
