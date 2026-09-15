Title: Categorize Sepsis 1 from infection anchors and effective SIRS episodes

Description: As a clinical billing reviewer, I want Sepsis 1 evidence associated at the encounter level, so that suspected infection plus qualifying SIRS can be classified with traceable onset timestamps.

Acceptance criteria:
- Every suspected-infection evidence row is treated as an independent anchor after exact deduplication by encounter, timestamp, criterion, and infection type.
- A qualifying SIRS-positive episode must overlap the configured 24-hour backward/forward infection window with positive elapsed duration.
- When SIRS filtering is enabled, only retained effective positive episodes qualify; when disabled, raw positive episodes qualify.
- `sepsis_1_dt` is the later of infection time and SIRS episode start.
- `sepsis_1_earliest_evidence_dt` is the earlier of infection time and SIRS episode start.
- Association-level evidence is retained before encounter reduction.
- Encounter output retains negative encounters and counts associations, anchors, and SIRS episodes.

Story hours: 15

title: Build effective SIRS episode state

Description: Convert the existing raw and filtered SIRS episode lineage into a classification-effective positive flag controlled by configuration.

working hours: 3

Priority: 1

title: Build exact-deduplicated infection anchors

Description: Preserve every approved infection evidence row while removing only exact duplicate anchors and assigning stable encounter-local IDs.

working hours: 2

Priority: 1

title: Associate infection anchors with SIRS episodes

Description: Apply the configured half-open temporal window and calculate classification and earliest-evidence timestamps for every qualifying association.

working hours: 4

Priority: 1

title: Build Sepsis 1 encounter summaries

Description: Reduce qualifying associations to one auditable row per encounter while retaining negative encounters and evidence counts.

working hours: 2

Priority: 1

title: Integrate and validate Sepsis 1

Description: Wire Sepsis 1 into main_strategy.py, add versioned outputs, boundary tests, regression checks, smoke validation, and inline documentation of the sensitivity-first anchor policy.

working hours: 4

Priority: 2
