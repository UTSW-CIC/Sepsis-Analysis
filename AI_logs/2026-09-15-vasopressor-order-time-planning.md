# Vasopressor order-time planning — 2026-09-15

## Requested rule change

Question: Which source and identifier link a qualifying vasopressor
administration to its order so that order time can be used as the septic-shock
evidence timestamp?

Owner answer: A linking identifier is not currently available. The owner is
considering linking each qualifying administration to the chronologically
closest vasopressor order.

The administration remains the evidence that qualifies the vasopressor shock
pathway; the proposed matched order time, rather than administration time,
would become the shock evidence timestamp.

## Current technical findings

- The active medication-administration extract contains the four configured
  vasopressor groupers only as `Medication Administration` events.
- The active procedure-order extract contains no events for those vasopressor
  groupers.
- Both active extracts expose the common event columns but no medication-order
  identifier or separate medication-order timestamp.
- A medication-order source still needs to be identified and added to the
  ingestion contract before matching can be implemented.

## Proposed matching rule for review

Use the most recent prior order for the same encounter and normalized
vasopressor grouper, rather than the smallest absolute time difference. This
prevents a later renewal order or an order for a different vasopressor from
being treated as the cause of an earlier administration.

Before approving the rule, summarize order-to-administration lags, unmatched
administrations, repeated orders, and same-time ties without displaying
patient-level data. Use those results to decide whether a maximum allowed lag
is required.

## Decisions still required

1. Identify the medication-order file and its order-time, medication-name,
   encounter, event-status, and available provenance columns.
2. Confirm latest-prior same-vasopressor matching instead of absolute-nearest
   matching.
3. Decide whether to impose a maximum order-to-administration interval.
4. Decide whether an unmatched positive administration is retained only for
   audit or falls back to administration time.
5. Confirm that the matched order time must satisfy the Sepsis 3 organ-episode
   and infection-window boundaries, even if administration occurs inside the
   boundaries but its order does not.

No clinical code or tests were changed during this planning step.
