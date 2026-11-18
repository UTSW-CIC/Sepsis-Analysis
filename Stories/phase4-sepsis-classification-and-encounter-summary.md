Title: Classify Phase 4 sepsis with two shock pathways and earliest-evidence onset

Description: As a clinical billing reviewer, I want Sepsis 1, 2, and 3 composed into one auditable encounter classification, so that severity, onset, POA/NPOA status, and billed-category agreement follow the approved retrospective rules.

Acceptance criteria:
- The SIRS and hypotension duration filters are enabled by default, and filtered effective episodes—not removed short episodes—contribute to classification.
- Sepsis 3 Pathway A requires Sepsis 2, effective hypotension, and lactate `>2` evidence associated with the same suspected-infection anchor and its inclusive plus/minus 48-hour window; simultaneous component overlap is not required.
- Sepsis 3 Pathway B requires suspected infection and a positive-dose vasopressor administration within the inclusive plus/minus 48-hour window and can qualify independently of Sepsis 2.
- Vasopressor orders and administrations are linked by encounter, grouper, and `Event_ID`; order-only evidence does not qualify, and an unlinked positive administration uses its administration time as the anchor.
- Dopamine follows the same positive-administration qualification rule as the other configured vasopressors.
- Sepsis 3 evidence retains the qualifying pathway, retrospective onset, criterion-completion time, and distinct infection, organ, blood-pressure, lactate, order, and administration timestamps.
- The primary Sepsis 1, Sepsis 2, and Sepsis 3 timestamps use the earliest contributing evidence rather than the time at which all criteria are complete.
- Final calculated severity is the highest positive severity, and final onset is the earliest explicit evidence timestamp among all positive severity groups.
- Onset at exactly `Arrival_Instant + 48 hours` is POA; later onset is NPOA; encounters without calculated sepsis receive severity 0, null onset, and `No Sepsis`.
- The final one-row-per-encounter output preserves billed `Sepsis_Category`, approved outcome/timing fields, component summaries, and a calculated-versus-billed match indicator.

Story hours: 27

title: Enable classification-active duration filters

Description: Make the approved SIRS and blood-pressure episode filters active by default while preserving raw episode evidence for audit.

working hours: 3

Priority: 1

title: Implement Sepsis 3 Pathway A

Description: Associate Sepsis 2, effective hypotension, and lactate greater than 2 with the same infection-anchor window and retain component evidence without requiring simultaneous overlap.

working hours: 5

Priority: 1

title: Implement Sepsis 3 Pathway B

Description: Link positive vasopressor administrations to orders where available, associate them with infection anchors, and support administration-time fallback and Dopamine.

working hours: 5

Priority: 1

title: Correct retrospective sepsis onset

Description: Use the earliest contributing timestamp for each Sepsis severity and for the final encounter onset while retaining criterion-completion timestamps separately.

working hours: 4

Priority: 1

title: Build the final encounter classification

Description: Combine all three severity summaries into one row per encounter with maximum severity, first onset, inclusive Arrival-plus-48-hour POA/NPOA status, and billed-category comparison.

working hours: 4

Priority: 1

title: Validate classification and encounter composition

Description: Add focused pathway, onset, boundary, invalid-state, and output-uniqueness tests and complete an aggregate-only smoke calculation.

working hours: 6

Priority: 2
