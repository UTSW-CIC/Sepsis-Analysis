# Phase 4 clinical-definition presentation — 2026-11-12

## Request and scope

The owner requested a PowerPoint-style Markdown presentation for a clinical
team covering only the clinical data pipeline executed by
`main_strategy_phase4.py`. Analysis-pipeline statistics and figures are outside
scope.

## Implementation

Created the Marp-compatible deck:

`docs/ppts/phase4_clinical_definitions.md`

The deck describes:

- active EHR inputs and the clinical data flow;
- measurement validity periods and exact expiration behavior;
- five suspected-infection pathways and their timelines;
- SIRS thresholds and the enabled 20-minute episode filter;
- all six organ-dysfunction systems;
- pulmonary start, termination, P/F pairing, and encounter-wide exclusions;
- the ±24-hour Sepsis 1 and ±48-hour Sepsis 2 association windows;
- hypotension reconstruction and its enabled 20-minute filter;
- lactate and vasopressor evidence;
- both active Sepsis 3 pathways;
- onset versus criterion-completion timestamps; and
- final severity and Arrival + 48-hour POA/NPOA categorization.

Timeline diagrams use fixed-width Markdown blocks so the source remains
readable without an external diagram renderer.

## Important implementation findings documented for clinical review

- Vasopressor Pathway B can produce Sepsis 3 without Sepsis 2.
- Active Sepsis 3 Pathway A uses lactate >2 with filtered hypotension; the
  configured lactate >4 strategy is not called by `main_strategy_phase4.py`.
- POA/NPOA uses earliest-evidence onset rather than criterion-completion time.
- Sepsis 2 selects the first positive episode per organ type before infection
  association, so a later episode cannot replace an earlier non-overlapping
  episode of that type.
- INR/aPTT qualify coagulation dysfunction only when baseline platelets are
  missing.
- P/F recovery is not an active pulmonary termination pathway.
- Culture-result status is audit-only for suspected infection.
- The configured perioperative-antibiotic exclusion is not applied by the
  active detector.
- Event encounter-boundary restriction is delegated to the source extracts.
- Aggregation, collision, and outlier registries are not currently included in
  the versioned run's registered configuration snapshot.

## Evidence reviewed

The presentation was derived from the active composition script, its imported
configuration and event modules, and the completed Phase 4 run manifest:

`20261111T191702Z__b1b37c26968f__cfg-4036c016b122`

The manifest labels the implemented clinical definition as version `4`.
