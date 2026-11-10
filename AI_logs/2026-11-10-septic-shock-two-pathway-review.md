# Septic-shock two-pathway requirement review — 2026-11-10

## Owner-proposed requirement

Septic shock is split into two independent pathways combined with OR:

1. hypotension **AND** lactate `>2` **AND** Sepsis 2 already active; or
2. suspected infection **AND** an administered vasopressor, with onset
   `min(infect_dt, vasopressor_order_time)`.

The owner requested review and confirmation of the requirement before any code
is written. No implementation is authorized at this stage.

## Current interpretation

### Pathway 1 — hypotension/lactate/Sepsis 2

- Hypotension is the approved composite of filtered effective BP evidence:
  SBP `<90`, baseline-to-current SBP decline `>40`, or measured MAP `<65`.
- The BP episode filter is classification-active and always enabled by default.
- Lactate uses a strict `>2` threshold and its configured six-hour validity.
- Hypotension and valid lactate `>2` must be simultaneously active.
- "Sepsis 2 flag already UP" requires a time-aware interpretation; using only
  the final encounter-level Sepsis 2 flag would permit future organ evidence to
  qualify earlier shock evidence retrospectively.

### Pathway 2 — infection/vasopressor

- This pathway is independent of Pathway 1.
- Suspected infection is required.
- A linked positive-dose vasopressor administration is required; an order
  without administration does not qualify under prior approved decisions.
- The medication order and administration should remain separately auditable.
- The proposed onset is the earlier of the infection anchor and linked
  vasopressor-order time.

## Material changes from the current implementation

- The current shock reducer uses OR across individual SBP `<90`, SBP decline
  `>40`, MAP `<65`, lactate `>4`, and vasopressor administration criteria.
- The new first pathway changes that to an AND composition and changes lactate
  from `>4` to `>2`.
- The current Sepsis 3 path begins from Sepsis 2 associations and validates that
  every Sepsis 3 encounter is a subset of Sepsis 2.
- If the new vasopressor pathway requires infection but not organ dysfunction,
  Sepsis 3 can be positive while Sepsis 2 is negative; the existing subset
  invariant would no longer be valid.
- Current vasopressor shock evidence is administration-time point evidence.
  The new requirement needs order/administration linkage and a retrospective
  order-based anchor.

## Pending owner confirmations

1. For Pathway 1, does "Sepsis 2 already UP" mean `sepsis_2_dt` must be at or
   before the instant when hypotension and lactate overlap, or must the
   qualifying organ-dysfunction episode still be active at that instant?
2. What is the Pathway 1 onset timestamp: the earliest contributing timestamp,
   `min(sepsis_2_dt, hypotension_start, lactate_result_dt)`, consistent with the
   project's retrospective onset rule?
3. Does Pathway 2 intentionally allow Sepsis 3 when Sepsis 2 is negative?
4. Must the infection and vasopressor evidence fall within a configured
   temporal window (for example, the existing plus/minus 48-hour window), or
   is occurrence anywhere in the same encounter sufficient?
5. If a positive administration has no linked medication order, does it still
   qualify, and if so, should administration time replace missing order time?
6. The proposed Pathway 2 onset can precede both infection confirmation and
   drug administration. Should the output retain a separate
   `criterion_met_dt = max(infection criterion completion, first positive
   administration)` in addition to the requested retrospective onset?

## Vasopressor modification

The owner subsequently clarified:

- Exclude vasopressors from generic Aggregator logic. The four rolling
  vasopressor features are not inputs to septic-shock classification.
- Represent qualifying vasopressor administrations as event-level flags.
- Associate an administration with suspected infection only when its
  administration timestamp is within plus/minus 48 hours of the infection
  anchor.
- For a qualifying infection/vasopressor association, attribute retrospective
  onset to `min(vasopressor_order_time, infect_dt)`.

This supersedes the earlier planned 24-hour carried-forward vasopressor state.
The medication order supplies a retrospective onset anchor but does not qualify
without an administration. Order time and administration time must remain
separate for audit.

### Owner confirmations

- The plus/minus 48-hour infection window is inclusive at both boundaries.
- A qualifying positive-dose administration without a linked medication order
  still qualifies. In that case, administration time replaces the missing
  vasopressor-order time in the onset calculation.
- Retain a separate criterion-completion timestamp in addition to the
  retrospective onset.

Accordingly, the vasopressor pathway timestamps are:

- `vasopressor_anchor_dt = coalesce(vasopressor_order_time,
  vasopressor_administration_time)`;
- retrospective onset `= min(infect_dt, vasopressor_anchor_dt)`; and
- criterion completion must be retained separately and cannot precede the
  evidence that confirms both suspected infection and positive-dose
  administration.

## Further owner clarification on the two pathways

### Pathway 1

The owner confirmed that the qualifying Sepsis 2 organ-dysfunction episode
must still be active; a final encounter-level Sepsis 2 flag alone is not
sufficient. The owner further restricted the pathway so that Sepsis 2 onset,
hypotension, and lactate `>2` must be associated with the same suspected-
infection anchor and its inclusive plus/minus 48-hour window.

The primary Pathway 1 onset follows the project-wide retrospective rule and is
the earliest contributing timestamp:

`min(infect_dt, sepsis_2_onset, lactate_positive_onset, hypotension_onset)`.

The owner's response wrote "lactate `<2` onset" in the timestamp expression,
while the criterion was stated as lactate `>2`. The owner confirmed this was a
typo: the required criterion and timestamp are lactate **`>2`** and its positive
onset.

One temporal detail also remains unresolved: whether Sepsis 2, effective
hypotension, and valid lactate `>2` must have a common positive-time overlap,
or whether it is sufficient for each onset/evidence event to occur somewhere
inside the same inclusive plus/minus 48-hour infection window.

The distinction was explained to the owner as follows:

- **Occurrence-only within the window:** each component may occur at a
  different, non-overlapping time anywhere from 48 hours before through 48
  hours after the infection anchor. This can combine evidence separated by
  nearly 96 hours.
- **Common positive overlap:** there must be at least one instant inside the
  infection window when the qualifying Sepsis 2 organ episode remains active,
  effective hypotension is active, and valid lactate is greater than 2.

### Final temporal decision

The owner selected **occurrence-only within the window**. Simultaneous overlap
is not required. For Pathway 1, the qualifying Sepsis 2 onset, effective
hypotension evidence, and valid lactate `>2` evidence must each occur within
the same suspected-infection anchor's inclusive plus/minus 48-hour window, but
their positive intervals may be non-overlapping.

Pathway 1 retrospective onset remains:

`min(infect_dt, sepsis_2_onset, lactate_gt2_onset, hypotension_onset)`.

The criterion-completion timestamp should separately represent when the last
required component has been established.

### Pathway 2

The owner confirmed that Pathway 2 is independently OR-composed with Pathway
1. Therefore, infection plus qualifying vasopressor administration can produce
Sepsis 3 even when Sepsis 2 is negative. The existing validation that every
Sepsis 3-positive encounter must be Sepsis 2-positive is incompatible with the
new approved composition and must be replaced when implementation is
authorized.

## Implementation completed

Implementation was subsequently authorized and completed on 2026-11-10:

- Removed vasopressors from the rolling Aggregator feature registry.
- Added event-level lactate-result evidence using the strict `>2` threshold.
- Linked vasopressor orders and positive-dose administrations by encounter,
  grouper, and `Event_ID`; an unlinked administration uses administration time
  as its retrospective anchor.
- Replaced the active Sepsis 3 composition with the two approved OR pathways.
- Added `sepsis_3_pathway` and `sepsis_3_criterion_met_dt` audit fields.
- Removed the Sepsis 3-subset-of-Sepsis 2 validation from active run scripts.
- Updated both `main_strategy.py` and `main_strategy_phase4.py`.

Validation results:

- 82 focused tests passed.
- The full maintained `tests/` directory produced 291 passes and 7 unrelated
  failures already associated with dataloader fixtures, SIRS-filter defaults,
  and in-progress suspected-infection changes.
- Repository-root pytest collection also remains blocked by the legacy
  `main_test.py` import of removed `input_output_config`.
