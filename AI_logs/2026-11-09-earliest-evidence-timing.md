# Earliest-evidence timing decision

## Owner decision

The project is a retrospective billing-review analysis. Its primary Sepsis
1/2/3 timestamp is the earliest contributing evidence timestamp, not the time
when every component criterion has occurred.

For a qualifying composed episode:

- `sepsis_n_dt` should represent the minimum timestamp among its contributing
  evidence;
- a separate criteria-completion timestamp may be retained for audit and
  sensitivity analysis, but it is not the primary project onset;
- the algorithm does not infer a physiological ordering of infection, organ
  dysfunction, and shock from their recorded order.

For linked vasopressor evidence:

- a positive-dose medication administration remains required for the
  vasopressor pathway to qualify;
- an order without a positive administration does not qualify;
- the planned vasopressor shock anchor is
  `min(order_dt, first_positive_admin_dt)`;
- retain order and administration timestamps separately for audit.

## Known implementation gap

The existing Sepsis 1/2/3 association code currently calculates the primary
`sepsis_n_dt` with `max(...)`, while separately calculating an
earliest-evidence field with `min(...)`. This does not match the newly confirmed
project-wide primary-timestamp rule and must be addressed in a later,
explicitly authorized step.

No Sepsis association, septic-shock, or Aggregator code was changed when this
decision was recorded. The owner requested that the pipeline continue to be
reviewed and modified incrementally; the current review stage is Aggregator.

## Aggregator boundary for the current review

- Do not add `Event_ID` to the backbone or rolling-aggregation grouping keys.
- Preserve `Event_ID` in the collision-free event table for criterion-specific
  order/result or order/administration linkage before evidence reduction.
- Vasopressor order/administration linkage belongs in the septic-shock evidence
  stage, not in the generic rolling Aggregator.
- The four existing rolling vasopressor registry features require a separate
  decision because their grouper-only filtering currently includes medication
  orders and non-positive administrations. They are not the approved mechanism
  for the planned order-linked vasopressor shock evidence.

## Owner clarification: rolling vasopressor state

The owner approved using the carried-forward vasopressor flag as a qualifying
Sepsis 3 shock pathway when suspected infection and organ dysfunction also
qualify. The rolling state and the earliest linked vasopressor evidence time
are two properties of the same evidence, not separate clinical uses.

Intended future behavior:

- group linked vasopressor records by encounter, vasopressor grouper, and
  `Event_ID`;
- require at least one positive-dose medication administration in the linked
  group;
- an order without a positive administration does not qualify;
- define the retrospectively confirmed vasopressor anchor as
  `min(order_dt, first_positive_admin_dt)`;
- create/carry the qualifying vasopressor state from that anchor under the
  configured rolling window;
- retain `order_dt`, `admin_dt`, `Event_ID`, and the anchor source for audit;
- when the rolling state contributes to a qualifying Sepsis 3 episode, retain
  the vasopressor anchor as its shock evidence timestamp;
- the primary Sepsis 3 timestamp remains the earliest contributing evidence
  across suspected infection, organ dysfunction, and shock.

This clarification supersedes the prior exact-time-only vasopressor point
interpretation for the planned Phase 4 behavior. Implementation remains
deferred until the owner reaches the relevant incremental pipeline step.

## Aggregator implementation completed

The owner authorized the first incremental Aggregator change. The four
24-hour vasopressor features now restrict their source events to:

- `Type == "Medication Administration"`; and
- a non-null `NumericValue > 0`.

Medication orders, null doses, zero doses, and positive values from other
source types no longer activate these rolling flags. The flag is carried
forward from the positive administration timestamp under the existing
inclusive 24-hour window.

This step does not yet link orders and administrations by `Event_ID`, move the
rolling-state anchor to the earlier linked order, or revise Sepsis 3 timing.
Those changes remain deferred to their separately authorized pipeline stages.
