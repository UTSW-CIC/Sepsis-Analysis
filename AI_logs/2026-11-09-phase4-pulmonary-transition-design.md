# Phase 4 pulmonary transition decisions and design

## Scope and implementation status

The project owner approved the Phase 4 interpretation of the new
`Vent On/Off` values and requested a design for updating pulmonary dysfunction.
The owner subsequently authorized implementation by saying `Proceed`. The
approved implementation and validation results are recorded below.

## Approved `Vent On/Off` interpretation

### Positive start/on evidence

- `Initial`
- `$ On Going Hospital Vent`
- `On Going Hospital Vent`
- `Place back on Ventilator (Trachs)`
- `Place on BiPAP (Trachs)`

### Termination/off evidence

- `Standby`
- `Discontinue Vent (Trachs Only)`
- `Place on Trach Collar`
- `Place on High Flow (Trachs)`
- null `Value` on a `Vent On/Off` event

The null rule is scoped narrowly to rows whose grouper is `Vent On/Off`. It is
not a general rule that missing values terminate clinical states.

### Continuation-only evidence

- `Extubation not ordered`
- `Do not Extubate Patient`
- `Do not Extubate Patient, Resume Ordered Settings`

These values do not create a transition. They retain an already established
state. In the state machine, ignoring them as change points naturally preserves
the prior state; they should remain identifiable for audit.

### Neutral or ambiguous evidence

- `Extubation ordered`
- `Other (Comment)`

An extubation order records intent, not completed tube removal, so it does not
terminate pulmonary dysfunction. Neither value changes the reconstructed
state.

### Encounter exclusion

- `$ Home Vent Used`

This remains an encounter-wide pulmonary exclusion rather than a start or
termination transition.

## Pre-implementation gaps that motivated the change

1. `VentOnOffConfig.termination_values` contained only
   `$ Extubation`, a value not present in the reviewed Phase 4 collision-free
   data.
2. `Standby` was present in Phase 4 but was not configured as a
   termination value.
3. Null `Vent On/Off` values were configured not to terminate.
4. The newly observed `Vent On/Off` values need explicit source-role mappings
   so that unrecognized values do not silently change state.

## Owner clarification: no pulmonary tier output

The clinical-definition document organizes its respiratory evidence into
tiers, but the algorithm does not calculate, retain, or classify pulmonary
dysfunction tiers. Only the document's Tier 1 and Tier 2 evidence can begin the
single binary pulmonary-dysfunction state.

Consequences:

- the existing P/F start threshold of `<200` remains correct because the union
  of the accepted `<100` and `<200` evidence is `<200`;
- no `<100`, `<200`, or `<300` severity label should be added;
- P/F values from `200` through `300` do not begin pulmonary dysfunction;
- high-flow and non-rebreather evidence do not belong in the positive/start
  set; and
- the earlier provisional classification of `Place on High Flow (Trachs)` as
  start evidence is superseded by this clarification.

## Proposed minimal design

### 1. Keep source interpretation in configuration

Extend the pulmonary configuration so each raw value has one explicit role:

- `start_values`
- `termination_values`
- `continuation_values`
- `neutral_values`
- the existing encounter-exclusion value

Set `null_value_terminates=True`, while continuing to apply that setting only
inside the `Vent On/Off` grouper condition.

Configuration validation should reject overlap between these role lists. This
prevents a value from silently becoming both start and termination evidence.

### 2. Update O2-support mappings without changing state architecture

Keep the existing Strategy/Registry and reconstructed-state workflow. Change
only the source classification:

- mechanical ventilation and BiPAP/CPAP/NPPV remain positive pulmonary
  evidence;
- nasal cannula, simple face mask, and room air remain termination evidence;
- high-flow and non-rebreather support remain termination evidence and are
  excluded from positive evidence;
- `Vent off Documentation` remains termination evidence.

Do not add a separate procedural state machine. The existing termination-wins
same-instant rule and backward state propagation remain appropriate.

### 3. Preserve non-transition evidence for audit

Continuation and neutral values must not enter the start/termination reducer.
Retain their source rows in a small classified raw-evidence table or classified
evidence columns so reviewers can distinguish "ignored by design" from an
unrecognized source value. The state timeline itself should still contain only
encounter bounds and genuine state transitions.

### 4. Make unknown values observable

Add monitoring that compares observed `Vent On/Off` values with every
configured role. Any new unmapped non-null value should be reported as an
unclassified value and must not change state automatically.

### 5. Preserve `Event_ID` as provenance, not as a state key

Pulmonary state remains keyed by encounter and timestamp. `Event_ID` should not
be added to state grouping keys. Where available, retain the source `Event_ID`
on classified transition evidence so the triggering EHR event remains
traceable.

For P/F evidence, retain separate PaO2 and FiO2 source `Event_ID` fields. Do
not require the two measurements to share an `Event_ID`; the approved pairing
rule remains nearest valid FiO2 within the inclusive two-hour window.

### 6. Keep lab availability separate from a future billing anchor

P/F and other abnormal lab values should become physiologically available at
their result/evidence timestamp. If the owner later approves an earlier linked
order timestamp for retrospective billing, retain it as a separate audit/anchor
field rather than moving the abnormal value backward in the state timeline.

## Proposed incremental implementation order

1. Add configuration role lists and overlap validation.
2. Add parameterized tests for every approved `Vent On/Off` value.
3. Update raw start/termination criteria and add unclassified-value monitoring.
4. Preserve high-flow and non-rebreather as termination evidence and add
   focused state tests.
5. Preserve the single `<200` P/F start threshold and add exact boundary tests
   proving that `200` and higher do not start pulmonary dysfunction.
6. Add `Event_ID` provenance to raw transition and P/F evidence without
   changing pairing or state keys.
7. Run a Phase 4 aggregate-only validation of transition counts, exclusions,
   unknown values, P/F pairing cardinality, and pulmonary-state intervals.
8. Re-run pulmonary-to-organ integration tests to prove that the organ layer
   consumes the corrected nullable pulmonary state without reinterpretation.

## Required regression cases

- every approved raw value maps to exactly one role;
- `Standby`, scoped null, trach-collar placement, and ventilator discontinuation
  terminate an active state;
- `Extubation ordered` does not terminate;
- continuation values preserve on, off, and unknown prior states;
- `$ Home Vent Used` forces the encounter-wide exclusion behavior;
- high-flow and non-rebreather support generate termination, not start, events;
- simultaneous start and termination still resolves to termination;
- state remains null before the first genuine transition unless excluded;
- no raw event, aggregate row, or organ-dysfunction row is multiplied;
- source timestamps and source `Event_ID` values remain auditable.

## Final source-role clarification

The owner confirmed that the existing high-flow and non-rebreather termination
logic must remain. These events do not begin pulmonary dysfunction and actively
terminate an existing pulmonary-dysfunction state. Therefore,
`Place on High Flow (Trachs)` is also termination evidence rather than neutral
or positive evidence.

The reviewed Phase 4 data additionally contains
`Do not Extubate Patient, Resume Ordered Settings`, which was not present in
the owner's initial value list. The owner classified it as continuation-only
evidence because it does not document extubation. It does not create a start or
termination transition and preserves the previously established state.

All clinical/source-role questions required for the Phase 4 pulmonary update
were resolved before implementation.

## Implementation completed

- Added explicit start, termination, continuation, and neutral `Vent On/Off`
  value lists, overlap validation, and the approved scoped-null termination.
- Restricted raw pulmonary transitions to flowsheet events so similarly named
  groupers from another source type cannot change state.
- Kept the P/F rule start-only at `<200`; `>=200` does not terminate pulmonary
  dysfunction.
- Restricted PaO2 and FiO2 source rows to `Lab Results` while retaining the
  nearest-FiO2-within-two-hours pairing rule.
- Preserved separate PaO2 and FiO2 `Event_ID` values and propagated raw/PF
  source IDs to pulmonary transition evidence without using them as state or
  pairing keys.
- Added privacy-safe monitoring for unclassified non-null `Vent On/Off`
  values. Monitoring logs the count only, not raw EHR values.
- Attached pulmonary transition source IDs to the aggregate table alongside
  the existing transition timestamp and transition type.
- Added focused regression tests for every approved role, null termination,
  continuation behavior, P/F boundaries and source filtering, provenance,
  timeline cardinality, attachment, and organ-dysfunction integration.

Continuation and neutral rows remain present in the original event table for
audit but do not become state-transition rows. New unclassified values remain
state-neutral and produce a warning count.

## Validation completed

- Focused P/F, pulmonary, attachment, termination, configuration, and organ
  integration suite: **85 passed**.
- Read-only Phase 4 aggregate smoke validation:
  - 95,829 P/F rows and 95,829 unique PaO2 source keys;
  - zero null PaO2 `Event_ID` values;
  - zero unclassified `Vent On/Off` values;
  - 927,599 pulmonary timeline rows;
  - zero duplicate encounter/timeline-time keys.
- The maintained `tests/` suite reached **285 passed, 6 failed**. All six
  failures are outside this pulmonary change: one stale DataLoader-v2 filename
  expectation, one SIRS-default expectation, and four older suspected-
  infection fixtures that do not supply the now-required `Event_ID`.
- Source modules compile cleanly and `git diff --check` reports no whitespace
  errors.

The smoke validation was aggregate-only and did not print or write patient-
level records.
