# Session Handoff — 2026-08-24

## Decisions Confirmed

- `Baseline_SBP` is the team-approved reference for the SBP decline criterion.
- SBP hypotension is current SBP `< 90` **or** a decline from `Baseline_SBP`
  greater than 40 mmHg.
- Directly measured MAP `< 65` is an independent hypotension criterion.
- Consecutive unknown hypotension rows form an unknown episode.
- An internal unknown episode is bridged only when its immediately preceding
  and following known episodes have the same state:
  - `True → null → True` becomes one positive episode.
  - `False → null → False` becomes one negative episode.
  - Different surrounding states remain separate, and the unknown interval is
    assigned to neither state.
- No maximum duration was specified for bridging an unknown episode when both
  surrounding states match.

## Findings

- The matching duration-histogram peaks for SIRS and hypotension are primarily
  caused by their shared event-time backbone and common vital-sign charting
  cadence. Five-minute histogram bins display common 15-, 30-, 60-, and
  120-minute durations at centers such as 17.5, 32.5, 62.5, and 122.5 minutes.
- Both positive-duration plots currently use `< 12 * 24` against a duration
  measured in minutes, which limits the plots to 288 minutes. Use an explicitly
  approved unit conversion when revising these plots.
- The lactate/culture SQL can retain every qualifying lactate timestamp by
  joining all matches to `qualifying_episodes` without the rank-1 reduction.
  The current four-column long output still loses the association between a
  lactate episode and its supporting culture rows. An episode identifier or
  anchor column requires owner approval before changing that output contract.

## TODO — Optional Duration Filtering in the Pipeline

- [ ] After notebooks 26 and 27 are validated and approved, port their
  short-duration logic into the data pipeline as optional filtering stages:
  - notebook 26: SIRS episode filtering;
  - notebook 27: hypotension episode filtering.
- [ ] Keep both filters disabled by default until their thresholds and clinical
  use are approved, preserving current pipeline behavior.
- [ ] Make the short negative-gap threshold and minimum positive-duration
  threshold configurable rather than hard-coded.
- [ ] For hypotension, preserve the separately approved unknown-episode bridging
  rule rather than treating unknown evidence as a measured negative gap.
- [ ] Preserve raw and filtered episode outputs, onset timestamps, component
  evidence, source timestamps, and bridged-gap counts for audit and comparison.
- [ ] Add focused synthetic tests for exact threshold boundaries, leading and
  trailing gaps, connected positive-gap-positive chains, unknown episodes, and
  multiple encounters before enabling either filter.
- [ ] Compare optional-filter outputs with the reviewed notebook results and the
  unfiltered pipeline using aggregate, de-identified fingerprints.

## Status

No duration filtering was added to the pipeline during this session. The work
remains an explicitly deferred TODO pending notebook validation and threshold
approval.
