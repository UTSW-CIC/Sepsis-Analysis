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
- The current pulmonary P/F termination registry is disabled, reflecting the
  approved start-only P/F behavior.
- Existing tests and the authoritative clinical-definition document still
  encode the prior behavior and require an explicitly authorized update.
- No clinical code or tests were changed while recording this clarification.
