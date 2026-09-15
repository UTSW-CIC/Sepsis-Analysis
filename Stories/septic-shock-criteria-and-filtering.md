Title: Build auditable septic-shock criteria with optional BP filtering

Description: As a clinical billing reviewer, I want septic shock calculated from the approved blood-pressure, lactate, and vasopressor evidence, so that shock classification is temporally correct and clinically reviewable.

Acceptance criteria:
- SBP below 90, baseline-to-current SBP decline above 40, MAP below 65, lactate above 4, or a qualifying vasopressor administration can establish septic shock.
- SBP and MAP expire after eight hours and lactate expires after six hours, with evidence cleared at the exact expiration instant.
- Vasopressor medication orders, null doses, and zero doses do not qualify; a recorded positive administration dose qualifies only at its exact timestamp.
- Nonqualifying vasopressor rows remain available for audit.
- When BP filtering is disabled, raw BP criteria contribute directly to shock.
- When BP filtering is enabled, only retained positive BP episode lineage contributes; lactate and vasopressor pathways remain independent.
- Raw BP component flags remain available as audit evidence when filtered hypotension controls classification.
- The active composition exposes versioned shock and hypotension evidence outputs without overwriting prior artifacts.

Story hours: 24

title: Configure septic-shock criteria and registry

Description: Define selectable clinical criteria, thresholds, evidence columns, and output names in configuration.

working hours: 3

Priority: 1

title: Implement numeric shock strategies and reducer

Description: Implement nullable SBP, SBP-decline, MAP, and lactate strategies and combine them with auditable boolean OR reduction.

working hours: 4

Priority: 1

title: Build vasopressor administration evidence

Description: Retain all relevant medication evidence while marking only positive qualifying administrations as exact-time shock evidence.

working hours: 4

Priority: 1

title: Reuse existing BP episode-filter lineage

Description: Map retained source episodes to effective hypotension and attach the half-open effective state without rebuilding the approved filtration process.

working hours: 5

Priority: 1

title: Integrate septic shock into main_strategy.py

Description: Order BP filtering before shock calculation, keep shock independent from organ input, and add versioned outputs with preflight protection.

working hours: 3

Priority: 1

title: Validate shock criteria and document decisions

Description: Add boundary, medication, filtering, regression, and aggregate-only real-data smoke checks and record the approved clinical decisions.

working hours: 5

Priority: 2
