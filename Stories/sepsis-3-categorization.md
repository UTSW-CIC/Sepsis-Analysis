Title: Categorize Sepsis 3 from overlapping Sepsis 2 and septic-shock evidence

Description: As a clinical billing reviewer, I want Sepsis 3 calculated from Sepsis 2 plus temporally overlapping septic shock, so that the highest severity state has reviewable infection, organ, and shock provenance.

Acceptance criteria:
- Sepsis 3 starts only from qualifying Sepsis 2 evidence, so suspected infection remains required and SIRS remains unnecessary.
- Interval-based shock evidence must overlap both the positive organ episode and the same infection anchor's configured 48-hour window with positive duration.
- A qualifying vasopressor administration is point evidence inside both half-open intervals and is never carried forward.
- BP and lactate interval evidence end at their configured validity or effective-state boundary.
- `sepsis_3_dt` is the latest of infection time, organ episode start, and shock evidence start.
- `sepsis_3_earliest_evidence_dt` is the earliest of those three timestamps.
- Association evidence distinguishes interval shock from vasopressor-point shock and preserves component provenance.
- Encounter output retains negative encounters and counts associations, anchors, organ episodes, and shock evidence.

Story hours: 19

title: Build exact septic-shock interval segments and episodes

Description: Reconstruct numeric and optionally filtered BP/lactate shock intervals at measurement, expiration, and effective-state change points while retaining component flags.

working hours: 5

Priority: 1

title: Build exact vasopressor shock points

Description: Group qualifying positive administrations at their exact encounter timestamp and retain medication groupers and dose counts.

working hours: 2

Priority: 1

title: Associate Sepsis 2 evidence with shock evidence

Description: Enforce approved organ and infection-window overlap rules for interval and point evidence and calculate classification timestamps.

working hours: 4

Priority: 1

title: Build Sepsis 3 encounter summaries

Description: Reduce association evidence to one classification row per encounter while preserving negative encounters and distinct evidence counts.

working hours: 2

Priority: 1

title: Integrate Sepsis 3 into main_strategy.py

Description: Add interval, point, association, and encounter outputs to the active versioned no-overwrite composition.

working hours: 2

Priority: 1

title: Test boundaries, repair adapter defect, and document results

Description: Validate half-open boundaries and timestamp ordering, add multi-feature source-timestamp regression coverage, run aggregate-only smoke checks, and record approved decisions.

working hours: 4

Priority: 2
