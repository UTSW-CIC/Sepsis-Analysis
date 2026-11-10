# Shared suspected-infection culture configuration

## Owner decision

- Use the six title-cased Phase 4 culture groupers previously defined under
  `AntibioticBloodCultureConfig` as one shared definition.
- Both the antibiotic+culture and lactate+culture criteria must consume that
  same definition so their configured groupers cannot diverge.

## Implementation status

- Moved the shared values to `SuspectedInfectionConfig.blood_culture_groupers`.
- Removed the duplicated grouper fields from the two criterion-specific
  configuration models.
- Updated both criteria to read the shared field.
- Added a focused behavioral test proving that a custom shared culture grouper
  is recognized by both paired criteria.

## Still unresolved

- This refactor only centralizes the current data-family labels. It does not
  decide whether result rows or non-blood body-fluid cultures should directly
  qualify clinically. Order-time versus result-time semantics and distinct
  `Event_ID` counting still require the planned criterion update.

## Owner-approved culture-time direction

The owner approved separating the blood-culture order from its later result:

- the procedure-order timestamp should supply `culture_dt`;
- culture results must not determine whether the suspected-infection criterion
  qualifies;
- later result evidence should be retained separately for audit and possible
  microbiology-positive subclassification;
- negative results must not erase the earlier clinical suspicion.

No criterion code has yet been changed for this decision because the result
classification mapping below requires clarification.

## Culture-result classification question

Aggregate Phase 4 inspection found that a simple `Value == "NEGATIVE"` rule is
not a culture-result rule:

- exact `NEGATIVE` values occur predominantly on urinalysis components such as
  `NITRITE UA`, `GLUCOSE UA`, and `LEUKOCYTE ESTERASE UA`;
- true negative culture values commonly contain phrases such as `NO GROWTH AT
  5 DAYS` or `NO ... ISOLATED`;
- positive evidence appears across `CULTURE`, `GRAM ST`, and organism-ID
  components;
- all 140,400 culture Event_ID groups with a lab result also have a linked
  procedure order in the current Phase 4 artifact; 163 order Event_ID groups
  have no result yet.

Owner clarification required: should the first implementation only link and
retain the raw result evidence without assigning positive/negative status, or
should it introduce an explicitly approved Event_Name/Value mapping for
`positive`, `negative`, `indeterminate`, and (if possible) `contaminant`?

### Owner answer and implementation

The owner approved an Event_ID-level, audit-only status mapping that does not
affect criterion qualification or `culture_dt`:

- `positive`: explicit `POSITIVE` or organism `DETECTED` evidence on a
  culture/microbiology component (`CULTURE`, `GRAM ST`, `BCID`, gene/PCR, or
  smear); unrelated UA components do not qualify;
- `negative`: a `CULTURE` component explicitly reports `NEGATIVE`, `NO GROWTH`,
  or `NO ... ISOLATED`, provided no higher-priority evidence exists;
- `contaminant`: contamination is explicitly documented;
- `indeterminate`: a result exists but does not meet an approved mapping;
- `pending`: the procedure order has no linked result.

Implemented behavior:

- Only `Procedure Order` rows can qualify as culture orders.
- The earliest procedure-order timestamp per encounter/Event_ID supplies
  `culture_dt`.
- `Lab Results` rows with the same encounter/Event_ID supply
  `culture_result_dt` and `culture_result_status` audit metadata.
- Result-only Event_ID groups cannot qualify.
- Multiple result components under one Event_ID count as one culture order for
  the lactate-plus-two-cultures criterion.
- Negative, indeterminate, contaminant, and pending results do not remove a
  qualifying order.
- The existing behavior that retains all qualifying antibiotic/culture pairs
  remains unchanged.

Validation:

- 23 focused suspected-infection and downstream Sepsis 1/2 tests passed.
- The Phase 4 parquet completed end to end through suspected-infection
  detection using the new schema and status mapping.
- Four legacy tests in `tests/test_suspected_infection_strategy.py` remain
  stale because their fixtures omit Phase 4 `Event_ID` and still model the old
  antibiotic/type contract; one also asserts the old four-column output.

## Owner decision: lactate order time

The owner approved applying the same order/result separation to lactate, with
the distinction that a result is optional and never acts as confirmation.

Implemented behavior:

- Lactate orders are `Procedure Order` rows with `Event_Grouper == "Lab"` and
  one of the three configured Phase 4 lactate Event_Name values.
- The earliest procedure-order timestamp per encounter/Event_ID supplies
  `lactate_dt` and controls the six-hour culture-proximity window.
- A linked `Lab Results`/`Lactate` row supplies audit-only
  `lactate_result_dt` and `lactate_result_value`.
- An order without a result remains eligible; a result without a linked order
  cannot qualify.
- The two-culture requirement counts distinct culture-order keys, not result
  component rows or repeated matches.

Phase 4 aggregate inspection supporting the decision:

- 90,845 lactate result Event_ID groups had linked procedure orders;
- 318 lactate procedure orders had no linked result;
- one lactate result Event_ID had no linked order;
- 7,890 linked results were timestamped before their recorded procedure order,
  making result time an unsafe proxy for order time.

Validation after implementation:

- 24 focused suspected-infection and downstream Sepsis 1/2 tests passed.
- Full Phase 4 suspected-infection detection completed successfully.
- Among 33,680 qualifying lactate-order evidence rows, 171 had no result and
  remained eligible as intended.

## Pending decision: canonical infection-episode grain

The owner approved replacing separate component anchors with one canonical
`infect_dt` per logical suspected-infection episode. All evidence rows in that
episode should share the earliest required evidence timestamp, while retaining
their own component timestamp separately. A distinct `criterion_met_dt` should
record when all required components were established.

Implementation is pending one episode-grain decision for encounters with many
matching events. Recommended minimal grain:

- one IV+culture episode per qualifying antibiotic Event_ID, with every culture
  order in its 72-hour-before/24-hour-after administration window retained as
  supporting evidence;
- one lactate+culture episode per qualifying lactate-order Event_ID, with every
  culture order in its six-hour window retained after confirming at least two
  distinct culture-order Event_ID values.

The alternative—one episode for every antibiotic/culture pair or every
lactate/two-culture combination—would preserve pairwise combinations but create
large combinatorial duplication.

### Owner answer — 2026-11-09

The owner approved the recommended episode grain:

- one IV+culture episode per qualifying antibiotic `Event_ID`, retaining every
  culture order in the administration-based timing window as evidence;
- one lactate+culture episode per qualifying lactate-order `Event_ID`, retaining
  every culture order in the six-hour window after the distinct-order count
  qualifies;
- a culture ordered before the antibiotic remains eligible when it is within
  the approved 72-hour-before-administration window;
- every long evidence row in an episode shares the same canonical `infect_dt`,
  which is the earliest required evidence timestamp;
- `evidence_dt` retains each component's own timestamp;
- `criterion_met_dt` records when every required component has occurred;
- downstream Sepsis 1/2/3 association must create one anchor per canonical
  infection episode rather than one anchor per evidence row.

For IV+culture, `criterion_met_dt` is the later of administration time and the
earliest qualifying culture-order time. For lactate+culture, it is the later of
the lactate-order time and the Nth distinct culture-order time, where N is the
configured minimum culture count (currently two).

### Implementation and validation

- Added `infection_episode_id`, `criterion_met_dt`, and `evidence_dt` to the
  suspected-infection long-frame contract.
- IV+culture now emits one antibiotic row per qualifying antibiotic episode and
  one row for every qualifying culture. All rows share the episode's earliest
  `infect_dt`.
- Lactate+culture emits one lactate row per qualifying lactate-order episode and
  one row for every culture in its six-hour window. All rows share the episode's
  earliest `infect_dt`.
- Direct Code Sepsis and flowsheet events each form a one-event episode, for
  which `infect_dt`, `criterion_met_dt`, and `evidence_dt` are identical.
- `build_infection_anchors()` now validates timestamp/type consistency within
  each episode and emits exactly one downstream anchor per episode.
- Added regression coverage for culture-before-antibiotic timing, inclusive
  window boundaries, multiple cultures supporting one antibiotic episode,
  lactate criterion-completion time, and inconsistent episode rejection.
- 73 focused suspected-infection, Sepsis 1/2/3, and run-configuration/versioning
  tests passed.
- Aggregate-only validation against the Phase 4 collision-free parquet produced
  155,554 episodes and exactly 155,554 downstream anchors, with no null required
  episode timestamps, no inconsistent episode timestamps/types, and exactly one
  source antibiotic/lactate row per applicable episode.

The four tests in `tests/test_suspected_infection_strategy.py` remain legacy
Phase 3 tests: their fixtures omit `Event_ID`, use the former Type-based
antibiotic model, and assert the former output/reduction contract. They are not
valid Phase 4 regressions and were not modified in this change.

## Owner decision: antibiotic order and administration times

The owner approved retaining a linked antibiotic administration as required
confirmation while using the linked medication order time as the downstream
suspected-infection anchor. The administration timestamp must also remain in
the output as `admin_dt`.

Implementation semantics:

- Link administration and order rows on encounter plus `Event_ID`.
- Use the earliest linked administration time for the clinically defined
  72-hours-before/24-hours-after culture-pairing window.
- Use the earliest linked medication order time as `infect_dt` for the `iv_dt`
  evidence row.
- Carry `admin_dt` on both evidence rows emitted by the qualifying pair.
- An unlinked medication order does not qualify without an administration.
- When a qualifying administration has no linked medication order, use the
  earliest timestamp in its encounter-scoped `Event_ID` group. If there is no
  earlier linked event—or the administration has a null `Event_ID`—use the
  administration timestamp itself.
- Carry `infect_dt_source` with one of `medication_order`,
  `event_id_first_event`, or `administration_fallback` so the fallback is
  auditable.
