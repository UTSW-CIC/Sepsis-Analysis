Title: Reconstruct auditable Phase 4 clinical evidence from linked EHR events

Description: As a clinical billing reviewer, I want Phase 4 infection and organ-dysfunction evidence reconstructed from correctly typed and linked EHR events, so that every qualifying Sepsis association is clinically interpretable and traceable to its source.

Acceptance criteria:
- Blood-culture and lactate criteria qualify from procedure orders linked by encounter and `Event_ID`; result rows are retained for audit but do not independently establish suspected infection.
- IV-antibiotic evidence requires a positive administration, retains linked order and administration times, and applies the approved 72-hour-before/24-hour-after culture window.
- Each IV-antibiotic or lactate criterion produces one canonical infection episode with one downstream anchor, while retaining all qualifying culture-order evidence and a separate criterion-completion timestamp.
- Direct Code Sepsis and Sepsis Documentation criteria match only the approved `(Event_Grouper, Event_Name)` pairs and produce auditable one-event infection episodes.
- Pulmonary dysfunction applies the approved Vent On/Off roles, scoped null termination, high-flow/non-rebreather termination, P/F `<200` start rule, and encounter-wide home-ventilation exclusion.
- PaO2 and FiO2 retain separate source identifiers and use the approved nearest-FiO2-within-two-hours pairing without using `Event_ID` as a pairing key.
- Cardiovascular, renal, hepatic, coagulation, and neurological features use the approved source types and retain aligned value, result time, type, event ID, and event name through organ episodes and Sepsis 2/3 evidence.
- Missing aPTT evidence remains unavailable, does not satisfy coagulation dysfunction, and does not interrupt downstream processing.
- Focused tests and aggregate-only smoke validation confirm source-role mapping, time-window boundaries, provenance completeness, and unchanged encounter/timestamp grain.

Story hours: 32

title: Link infection orders, administrations, and results

Description: Implement Event_ID-aware culture, lactate, and antibiotic evidence while preserving the distinct qualification and audit roles of orders, administrations, and results.

working hours: 6

Priority: 1

title: Build canonical suspected-infection episodes

Description: Group qualifying evidence into one episode per antibiotic or lactate anchor, calculate infection and criterion-completion timestamps, and emit one downstream anchor per episode.

working hours: 5

Priority: 1

title: Implement exact direct-event criteria

Description: Restrict Code Sepsis matching to the approved event pairs and add the Sepsis Documentation direct-event pathway with the corrected criterion name.

working hours: 3

Priority: 1

title: Update pulmonary transition reconstruction

Description: Apply the approved start, termination, continuation, neutral, exclusion, and P/F rules while retaining transition and PaO2/FiO2 provenance.

working hours: 7

Priority: 1

title: Propagate non-pulmonary organ provenance

Description: Carry aligned selected-measurement evidence through aggregation, exact organ segments, organ episodes, and downstream Sepsis associations.

working hours: 5

Priority: 1

title: Validate the Phase 4 evidence contract

Description: Add focused boundary and provenance tests and run privacy-safe aggregate smoke checks for cardinality, source coverage, and unavailable evidence.

working hours: 6

Priority: 2
