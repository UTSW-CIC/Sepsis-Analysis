# First-organ-per-type Sepsis 2 implementation — 2026-09-16

## Owner request

Implement only these two steps from the 2026-09-15 handoff:

1. Keep the earliest positive organ-dysfunction episode for each of the six
   organ types in an encounter.
2. Exclude every later positive episode of the same organ type.

Wait to design or execute the comparison with the all-episode method until the
owner plans it jointly with the assistant.

## Implementation

- Added `select_first_organ_episodes_by_type()` in
  `src_strategy/events/sepsis/sepsis2.py`.
- Selection occurs before suspected-infection temporal association. Therefore,
  a later episode cannot qualify when the first episode of the same organ type
  does not overlap an infection window.
- Selection uses the earliest `organ_episode_start` per encounter and
  configured organ type. `organ_episode_id` is the deterministic tie-breaker.
- A combined organ episode can be first for more than one organ type. It
  remains one episode row, with all selected types retained in the configured
  `first_organ_dysfunction_types` list column. This avoids duplicating Sepsis 2
  and downstream Sepsis 3 association rows while preserving audit evidence.
- The selector follows `OrganDysfunctionConfig.selected`; the default registry
  contains cardiovascular, pulmonary, renal, hepatic, coagulation, and
  neurological dysfunction.

## Focused validation

- `conda run -n ED python -m pytest tests/test_sepsis2.py -q`: 7 passed.
- `conda run -n ED python -m pytest tests/test_sepsis3.py tests/test_sepsis2.py -q`:
  12 passed.
- Regression coverage verifies both multiple organ types on one first episode
  and the rule that a later in-window renal episode cannot rescue an earlier
  out-of-window renal episode. It also verifies that equal-start ties select
  the lower episode identifier regardless of input row order.
- `git diff --check` passed.

## Broader suite status

`conda run -n ED python -m pytest tests -q` completed with 195 passed and 20
failures. None of the failures were in the changed Sepsis 2 or downstream
Sepsis 3 tests. The failures reflect pre-existing stale pulmonary-termination,
SIRS-filter, and suspected-infection expectations after recent approved
configuration decisions; those files were not changed as part of this scoped
request.

## Explicitly deferred

- No all-episode versus first-per-organ comparison was designed or run.
- No encounter counts, discordance results, or patient-level output were
  generated.
