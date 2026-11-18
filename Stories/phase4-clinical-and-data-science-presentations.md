Title: Create audience-specific Phase 4 pipeline presentations

Description: As a project stakeholder, I want separate presentations for the clinical and data science teams, so that each audience can understand the clinical findings, approved sepsis definitions, and technical implementation at the appropriate level of detail.

Acceptance criteria:
- Two distinct Marp-compatible PowerPoint-style Markdown presentations are created: one for the clinical team and one for the data science team.
- The clinical presentation explains active EHR inputs, measurement validity and expiration, suspected-infection pathways, SIRS, six-organ dysfunction, pulmonary evidence, hypotension, lactate, vasopressors, both Sepsis 3 pathways, retrospective onset, criterion completion, final severity, and POA/NPOA categorization.
- The clinical presentation highlights clinically important implementation findings and known differences between configured, active, and excluded behavior without presenting them as approved causal conclusions.
- The data science presentation maps `main_strategy_phase4.py` to its invoked `src_strategy/` workflow, including ingestion, collision resolution, temporal aggregation, Strategy/Registry criteria, state reconstruction, association, encounter categorization, and versioned publication.
- The data science presentation documents table grains, code-defined schemas, all declared clinical output files, caches, monitoring artifacts, run-directory structure, Git-backed identity, manifest contents, hashes, and publication validations.
- Clinical findings and definitions are consistent across both presentations, while technical depth and terminology are adapted to the intended audience.
- The data science presentation is derived from invoked code and configuration without inspecting patient data, notebook outputs, or patient-level persisted results.
- Both presentations avoid patient identifiers, keep diagrams readable in source form, use balanced Markdown fences, and clearly distinguish implemented behavior from limitations.
- Validation confirms that every configured clinical output filename appears in the technical presentation and that schema examples can be generated from empty frames without loading patient records.

Story hours: 12

title: Review clinical definitions and implemented findings

Description: Reconcile the active Phase 4 composition, configuration, completed-run identity, and documented implementation findings before drafting either presentation.

working hours: 2

Priority: 1

title: Create the clinical-team presentation

Description: Build an accessible clinical deck covering evidence sources, criteria, timing, severity composition, important findings, limitations, and POA/NPOA classification.

working hours: 4

Priority: 1

title: Create the data-science-team presentation

Description: Build a technical deck covering pipeline architecture, transformations, data grains, schemas, outputs, run identity, manifests, and publication safeguards.

working hours: 4

Priority: 1

title: Validate presentation completeness and safety

Description: Check output-file coverage, schema-only examples, Markdown structure, terminology consistency, audience separation, and absence of patient-level information.

working hours: 2

Priority: 2
