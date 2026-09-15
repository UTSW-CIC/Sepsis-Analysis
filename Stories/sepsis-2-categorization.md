Title: Categorize Sepsis 2 from infection anchors and organ-dysfunction episodes

Description: As a clinical billing reviewer, I want Sepsis 2 calculated from suspected infection and at least one organ dysfunction, so that severe sepsis evidence and timing remain auditable without requiring Sepsis 1.

Acceptance criteria:
- Sepsis 2 requires suspected infection and at least one positive organ-dysfunction episode; SIRS and Sepsis 1 are not prerequisites.
- Organ state change points include source measurements, configured feature expirations, and pulmonary transitions.
- Positive organ episodes use half-open intervals and must overlap the configured 48-hour backward/forward infection window with positive elapsed duration.
- `sepsis_2_dt` is the later of infection time and organ episode start.
- `sepsis_2_earliest_evidence_dt` is the earlier of infection time and organ episode start.
- Evidence identifies the contributing organ flags and maximum simultaneous organ count.
- Encounter output retains negative encounters and counts associations, anchors, and organ episodes.

Story hours: 17

title: Align pulmonary termination behavior before composition

Description: Add the approved Tier 3 and Tier 4 pulmonary termination events while preserving all previously approved starts, exclusions, and boundary behavior.

working hours: 3

Priority: 1

title: Build exact organ-dysfunction segments and episodes

Description: Re-evaluate the six configured organ strategies at measurement, expiration, and pulmonary transition times and collapse contiguous state into auditable episodes.

working hours: 5

Priority: 1

title: Associate infection anchors with organ episodes

Description: Apply the configured half-open 48-hour window to every exact-deduplicated infection anchor and calculate approved onset timestamps.

working hours: 4

Priority: 1

title: Build and integrate Sepsis 2 encounter summaries

Description: Preserve negative encounters, add evidence counts, wire the pipeline into main_strategy.py, and expose versioned no-overwrite outputs.

working hours: 2

Priority: 1

title: Validate and document Sepsis 2

Description: Add organ-adapter, association, boundary, regression, and aggregate-only smoke tests and document the clarified timestamp semantics.

working hours: 3

Priority: 2
