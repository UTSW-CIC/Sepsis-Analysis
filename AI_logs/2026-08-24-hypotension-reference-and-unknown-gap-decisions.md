# Hypotension Reference and Unknown-Gap Decisions — 2026-08-24

## Confirmed Decisions

- `Baseline_SBP` is the team-approved reference point for evaluating an SBP
  decline greater than 40 mmHg.
- An unknown hypotension episode is removed and its neighboring known episodes
  are merged only when both neighboring episodes have the same state:
  - `True → null → True` becomes one `True` episode.
  - `False → null → False` becomes one `False` episode.
- Different known states separated by an unknown episode are not merged. For
  example, `True → null → False` remains separate `True` and `False` episodes,
  and the unknown interval is not assigned to either known state.
- Leading and trailing unknown episodes cannot be merged because they do not
  have known episodes on both sides.
- No maximum unknown-gap duration was specified; the merge decision depends on
  matching states immediately before and after the unknown episode.

## Hypotension Components

The approved component logic remains:

- SBP hypotension: current SBP `< 90` **or**
  (`Baseline_SBP - current SBP`) `> 40`.
- MAP hypotension: directly measured MAP `< 65`.
- Combined hypotension: either approved component is positive, while missing
  evidence remains distinguishable from a measured negative result.

