# DataLoader V2 Refactor — 2026-08-23

## Decisions

- Keep `src_strategy/data_ingest/dataloader_1.py` frozen as the current parity
  oracle and active loader.
- Add `src_strategy/data_ingest/dataloader_2.py` as an opt-in implementation with
  the same constructor and `load_data() -> (events, encounters)` contract.
- Keep `main_strategy.py` on V1 until the project owner reviews V2 parity.
- Move outlier artifact generation and mismatch validation to a focused
  `OutlierMonitor`; it observes data but does not transform it.
- Preserve current clinical and ingestion behavior during this refactor.

## Deferred Hazards

- Source-specific columns are still dropped during concatenation and rejoined
  on the existing key. Join-cardinality changes require a separate focused test
  and owner-reviewed correction.
- Bounds and P/F configs retain V1's optional annotations even though the active
  workflow expects them to be supplied.
- Full support for custom BP column names remains limited by the BP bounds
  configuration defaults.
- Arrival-to-discharge filtering remains unresolved pending source-boundary
  confirmation.

## Validation Requirements

- V1 and V2 must match on synthetic end-to-end inputs and real-data aggregate
  fingerprints.
- Do not commit patient-level parity artifacts.

