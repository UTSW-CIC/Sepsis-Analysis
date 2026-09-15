Title: Integrate pulmonary dysfunction into six-organ composition

Description: As a clinical billing reviewer, I want pulmonary dysfunction reconstructed from auditable encounter evidence and included as the sixth organ system, so that Sepsis 2 classification uses the approved organ-dysfunction definition.

Acceptance criteria:
- Given qualifying invasive ventilation, non-invasive ventilation, or P/F ratio below 200, when pulmonary transitions are reconstructed, then pulmonary dysfunction begins at the qualifying evidence time.
- Given Tier 3 high-flow, Tier 4 non-rebreather, or P/F ratio above 200, when pulmonary transitions are reconstructed, then pulmonary dysfunction terminates at the qualifying evidence time.
- P/F ratio exactly 200 does not change pulmonary state.
- Encounter-wide home-ventilation or tracheostomy exclusions force pulmonary state to zero while retaining exclusion evidence.
- Termination wins when start and termination evidence occur simultaneously.
- Pulmonary state is attached to the temporal wide table without changing its keys, row order, or existing values.
- Pulmonary dysfunction contributes to the configured six-organ total and is exposed through versioned, no-overwrite outputs.

Story hours: 20

title: Define pulmonary configuration and input contract

Description: Configure start, termination, exclusion, transition, evidence, and output fields using the approved source groupers and support values.

working hours: 3

Priority: 1

title: Implement pulmonary start and termination criteria

Description: Implement registry-selected transition strategies, including the approved Tier 1/2 starts and Tier 3/4 termination events.

working hours: 4

Priority: 1

title: Implement exclusions and pulmonary state reconstruction

Description: Retain encounter exclusion evidence and reconstruct nullable, half-open pulmonary state intervals with termination-wins behavior.

working hours: 4

Priority: 1

title: Attach pulmonary state to the temporal wide table

Description: Carry the latest pulmonary state and evidence to aggregate instants while validating key and row preservation.

working hours: 3

Priority: 1

title: Register pulmonary as the sixth organ strategy

Description: Map reconstructed pulmonary state to the pulmonary failure flag and include it in the combined organ-dysfunction calculation.

working hours: 2

Priority: 1

title: Integrate outputs and validate pulmonary composition

Description: Wire the pulmonary and six-organ pipeline into main_strategy.py, add versioned outputs, focused tests, full regression checks, and aggregate-only smoke validation.

working hours: 4

Priority: 2
