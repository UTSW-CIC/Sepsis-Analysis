# Phase 4 BP reconstruction review — 2026-11-10

## Review scope

Read-only review of BP collision handling, rolling SBP/measured-MAP
aggregation, hypotension-state reconstruction, optional episode filtering, and
the filtered-hypotension contribution to septic shock.

## Review findings

- Systolic BP and measured MAP are resolved as separate source events.
- The hypotension adapter applies strict SBP `<90`, SBP decline `>40`, and MAP
  `<65` thresholds using nullable three-state OR composition.
- BP and shock interval adapters clear numeric evidence at the exact eight-hour
  expiration boundary.
- The generic aggregate table itself retains a BP value at the exact eight-hour
  boundary because its rolling SQL window is inclusive, but the downstream BP
  and shock criteria explicitly mask that expired value.
- The BP feature registry does not restrict SBP or MAP to one source `Type` and
  does not retain source `Type`, `Event_ID`, or `Event_Name`; only the selected
  source timestamp is retained.
- Focused validation completed with 48 passing tests.

## Owner answers

### BP source type

Question: Should both BP features accept only `Type="Flowsheet"`?

Owner answer: "Not necessarily."

Consequence: Do not add a flowsheet-only restriction. The exact set of
qualifying source types remains unspecified and must be clarified before any
source-type filtering is implemented.

### BP episode filter

Question: Should the BP duration filter remain disabled?

Owner answer: "Actually bp_episode_filter is not a part of the algorithm so it
should be enabled all the time."

This answer requires clarification because the current implementation makes
the filter classification-active when enabled:

- `main_strategy_phase4.py` reconstructs and filters BP episodes only when
  `bp_episode_filter_config.enabled` is true;
- `attach_effective_hypotension()` then attaches the filtered effective state;
- the septic-shock pipeline changes raw SBP/MAP criteria to evidence-only and
  uses `effective_hypotension_flag` as the BP contribution; and
- short positive episodes removed by the filter therefore no longer qualify
  through a BP shock pathway.

### Final clarification

The owner confirmed that the BP episode filter **is part of the algorithm and
must always be enabled by default**. Therefore, filtered effective hypotension,
rather than the unfiltered raw SBP/MAP flags, is the intended BP contribution
to septic-shock classification. The current configuration value
`bp_episode_filter_config.enabled=False` does not match this approved default.

No configuration or clinical code was changed because the clarification did
not itself authorize implementation.

### Scope of any modification

Owner direction: If the current implementation does not affect
`attach_effective_hypotension`, which is used by the septic-shock pipeline, no
modification is needed as long as it works correctly.

Review consequence: Enabling the filter does affect
`attach_effective_hypotension` and septic-shock composition as described above.
No clinical code was modified during this review.

## Implementation update

After explicit implementation authorization, the BP episode filter default was
changed to enabled and both active strategy scripts now always construct and
apply the effective-hypotension episodes used by Sepsis 3 Pathway A. The raw BP
episode evidence remains available for audit.
