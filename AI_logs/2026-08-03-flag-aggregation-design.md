# Flag Aggregation Design — 2026-08-03

## Summary

Designed a new **flag-type aggregation** feature for the `Aggregator` pipeline to handle boolean event states (e.g., vasopressor on/off) that persist across time and terminate on explicit stop events or validity expiry.

## Problem

Current `Aggregator` only supports numeric aggregation (max/min/last). Sepsis classification requires tracking:
- Vasopressor administration status (flag = 1 when on, 0 when off)
- Ventilation support status
- Other binary event states that remain true until a termination event or validity window expires

## Solution: Flag-Type Aggregation

### Architecture

1. **FeatureDefinition** (src_strategy/configs/aggregator.py):
   - Add `agg_type: Literal["numeric", "flag"] = "numeric"`
   - Add `flag_true_values: list[str] | None = None` — text values marking "on" (e.g., ["Yes", "Administered"])
   - Add `flag_false_values: list[str] | None = None` — text values marking "off" (e.g., ["No", "Stopped"])
   - Add `persist_until_termination: bool = True` — flag persists until false event or validity expires
   - Add optional `termination_event_grouper: str | None = None` — separate grouper that can terminate the flag
   - Keep `val_col`, `lookback_period`, `event_grouper`, `alias` unchanged

2. **Aggregator** (src_strategy/data_preparation/aggregator.py):
   - Add `rolling_flag_by_duckdb()` helper:
     - For each backbone instant, find `last_true_ts` = latest true-valued event within lookback
     - Find `last_false_ts` = latest false-valued event within lookback
     - Return flag = 1 if `last_true_ts > last_false_ts` (true dominates)
     - Return flag = 0 otherwise
   - Add optional columns: `<alias>_last_set_ts` (timestamp of flag onset), `<alias>_evidence` (event provenance)
   - Branch in `_aggregate_by_duckdb()`:
     - if `feature.agg_type == "numeric"`: call existing `rolling_agg_by_duckdb()`
     - elif `feature.agg_type == "flag"`: call new `rolling_flag_by_duckdb()`

3. **Collision Handling** (src_strategy/data_preparation/resolvecollision.py + collision.py):
   - Extend collision config to optionally specify `agg_type: "flag"` for certain groupers
   - Define tie-breaker policy: prefer `false` by default for same-instant true/false conflicts (safer)
   - Resolve same-instant collisions *before* rolling aggregation so aggregator receives clean data

### Key Design Decisions

1. **FeatureDefinition stays clean**: Only aggregation logic; no tie-breaker policy.
2. **Collision resolution is separate**: Same-instant conflicts handled upstream by `ResolveCollision`.
3. **SQL-driven**: Uses DuckDB `MAX(CASE WHEN...)` to find latest true/false timestamps.
4. **Backward compatible**: Numeric features unchanged; flag features opt-in via `agg_type`.
5. **Provenance tracking**: Retain `_last_set_ts` and optional `_evidence` for audit/clinician review.

### Implementation Checklist

- [ ] **Step 1**: Add fields to `FeatureDefinition` (agg_type, flag_true_values, flag_false_values, persist_until_termination, termination_event_grouper)
- [ ] **Step 2**: Add validation to ensure flag features have required flag_* fields
- [ ] **Step 3**: Add vasopressor flag feature to `FEATURE_REGISTRY`
- [ ] **Step 4**: Implement `rolling_flag_by_duckdb()` in `Aggregator`
- [ ] **Step 5**: Branch in `_aggregate_by_duckdb()` to route numeric vs flag paths
- [ ] **Step 6**: Extend collision config for flag-aware same-instant resolution (if needed)
- [ ] **Step 7**: Add tests: unit tests (on/off/expiry/tie), integration/golden test
- [ ] **Step 8**: Verify numeric features still work (regression test)

### Next Steps

1. Implement FeatureDefinition changes
2. Implement rolling_flag_by_duckdb() with exact SQL logic
3. Add aggregator branching
4. Add regression test to ensure numeric features unaffected
5. Add flag-specific unit tests (at minimum: start→carry→expiry, true then false, same-instant tie)
6. Optional: Extend collision config if vasopressor source data has simultaneous true/false rows

### Files to Modify

- `src_strategy/configs/aggregator.py` — FeatureDefinition, FEATURE_REGISTRY
- `src_strategy/data_preparation/aggregator.py` — rolling_flag_by_duckdb, _aggregate_by_duckdb branching
- `src_strategy/configs/collision.py` — optional flag-aware fields (if tie-break policy needed)
- `tests/` — new test file `test_aggregator_flag.py` or extend existing aggregator tests

### Assumptions & Open Questions

1. **Vasopressor source**: Flowsheet rows with Event_Grouper="Vasopressor" and Value in {Yes, No, Administered, Stopped}?
2. **Validity window**: Same as configured `lookback_period` for the feature?
3. **Multi-source handling**: If med admin AND flowsheet both indicate vasopressor, do both contribute to flag decision?
4. **Evidence format**: Minimal (`_last_set_ts` + count) or detailed (full Event_Name list)?

---

**Status**: Design complete, ready for implementation.  
**Owner**: Project owner to implement per the nine-step plan.  
**Reviewers**: AI assistant to provide code review and test validation.
