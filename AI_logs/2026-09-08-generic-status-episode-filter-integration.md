# Generic Status Episode-Filter Integration — 2026-09-08

## Project-Owner Decisions

- The episode filter must be reusable for any clinical status, not only SIRS.
- Each status-specific adapter must produce explicit, contiguous half-open
  segments with normalized states: `1` positive, `0` negative, and `-1`
  unknown.
- Unknown episodes may be bridged when directly surrounded by the same state;
  this behavior is configurable per status and is enabled for SIRS.
- Each status has independent configuration. The exploratory negative-gap and
  minimum-positive-duration defaults are both 20 minutes.
- Filtering is disabled by default and must not change encounter
  classification.
- A final segment ends at the encounter's last event. A state beginning at that
  last event has zero observable duration and is omitted.
- For SIRS, only a null SIRS score maps to the unknown state. The current SIRS
  reducer produces numeric scores, so initial SIRS segments normally have no
  unknown state.

## Implementation

- Added `EpisodeFilterConfig` and a disabled SIRS instance.
- Added `run_episode_filter()` as the clinical-neutral composition of raw
  episode construction, optional unknown bridging, short negative-gap merging,
  and minimum positive-duration filtering.
- When unknown bridging is disabled, the bridge stage retains all episodes and
  initializes the lineage columns required downstream.
- Added strict state validation so fractional values cannot be silently cast to
  clinical states, and added non-positive interval validation to the unknown
  bridge.
- Added a SIRS adapter that reconstructs change points from source measurement
  timestamps and configured validity periods, recalculates SIRS at those
  points, and emits normalized segments clipped to the first/last encounter
  event.
- Wired SIRS into `main_strategy.py` behind the disabled configuration and
  added separate segment/raw/bridged/merged/filtered artifact names.
- No filtered result feeds Sepsis classification.

## Validation

- Focused episode-filter and SIRS-adapter suite: 48 passed.
- Maintained `tests/` suite: 78 passed with one existing suspected-infection
  failure concerning earliest antibiotic/culture episode reduction.
- Changed Python files compile successfully.
- Git diff whitespace validation reports no errors.

## Next Review

1. Review the generic normalized-segment contract and SIRS expiration adapter.
2. Keep SIRS filtering disabled until aggregate/parity comparison with the
   reviewed notebook is approved.
3. Add another clinical status by implementing only its adapter and independent
   configuration; do not put status-specific logic in the generic runner.
