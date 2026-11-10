# Phase 4 session handoff — 2026-11-09

## Session outcome

Phase 4 ingestion, collision handling, suspected-infection evidence, pulmonary
dysfunction, vasopressor aggregation, and non-pulmonary organ provenance were
reviewed and incrementally updated for the new source model containing
`Event_ID`, medication orders, and additional transactional tables.

No further implementation is authorized by this handoff. The next session
should begin with review and clarification before changing clinical logic.

## Decisions and implementation completed

- `Type` remains the source discriminator. `Event_ID` is provenance/linkage;
  it is not a generic uniqueness, P/F-pairing, or state-machine key.
- Systolic/diastolic blood pressure and measured MAP remain separate source
  events and are resolved independently.
- Suspected-infection antibiotic evidence requires an administration, uses its
  linked medication-order time as the infection anchor when available, and
  retains administration time separately.
- Culture and lactate result confirmation remain linked to their procedure
  orders without replacing abnormal-result evidence time in downstream organ
  dysfunction.
- Pulmonary dysfunction uses the approved Phase 4 Vent On/Off roles, scoped
  null termination, high-flow/non-rebreather termination, and P/F `<200` as
  start-only evidence.
- Pulmonary transition provenance retains source `Event_ID` values. P/F
  evidence retains separate PaO2 and FiO2 IDs.
- Positive vasopressor administrations are carried forward according to the
  configured validity period; medication administration remains confirmation.
- Cardiovascular, renal, hepatic, coagulation, and neurological aggregation is
  explicitly restricted to the approved source `Type`.
- Organ feature provenance now retains result timestamp, `Type`, `Event_ID`,
  `Event_Name`, and value through aggregation, organ segments, organ episodes,
  and Sepsis 2/3 association evidence.
- Laboratory result time remains the clinical organ-evidence time. Order time
  does not backdate an abnormal organ result.
- aPTT remains configured but is absent from the reviewed Phase 4 extract. Its
  evidence remains unavailable/null and does not crash or positively satisfy
  coagulation dysfunction.

## Validation state

- Maintained `tests/` suite: **288 passed, 6 failed**.
- The six failures predate the final pulmonary/organ work:
  - one stale DataLoader-v2 filename expectation;
  - one stale SIRS enabled-default expectation;
  - four older suspected-infection fixtures that omit required `Event_ID`.
- Read-only Phase 4 subset smoke validation confirmed that populated organ
  features retain aligned provenance, aPTT remains safe when absent, and all
  organ evidence columns reach Sepsis 2 associations.
- No patient-level artifacts were overwritten during the final validations.

## Required artifact refresh

The existing saved `df_aggregated_map_measured_only.parquet` predates the new
organ source-provenance columns. Regenerate it through the aggregation step
before running the downstream organ and Sepsis composition path from saved
artifacts.

## Next-session priorities

### 1. Review hypotension episodes

- Review BP state reconstruction, duration filtering, unknown/missing-state
  handling, and exact eight-hour expiration boundaries.
- Confirm how SBP `<90`, SBP decline `>40`, and MAP `<65` combine into effective
  hypotension episodes.
- Verify Phase 4 measured-MAP and systolic provenance survives into shock
  evidence without combining unrelated `Event_ID` values.
- Review whether the currently configured BP episode filter is enabled and
  whether its retained episodes are the intended Sepsis 3 input.
- Use aggregate-only diagnostics and focused boundary tests; do not expose
  patient identifiers.

### 2. Modify Sepsis 3 according to Clinical Definition 4

- Before implementation, confirm the exact authoritative document. The
  workspace currently contains `docs/clinical_definitions 4
  (AutoRecovered).docx`; do not assume an AutoRecovered copy is the approved
  source without owner confirmation.
- Re-open the confirmed document and compare every Sepsis 3/septic-shock rule,
  threshold, validity period, medication condition, temporal association, and
  exclusion against current configuration, adapters, and tests.
- Reconcile the project decision that classification timing uses earliest
  evidence with any differing current `max(...)` timestamp implementation.
- Preserve distinct infection, organ, shock, order, administration, and result
  timestamps rather than overwriting evidence semantics.
- Implement only owner-approved differences and add regression tests for every
  changed clinical boundary.

### 3. Review SIRS logic against the Phase 4 dataset

- Confirm Phase 4 source types, groupers, names, units, and non-null coverage
  for temperature, pulse, respiratory rate, and WBC.
- Verify same-instant collision behavior and the most-recent 8-hour/12-hour
  validity rules.
- Review missing/expired evidence behavior, exact threshold equality, score
  composition, and episode construction.
- Resolve the stale test disagreement about whether SIRS episode filtering is
  enabled by default.
- Confirm whether additional `Event_ID` provenance should be propagated into
  SIRS episodes and Sepsis 1 association evidence, following the organ-evidence
  pattern implemented this session.

## Session-start instruction

At the start of the next session, read this handoff together with:

- `AI_logs/2026-11-09-earliest-evidence-timing.md`
- `AI_logs/2026-11-09-phase4-pulmonary-transition-design.md`
- `AI_logs/2026-11-09-phase4-organ-provenance.md`
- `AI_logs/2026-09-14-septic-shock.md`
- `AI_logs/2026-09-14-sepsis-3-plan.md`

Then confirm the authoritative Clinical Definition 4 file before editing any
Sepsis 3 clinical logic.
