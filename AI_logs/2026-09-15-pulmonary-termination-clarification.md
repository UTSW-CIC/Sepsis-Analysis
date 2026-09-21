# Pulmonary termination clarification — 2026-09-15

## Questions resolved

1. Should `"$ Extubation"` remain a Vent On/Off termination value after
   removing `Standby` and null-valued Vent On/Off events?

   **Owner decision:** Yes. Use `"$ Extubation"` instead of `Standby` as the
   Vent On/Off termination value. A null Vent On/Off value is not a
   termination event.

2. Should P/F ratio recovery above 200 terminate pulmonary dysfunction?

   **Owner decision:** No. P/F ratio can start pulmonary dysfunction, but a
   P/F ratio greater than 200 cannot terminate it.

## Implementation status

- The current `VentOnOffConfig` reflects the approved Vent On/Off decisions.
- P/F termination remains registered so an explicit alternate configuration
  can enable it, but the default `selected_termination` list excludes it.
- The pulmonary state orchestrator skips P/F termination scoring when it is
  not selected and supplies a neutral combined termination flag. P/F start
  evidence remains enabled.
- Regression tests verify that P/F recovery does not terminate pulmonary
  dysfunction by default and that explicitly enabling the criterion restores
  the prior behavior.

## Validation after implementation

- Pulmonary state and configuration tests: 17 passed.
- Enabled P/F termination and registry tests: 2 passed.
- Pulmonary, organ-dysfunction, and downstream Sepsis regression selection:
  75 passed.
- Full maintained suite: 213 passed and 4 failed. The failures are stale
  Vent On/Off/raw-termination test fixtures, the previously identified SIRS
  enabled-state expectation, and the previously identified earliest-only
  antibiotic/culture expectation; none exercise the new disabled P/F path.
