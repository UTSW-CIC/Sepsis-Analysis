# Phase 4 non-pulmonary organ source and provenance decisions

## Approved decisions

The project owner approved the following changes for cardiovascular, renal,
hepatic, coagulation, and neurological evidence:

- Restrict lactate, creatinine, eGFR, bilirubin, platelets, INR, and aPTT
  aggregation to `Type="Lab Results"`.
- Restrict Glasgow Coma Score aggregation to `Type="Flowsheet"`.
- Preserve the source provenance for the measurement selected by each rolling
  feature. Because `Event_ID` can identify multiple components, provenance
  must not consist of `Event_ID` alone; it should retain the selected source
  timestamp, `Type`, `Event_ID`, and `Event_Name` together.
- Leave the aPTT feature and criterion configured even though the reviewed
  Phase 4 extract contains no aPTT events. Its all-null evidence is handled as
  unavailable and does not crash or positively satisfy coagulation
  dysfunction.
- Keep the laboratory result time as the clinical organ-evidence time. A
  linked order time must not replace or backdate the abnormal result time.

## Implementation-scope clarification

Question: Should source provenance stop at the wide organ-dysfunction table,
or must it also be propagated into organ-dysfunction segments, episodes, and
the downstream Sepsis 2/3 evidence outputs?

Owner answer: Propagate it through the organ episode and Sepsis 2/3 evidence
outputs.

## Implementation completed

- Added the approved explicit source `Type` to all eight non-pulmonary organ
  feature definitions.
- The approved organ numeric rolling features now retain aligned source
  timestamp, `Type`, `Event_ID`, and `Event_Name` columns for the source row
  selected by the aggregation rule. Provenance retention is explicitly enabled
  per feature so unrelated rolling features do not acquire unnecessary wide
  string columns in this increment.
- Exact organ segments carry the valid measurement value and provenance until
  the configured evidence expiration, then clear both together.
- Organ episodes retain per-feature lists of aligned evidence records. Each
  record contains value, result timestamp, source type, event ID, and event
  name. The list representation preserves multiple source measurements without
  breaking field alignment.
- Pulmonary transition provenance is represented similarly in organ episodes.
- Encounter baseline values used by renal, hepatic, and coagulation criteria
  are retained in the organ episode and Sepsis association evidence.
- Sepsis 2 association rows retain all organ source-evidence columns. Sepsis 3
  continues to carry every Sepsis 2 evidence column, so the provenance is
  preserved without changing Sepsis 3 classification logic.
- Result timestamps remain the clinical evidence times. No procedure-order
  timestamp is substituted.

## Validation

- Focused aggregation, organ, Sepsis 2, and Sepsis 3 tests: 27 passed.
- Broader focused implementation selection: 68 passed.
- Maintained `tests/` suite: 288 passed and the same six unrelated failures
  remained (stale DataLoader-v2 filename expectation, stale SIRS default, and
  four older suspected-infection fixtures without `Event_ID`).
- Read-only Phase 4 smoke validation on 20 encounters produced 17,866
  aggregate rows, 5,158 organ segments, 208 organ episodes, and 232 Sepsis 2
  evidence associations without changing row cardinality at aggregation.
- Every populated organ feature had zero missing source timestamp/type/name
  provenance in the smoke validation.
- aPTT remained entirely unavailable, produced an empty evidence list, and did
  not crash aggregation, organ-state reconstruction, or Sepsis 2 association.
- Every organ episode source-evidence column was present in the resulting
  Sepsis 2 association table.

The existing saved Phase 4 aggregate parquet predates these new provenance
columns. It must be regenerated through the aggregation step before the active
composition script can consume the new organ provenance contract. No saved
patient-level artifacts were overwritten during this implementation or smoke
validation.
