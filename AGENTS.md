# Sepsis billing-classification project

## Session Start Checklist

Before beginning each session, review `AI_logs/` for dated summaries of prior work. Each file contains:
- Summary of design decisions and implementation status
- Checklist of remaining tasks
- Open questions and assumptions
- Files to modify and current state

This ensures continuity and prevents rework.

## Mission and scope

The primary goal is to build an auditable algorithm that uses all available EHR data from a patient encounter (arrival through discharge) to determine whether the encounter meets the project's clinical criteria for Sepsis 1, Sepsis 2, or Sepsis 3 and whether it is present-on-admission (POA) or not-present-on-admission/hospital-acquired (NPOA). The result is intended to support billing review: compare the calculated classification and timing with the billed classification and identify likely missed or incorrect sepsis coding.

Do not treat the classifier as a generic real-time alerting system. It is currently a retrospective, encounter-level determination using the full encounter record. Preserve the evidence and timestamps behind every classification so the result can be reviewed clinically and for billing.

`src_strategy/` is the current development source. It is a Strategy/Registry redesign of the older runnable pipeline in `src/`; do not assume that every downstream capability has already been ported. `README.md` and analysis documents contain useful history and hypotheses, but they are not substitutes for an approved clinical/billing specification.

## How to collaborate with the project owner

The project owner is learning how to design reliable, well-structured software. The assistant's primary role is to help the owner comprehend the domain and code, reason through design choices, review work, expose assumptions and failure modes, and teach relevant software-engineering principles. Do not independently take over or broadly build the project. Implement code only when requested, keep changes small and reviewable, and explain why the design works and what tradeoffs it makes.

The intended patterns are:

- **Strategy + Registry** for configurable sepsis criteria and their reduction/composition.
- **Template Method** for the analysis pipeline's stable workflow with customizable analysis steps.
- **Pipes and Filters** for ordered ingestion/data-preparation transformations.

`docs/GUIDES/REDESIGN_GUIDE.md` is the working design reference for the redesign. Apply it incrementally, use existing behavior/golden outputs as a parity oracle, and avoid introducing abstractions before a concrete variation requires them.

## Authoritative clinical definition

`docs/clinical_definitions 3_1.docx` is the current source of truth for clinical criteria and validity periods. Re-open it before changing clinical logic; do not infer criteria from `README.md` when the two disagree. It was reviewed for this summary on 2026-07-31.

Its current high-level definitions are:

- **Suspected infection:** at least one of (a) a blood-culture order from 72 hours before through 24 hours after an administered IV antibiotic, (b) two blood-culture orders within six hours of a lactate order, (c) a Suspected Infection flowsheet answer of `Yes`, or (d) a Code Sepsis page order in the encounter.
- **Sepsis/SIRS criteria:** at least two abnormal criteria among most-recent temperature (`>100.4°F` or `<96.8°F`), pulse (`>90 bpm`), respiratory rate (`>20/min`), and WBC (`>12` or `<4 ×10³/µL`).
- **Severe sepsis/organ dysfunction:** dysfunction in at least one pulmonary, renal, hepatic, coagulation, cardiovascular, or neurological system. Pulmonary dysfunction has four support/P/F tiers, explicit termination events, and home-ventilation/tracheostomy exclusions; consult the document rather than reducing it to a simple vent flag.
- **Septic shock:** at least one of most-recent SBP `<90`, average-to-current SBP decline `>40`, most-recent MAP `<65`, most-recent lactate `>4`, or a recorded dose of vasopressin, phenylephrine, norepinephrine, or epinephrine.
- **Feature validity:** temperature, pulse, respiratory rate, and blood pressure are valid for 8 hours; GCS, WBC, creatinine, eGFR, bilirubin, INR, and BUN for 12 hours; platelets and aPTT for 24 hours; lactate for 6 hours. Aggregation is the most recent value. When validity expires without a confirming measurement, the value/flag clears.

The required outputs are Sepsis 1/2/3 and POA/NPOA. The current implementation produces/compares a final encounter classification; the intended evolution is to retain every sepsis episode or state transition and its evidence interval as well as the final encounter result. Missing or insufficient evidence currently resolves to **no sepsis**, not an indeterminate class.

The severity composition is:

- **Sepsis 1:** suspected infection + SIRS score ≥ 2.
- **Sepsis 2:** suspected infection + at least one organ dysfunction. Sepsis 1 is not a prerequisite.
- **Sepsis 3:** Sepsis 2 + septic shock.

POA/NPOA analysis uses two independent reference points: inpatient admission time and `Arrival_Instant + 48 hours`. Calculate and compare both definitions to demonstrate how the POA/NPOA distribution changes. Most final statistics and analyses should use `Arrival_Instant + 48 hours` as the primary reference point. The repository schema currently names the admission field `InpatientAdmissionInstant`; use the configured/schema name rather than introducing a competing `InpatientAdmissionTime` column without an explicit migration.

## Current intended data flow

1. **Ingest and normalize EHR sources.** Read encounter/baseline, flowsheet, lab, medication-administration, procedure-order, and diagnosis CSV files. Cast the configured schema, remove duplicates on configured source-event keys, normalize the common event columns, extract systolic/diastolic/MAP values, calculate P/F-related fields, and apply configured physiological-bound checks. Extreme values are retained in monitoring artifacts and replaced with null in the analytic value fields.
2. **Create the unified longitudinal event table.** Combine transactional sources into a long Polars dataframe keyed primarily by `EncounterEpicCsn`, `Event_DateTime`, `Type`, `Event_Grouper`, and `Event_Name`. Keep encounter/baseline data separately until deliberately joined upstream of criteria that require it.
3. **Resolve same-instant collisions.** `ResolveCollision` handles multiple numeric readings for the same encounter, instant, event type, and grouper using the per-feature registry in `src_strategy/configs/collision.py`. Strategies include min, max, and the value farthest outside a configured normal interval (`worst`). Blood pressure requires special handling because systolic and MAP live in dedicated columns.
4. **Build the temporal wide feature table.** Start from a backbone of unique `(EncounterEpicCsn, Event_DateTime)` rows. `Aggregator` creates one column per registered feature and carries/aggregates prior measurements over that feature's configured validity/lookback period. Windows are backward-looking and inclusive of the reference instant; the backbone currently contains observed event instants rather than a regular time grid.
5. **Apply clinical criteria and classify the encounter.** The planned downstream stages use the wide features to calculate SIRS, suspected infection, organ dysfunction (including pulmonary dysfunction), septic shock, sepsis severity/onset, and ultimately an encounter-level billing classification with supporting evidence. In `src_strategy`, much of this downstream stage currently exists only as configuration and still needs implementation/porting and parity validation.

The active composition script is `main_strategy.py`. It imports `DataLoader` from `src_strategy/data_ingest/dataloader_1.py`; `src_strategy/data_ingest/dataloader.py` is an older path and should not be described as active without rechecking the entry point.

## Clinical and billing intent

- Suspected infection must follow `clinical_definitions 3_1.docx` and cannot be inferred from antibiotics alone. The IV antibiotic + culture timing, two-culture + lactate proximity, Code Sepsis order, and suspected-infection flowsheet signal must all be implemented and tested as specified; differences in current configuration/code are implementation gaps to review.
- Time validity matters. A prior vital, lab, medication, or support status may influence a later instant only within its explicitly configured validity window.
- Same-instant collisions must be resolved deterministically and conservatively, with the original evidence traceable. Resolution rules affect clinical severity and require tests.
- Baseline/chronic disease, perioperative antibiotics, transient/push-dose vasopressors, home ventilation, and other non-sepsis explanations must be handled explicitly where the approved definition requires them.
- Final outputs should make false positives and false negatives inspectable: classification, onset/time zero, severity, POA/NPOA status if applicable, criteria met, contributing source events, and missing/ambiguous evidence.
- Although missing/insufficient evidence maps to “no sepsis,” retain enough provenance to distinguish “criteria evaluated and not met” from “source evidence absent” during validation and review.
- Never silently change a clinical threshold, time window, exclusion, missing-data interpretation, or billing label. Put such values in configuration, document the rationale/provenance, and add regression tests.

## Architecture and implementation principles

- Use Polars for dataframe transformations and DuckDB where its temporal joins/aggregations are useful.
- Ingestion is an ordered pipes-and-filters workflow. Clinical criteria and reducers are intended to use Strategy/Registry composition. Follow `docs/GUIDES/REDESIGN_GUIDE.md` incrementally rather than doing a speculative wholesale rewrite.
- Keep the older implementation runnable while porting. For each module, capture representative old output, add a parity/golden test, port the smallest unit, and remove the old implementation only after parity and intended clinical changes are understood.
- Prefer configuration/registries as the single source of truth for event groupers, value columns, aggregation method, validity period, thresholds, and enabled criteria.
- Validate invariants at each boundary: schemas and uniqueness after ingestion, one resolved numeric state per collision key, one row per backbone key, direct-event values preserved at their own timestamp, and feature expiration immediately after its validity window.
- Treat all EHR data as sensitive. Do not print, commit, or expose patient identifiers or raw patient-level records. Keep generated data, logs, and review artifacts out of version control unless they are explicitly de-identified and approved.

## Verified current limitations and hazards (reviewed 2026-07-31)

- `Aggregator._aggregate_by_duckdb()` updates `backbone` in its loop but has no return statement, so `aggregate(..., engine="duckdb")` currently returns `None`.
- The MAP feature registry uses `val_col="mean"`, while current ingestion and collision code use `map`; this will fail or select the wrong column until aligned.
- The current `main_strategy.py` loads saved no-collision/backbone parquet files and reaches aggregation, but it does not yet run an end-to-end encounter sepsis/billing classification.
- `dataloader_1.py` returns `(df_all_joined, encounters)` and does not itself enforce arrival-to-discharge boundaries or join baseline columns into the event table. Confirm whether source extracts already enforce encounter boundaries and deliberately join baselines before baseline-dependent criteria.
- Blood-pressure collision resolution can select systolic and MAP independently, then tries to recover one original row containing both selected values. If the selected values came from different source rows, the resolved event may be lost. Add a focused test before relying on this behavior.
- Collision and aggregation modules have assertions and monitoring, but there is not yet a dedicated automated test suite covering same-instant resolution, exact validity-window boundaries, missing values, ties, and feature expiration.
- Feature and collision registries are incomplete/inconsistent for some downstream criteria (for example creatinine is aggregated but has no explicit collision rule; medication units and administration semantics need clinical normalization).
- The clinical-definition document includes BUN with a 12-hour validity period, but the current aggregation feature registry has no BUN feature.
- The document requires two blood-culture orders within six hours of a lactate order; the current suspected-infection configuration names the proximity window but does not itself demonstrate that the two-culture cardinality is enforced.
- The document uses the names Sepsis, Severe Sepsis, and Septic Shock; use the project-owner-approved Sepsis 1/2/3 composition recorded above when translating those criteria into final labels.

Do not “fix” these by guessing clinical behavior. Technical defects can be corrected with focused tests; clinical ambiguities require an explicit decision.

## Questions awaiting project-owner confirmation

1. Which billed fields/codes are available as the comparison reference, and is the goal agreement with billing, clinically adjudicated truth, or identification of disagreements for review?
2. Are the collision strategies and medication administration/unit normalization rules clinically approved? The feature validity periods and clinical thresholds should follow `clinical_definitions 3_1.docx`, but ownership/sign-off for revisions is still needed.
3. Do the source extracts already contain only events between arrival and discharge, and how should pre-arrival baselines or post-discharge/result timestamps be treated?
4. What validation cohort and acceptance metrics should gate use (for example clinician-adjudicated encounters, sensitivity/PPV targets, and separate POA/NPOA performance)?
