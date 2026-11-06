# Phase 4 ingestion — Event ID contract (2026-11-03)

## Project-owner clarification

Question: What is the uniqueness and row-grain contract for `Event_ID` in the
new transactional extracts?

Answer: `Event_ID` is unique alongside encounter and source, but it is not a
row identifier. A medication or laboratory event may have multiple rows with
the same encounter, timestamp, and `Event_ID`; for example, one laboratory
event can produce multiple resulted components that all map to the same
`Event_ID`.

## Review consequence

- Do not deduplicate transactional data using only encounter, source, and
  `Event_ID`.
- Preserve component-level fields when defining row uniqueness.
- Preserve `Event_ID` through the unified event table for source-event
  provenance and source-specific joins.
- Any join using encounter/source/`Event_ID` must account for the one-event-to-
  multiple-component-row relationship and avoid unintended many-to-many row
  multiplication.

## Scope

This clarification was recorded during a read-only review of the Phase 4
`dataloader_2.py` modifications. No pipeline code was changed.

## Source discriminator clarification — 2026-11-05

Question: Does the transactional `Type` column reliably distinguish source
families in the Phase 4 dataset, so it can disambiguate source-scoped
`Event_ID` values during joins?

Answer: Yes. The project owner validated the current dataset and confirmed
that `Type` distinguishes the sources.

Review consequence: joins that use source-scoped `Event_ID` should also include
`Type` as a source discriminator. Component-level joins should retain
`Event_Name` (and any other fields required to establish right-side uniqueness).

## Branch and review scope clarification — 2026-11-05

Question: Must the Phase 4 `Event_ID` and new-table changes remain compatible
with the legacy ingestion implementation during the current review?

Answer: No. `Event_ID` and the new tables exist only in Phase 4, which is
defined only on the `StrategySepsisPhase4` Git branch. Reviews should focus on
the files requested by the project owner and their direct dependencies, and
should not treat legacy implementation compatibility as part of the current
scope.

## Blood-pressure join clarification — 2026-11-05

Question: Does the Phase 4 blood-pressure extraction join require
`Event_Name` to distinguish component rows?

Answer: No under the confirmed source contract. For blood-pressure flowsheet
rows, `Event_Grouper` explicitly identifies `Blood Pressure`, and the raw
`Value` contains the systolic/diastolic pair (for example, `120/80`). Together
with encounter, timestamp, and `Event_ID`, the current join key uniquely
identifies the blood-pressure row. `Event_Name` therefore adds no additional
protection against row multiplication for this join.

Review consequence: retain the current blood-pressure join fields, but enforce
or monitor the composite-key uniqueness assumption at the ingestion boundary
before production use. The project owner confirmed that current Phase 4 data
contains no null `Event_ID` values; future production extracts are not
guaranteed to preserve that invariant, so missing IDs require an explicit
validation/fallback policy before deployment.
