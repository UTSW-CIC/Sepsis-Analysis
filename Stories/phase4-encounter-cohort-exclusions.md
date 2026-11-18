Title: Apply auditable encounter-level cohort exclusions before Phase 4 processing

Description: As a clinical billing reviewer, I want configured encounter exclusions applied before event processing, so that every downstream clinical and analysis result uses the approved cohort and excluded encounters remain reviewable.

Acceptance criteria:
- Encounters discharged after September 30, 2026 are excluded, while encounters discharged on September 30 remain eligible.
- Encounters with integer `Cancer_Registry_YN == 1` are excluded; zero or null retains the encounter for that rule.
- Exclusion policy is stored separately from input/schema configuration and supports stable rule names, enabled flags, approved comparison operators, and explicit null behavior.
- Rules use OR composition, so any matching rule excludes the encounter while all matching reasons are preserved.
- Exclusions are evaluated after encounter casting and deduplication, and every transactional source is restricted to retained encounter IDs before preprocessing.
- The Phase 4 loader returns eligible events, eligible encounters, and a long-form exclusion audit.
- The versioned clinical bundle publishes `df_encounter_exclusions.parquet`, and exclusion settings contribute to the run configuration hash.
- Missing configured columns, invalid rules, and an empty eligible cohort fail fast.
- Focused tests and aggregate validation confirm configured types, overlapping reasons, retained/excluded counts, and absence of exposed patient-level records in diagnostics.

Story hours: 14

title: Define the exclusion configuration contract

Description: Add separately configured discharge-date and cancer rules with operator validation, stable names, enabled flags, and null-retention behavior.

working hours: 3

Priority: 1

title: Implement the exclusion evaluator

Description: Evaluate configured single-column rules in Polars, compose them with OR logic, and preserve every matching reason in a long-form audit.

working hours: 4

Priority: 1

title: Integrate exclusions into Phase 4 ingestion

Description: Apply exclusions after encounter casting and deduplication, filter all transactional sources to eligible encounters, and return the audit explicitly.

working hours: 3

Priority: 1

title: Publish and hash the exclusion audit

Description: Add the audit to the versioned clinical outputs and include exclusion configuration in run identity and manifest validation.

working hours: 2

Priority: 2

title: Test and validate cohort exclusions

Description: Cover cutoff boundaries, nulls, overlapping rules, invalid configuration, empty cohorts, source filtering, and privacy-safe aggregate counts.

working hours: 2

Priority: 2
