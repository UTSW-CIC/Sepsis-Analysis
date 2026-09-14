# P/F Ratio Redesign Decisions (2026-09-12)

## Scope and Authorization

The project owner approved redesigning P/F derivation before pulmonary
dysfunction is implemented. This work is limited to stabilizing PaO2 and FiO2,
building auditable P/F evidence after collision resolution, and removing the
incorrect rolling P/F aggregate. It does not implement pulmonary start/end
state logic.

## Approved Decisions

1. Same-instant PaO2 collisions use the existing minimum-value strategy.
2. Same-instant FiO2 collisions use the maximum-value strategy, producing the
   lowest and therefore conservative P/F ratio.
3. Each PaO2 is paired with the nearest valid FiO2 within two hours.
4. The two-hour boundary is inclusive.
5. If FiO2 candidates are equally close, prefer the earlier FiO2 because it
   was available when PaO2 was measured.
6. FiO2 values greater than zero through one are fractions; values greater
   than one are percentages and are divided by 100.
7. FiO2 equal to zero is invalid and cannot produce a P/F ratio.
8. A derived P/F ratio becomes available at the later of its PaO2 and FiO2
   timestamps.
9. These decisions must be documented with inline comments immediately above
   their implementations.

## Design Decision

P/F derivation moves out of ingestion. The intended order is:

`DataLoader -> ResolveCollision -> PFRatioBuilder`

The builder returns a separate evidence table with no more than one result per
PaO2 and retains both source measurements and timestamps. The two-hour window
is a pairing constraint, not a clinical validity duration.

## Validation Contract

Each increment will include a focused command the project owner can run. Tests
must cover collision configuration, deterministic pairing, exact boundaries,
FiO2 normalization, invalid values, evidence availability time, input
preservation, and prevention of row multiplication.

## Implementation Completed

- Added the approved maximum-FiO2 rule to the same-instant collision registry;
  the existing minimum-PaO2 rule remains unchanged.
- Added `PFRatioBuilder` in `src_strategy/data_preparation/pfratio.py`.
- The builder requires collision-free source measurements and returns exactly
  one evidence row per PaO2 measurement.
- Each evidence row retains PaO2 and FiO2 values and timestamps, normalized
  FiO2, the derived ratio, its availability timestamp, and a pairing status.
- Ratios that cannot be calculated remain present with either
  `invalid_pao2` or `no_valid_fio2_within_window` status.
- Removed P/F calculation from both ingestion loaders. They now return only
  normalized source events.
- Removed the obsolete ingestion transformer and utility implementation after
  the post-collision builder passed its focused tests.
- Removed `LAST_PFRATIO_2H` from the rolling feature registry because two hours
  is a measurement-pairing window rather than an approved validity duration.
- Updated the V1/V2 loader parity test to confirm that P/F is built explicitly
  after ingestion.

## Validation Results

- P/F builder and collision-order tests: 13 passed.
- Loader parity tests: 2 passed.
- Combined focused suite: 15 passed.
- Maintained project suite: 133 passed and 3 previously documented expectation
  mismatches deselected.
- Python compilation and focused whitespace/line-length checks passed.
- Aggregate-only smoke testing used 397,328 source PaO2/FiO2 rows. Collision
  resolution produced 94,335 PaO2 measurements, and the builder produced
  exactly 94,335 evidence rows: 85,891 paired and 8,444 without a valid FiO2
  in the approved window. No infinite ratios were produced, and no
  patient-level output was printed or saved.

## Next Step

Pulmonary dysfunction can now consume the separate P/F evidence table using
`pf_ratio` and `pf_ratio_time`. P/F below or above 200 has deliberately not
been interpreted here; those are pulmonary start/termination clinical rules.
