# Flag Aggregation, SIRS, and Suspected Infection Implementation — 2026-08-04

## Summary

Implemented three foundational pieces of the `src_strategy` redesign:

1. DuckDB-backed temporal flag aggregation, including presence-only/null-valued events, optional validity windows, explicit termination events, and evidence timestamps.
2. SIRS calculation using the Strategy + Registry pattern and shared Pipeline/Reducer primitives, producing the approved raw 0–4 score.
3. Suspected-infection detection using criterion strategies and a registry, preserving the long-frame output used by downstream project logic while updating the antibiotic matching rule and enforcing the two-culture lactate criterion.

The older `src/` implementation remains available as a parity reference. The new implementations are isolated, configuration-driven, and covered by focused regression tests.

## Shared Strategy/Pipeline Foundation

Added reusable clinical-criterion composition primitives under `src_strategy/pipeline/`:

- `Criterion` defines the strategy contract and criterion role.
- `Pipeline` runs enabled criteria, preserves the input dataframe, creates criterion columns, and delegates composition to a reducer.
- `SumReducer` sums positive criterion flags into a configured score while treating null flags as zero for classification.
- Registry mappings in each clinical module translate configured criterion names into concrete strategy classes.

The abstractions were introduced because SIRS already has multiple independently selectable criteria with one stable reduction rule. They are intentionally small and do not attempt to generalize every future sepsis module.

## DuckDB Flag Aggregation

### Problem Addressed

Some EHR events represent state by their presence rather than by a populated value. A row such as:

```text
Event_Grouper = "Some Flag Grouper"
Value = null
```

is still a valid state-setting event. The previous numeric-only aggregation path removed null values and could not represent a state that persisted until an explicit stop event.

### Configuration Changes

`FeatureDefinition` now supports:

- `agg_type`: `"numeric"` or `"flag"`
- optional `lookback_period` for flag features
- optional `flag_true_values`
- optional `flag_false_values`
- `persist_until_termination`
- optional `termination_event_grouper`

Validation decisions:

- Numeric features still require a lookback period.
- Flag features may omit the lookback period.
- Negative lookback periods are rejected.
- The same configured value cannot be both true and false.
- `persist_until_termination=False` remains unsupported because its semantics have not been approved.

### Flag Event Semantics

- A null-valued event from the main flag grouper sets the flag to `1`.
- Explicit configured true and false values remain supported.
- If true values are configured:
  - null or an explicit true value sets the flag;
  - an explicit false value clears it;
  - other values do not change state.
- If no true values are configured:
  - any main-grouper event not explicitly false sets the flag;
  - this supports presence-only source data.
- A row from `termination_event_grouper` clears the flag even when its value is null.

### Temporal Semantics

- With a lookback period, the window is backward-looking and inclusive at the exact validity boundary.
- When the true evidence leaves the lookback window, the flag becomes `0` unless a newer true event exists.
- Without a lookback period, the flag persists across all later encounter backbone rows until:
  - an explicit false value occurs;
  - a configured termination-grouper event occurs; or
  - the encounter ends.
- State is determined from the most recent true and false timestamps.
- A remaining same-instant true/false tie resolves to false defensively because true requires `last_true_ts > last_false_ts`. Same-instant collision resolution is still expected upstream.

### Provenance

Flag aggregation emits:

```text
<alias>_last_set_ts
```

This is the timestamp of the most recent true-setting source event that supports the rolling state. It is not the timestamp when the output cell was calculated.

Numeric aggregation was also extended to emit:

```text
<alias>_source_ts
```

For `min`, `max`, `first`, and `last`, this identifies the selected source row. Min/max ties select the most recent source row. Mean/sum/count additionally emit `<alias>_contributor_count`, while their source timestamp records the latest contributing event. The DuckDB helper supports `first` and `count`; the current `FeatureDefinition.agg` registry choices remain `max`, `min`, `last`, `sum`, and `mean`.

### Routing and Registry Status

- `Aggregator._aggregate_by_duckdb()` now routes numeric and flag features separately and returns the completed backbone.
- Flag preparation preserves null-valued source rows; numeric preparation still removes null analytic values.
- Vasopressin, phenylephrine, norepinephrine, and epinephrine are currently registered as flag features with 24-hour lookbacks.
- Their current registry entries do not configure explicit true/false values or separate termination groupers, so any event presence sets the flag and the state expires after 24 hours.
- Medication administration/unit normalization and clinically approved stop semantics still require validation before relying on these registry entries for septic-shock classification.

## SIRS Strategy Module

### Architecture

Added:

- `SIRSCriterionName` enum
- validated `SIRSConfig`
- `SIRS_CRITERION_REGISTRY`
- `TemperatureCriterion`
- `HeartRateCriterion`
- `RespiratoryRateCriterion`
- `WBCCriterion`
- `SIRSPipeline`
- `build_sirs_pipeline()` factory

The compatibility name `SIRSPostAggConfig` now aliases the new `SIRSConfig`.

### Input Features

SIRS uses the temporally aggregated most-recent features:

- `last_temp_8h`
- `last_pulse_8h`
- `last_resp_8h`
- `last_wbc_12h`

The source timestamps added to numeric aggregation remain in the dataframe for audit and subsequent interval reconstruction.

### Clinical Thresholds

The implemented comparisons are strict and match the approved definitions:

- Temperature: `< 96.8°F` or `> 100.4°F`
- Pulse: `> 90 bpm`
- Respiratory rate: `> 20/min`
- WBC: `< 4` or `> 12 ×10³/µL`

Values exactly equal to 96.8, 100.4, 90, 20, 4, or 12 are not abnormal.

### Score and Missing Evidence

- Each abnormal criterion contributes `1`.
- `sirs_score` is the raw sum and ranges from `0` through `4`.
- The module does not create a Boolean `sirs_flag`; downstream logic decides whether `sirs_score >= 2`.
- A missing feature column or null feature value produces a null criterion flag. For parity with the old output, measured normal values also produce a null criterion flag; the preserved feature and source-timestamp columns provide the distinction between measured-normal and missing evidence.
- The reducer fills null criterion flags with zero only when calculating the score, consistent with the current project rule that insufficient evidence resolves to no sepsis.
- Input rows, keys, and provenance columns are preserved.

### Configurability

- Criteria are selected through `SIRSConfig.selected`.
- Duplicate selections and an empty selection are rejected.
- Temperature and WBC lower/upper threshold order is validated.
- Registry selection controls both emitted criterion columns and score composition.

### Integration Status

`main_strategy.py` currently loads `df_aggregated.parquet`, runs the new SIRS pipeline, and saves `df_sirs.parquet`. The broader script still relies on staged saved artifacts and is not yet an end-to-end sepsis/billing classifier.

## Suspected Infection Strategy Module

### Architecture

Added:

- `SuspectedInfectionCriterionName` enum
- validated nested criterion configurations
- `SUSPECTED_INFECTION_CRITERION_REGISTRY`
- `AntibioticCultureCriterion`
- `LactateCultureCriterion`
- `CodeSepsisCriterion`
- `SuspectedInfectionFlowsheetCriterion`
- `SuspectedInfectionPipeline`
- `build_suspected_infection_pipeline()` factory
- `detect_infection_longframe()` compatibility method

The output preserves the established four-column long format:

```text
EncounterEpicCsn
criterion
infect_dt
suspicion_infection_type
```

### IV Antibiotic Plus Blood Culture

- Antibiotic matching now uses the `"IV Antibiotics"` type prefix rather than exact equality.
- This includes source types such as `IV Antibiotics - Single`, `IV Antibiotics - First`, and other prefixed variants.
- Configured excluded prefixes, currently including `Perioperative Antibiotics`, are removed.
- A culture qualifies from 72 hours before through 24 hours after an administered IV antibiotic.
- Both timing boundaries are inclusive.
- DuckDB forms valid antibiotic/culture pairs and deterministically selects the earliest pair per encounter.
- The long frame emits both the antibiotic and culture evidence timestamps for that pair.

### Lactate Plus Blood Cultures

- A lactate episode qualifies only when at least two distinct culture-order rows occur within six hours before or after the lactate order.
- Both six-hour boundaries are inclusive.
- Exact duplicate culture rows are removed before cardinality is evaluated.
- The earliest qualifying lactate episode per encounter is selected deterministically.
- The long frame emits the lactate timestamp and all matched culture evidence rows for the selected episode.

### Direct Suspected-Infection Signals

- A Code Sepsis Page order emits a qualifying evidence row.
- A Suspected Infection flowsheet event qualifies only when its raw value is `"Yes"`.
- A `"No"` flowsheet value does not qualify.

### Current Reduction Decision

The paired antibiotic/culture and lactate/culture strategies currently retain the earliest qualifying criterion episode per encounter, matching the old implementation's encounter-level reduction. Code Sepsis and flowsheet criteria preserve their qualifying event rows.

This is suitable for current parity, but it does not yet satisfy the intended future requirement to retain every suspected-infection episode/state transition. Adding all-episode output requires an explicit episode identifier and focused parity review.

### Integration Status

`main_strategy.py` contains the current suspected-infection pipeline construction and save path for `df_suspected_infection.parquet`, but that execution block is presently commented while the staged pipeline is being run from saved artifacts.

## Testing Completed

Focused test files:

- `tests/test_aggregator_flag.py`
- `tests/test_aggregator_numeric_provenance.py`
- `tests/test_sirs_strategy.py`
- `tests/test_suspected_infection_strategy.py`

Verified behaviors include:

- presence-only flag configuration;
- preservation of null-valued flag events;
- inclusive validity expiry;
- indefinite persistence without a lookback;
- null-valued termination-grouper events;
- configured true/false values and unrecognized values;
- numeric provenance and most-recent tie resolution;
- SIRS parity with the old post-aggregation calculator;
- strict threshold boundaries;
- missing SIRS evidence and registry selection;
- preservation of SIRS input rows/provenance;
- antibiotic prefix matching and inclusive 72-hour/24-hour boundaries;
- two-culture lactate cardinality and inclusive six-hour boundaries;
- Code Sepsis and flowsheet long-frame output;
- earliest-pair reduction; and
- suspected-infection registry selection.

The project environment does not currently include the `pytest` package. All zero-argument test functions were therefore executed directly in the project environment, and all 25 test functions passed:

```text
test_aggregator_flag.py: 8 passed
test_aggregator_numeric_provenance.py: 7 passed
test_sirs_strategy.py: 5 passed
test_suspected_infection_strategy.py: 5 passed
```

## Implementation Checklist

- [x] Add numeric-versus-flag aggregation configuration.
- [x] Permit null-valued presence events for flags.
- [x] Preserve explicit true and false value support.
- [x] Support optional flag lookback periods.
- [x] Persist flags to encounter end when no lookback or termination exists.
- [x] Support separate null-valued termination groupers.
- [x] Add flag last-set provenance timestamps.
- [x] Add numeric source timestamps and contributor counts.
- [x] Route both aggregation types through the DuckDB aggregator.
- [x] Implement shared Strategy/Pipeline/Reducer primitives.
- [x] Port SIRS criteria and raw 0–4 score.
- [x] Validate SIRS parity and boundary behavior.
- [x] Port suspected-infection criteria to a registry.
- [x] Match IV-antibiotic source variants by prefix.
- [x] Enforce at least two cultures around lactate.
- [x] Preserve the downstream-compatible infection long frame.
- [x] Add current-pipeline composition hooks in `main_strategy.py`.

## Remaining Tasks

- [ ] Install or declare `pytest` in the reproducible project environment and run the focused suite through the normal test runner.
- [ ] Add a full aggregation integration test using registered vasopressor features and representative normalized medication data.
- [ ] Clinically approve medication administration, units, false/stop values, termination groupers, and 24-hour validity semantics.
- [ ] Add focused upstream collision tests for same-instant flag conflicts.
- [ ] Decide whether each vasopressor should expire after 24 hours or persist until a documented termination event.
- [ ] Decide and implement how every suspected-infection episode should be identified and retained rather than keeping only the earliest paired episode.
- [ ] Confirm that distinct culture-order identity is adequately represented by encounter, timestamp, and event name in the source extract.
- [ ] Add golden/parity tests on de-identified representative encounter outputs, not only synthetic frames.
- [ ] Deliberately integrate suspected infection and SIRS into the downstream sepsis severity/classification pipeline.
- [ ] Preserve evidence timestamps through final Sepsis 1/2/3 and POA/NPOA outputs.
- [ ] Resolve the separate incomplete organ-dysfunction/severity configuration imports before end-to-end composition.

## Files Modified or Added

### Aggregation

- `src_strategy/configs/aggregator.py`
- `src_strategy/data_preparation/aggregator.py`
- `tests/test_aggregator_flag.py`
- `tests/test_aggregator_numeric_provenance.py`

### Shared Pipeline

- `src_strategy/pipeline/__init__.py`
- `src_strategy/pipeline/criterion.py`
- `src_strategy/pipeline/pipeline.py`
- `src_strategy/pipeline/reducers.py`

### SIRS

- `src_strategy/configs/sirscalculator.py`
- `src_strategy/events/sirs/__init__.py`
- `src_strategy/events/sirs/criteria.py`
- `src_strategy/events/sirs/pipeline.py`
- `tests/test_sirs_strategy.py`

### Suspected Infection

- `src_strategy/configs/suspected_infection.py`
- `src_strategy/events/suspected_infection/__init__.py`
- `src_strategy/events/suspected_infection/criteria.py`
- `src_strategy/events/suspected_infection/pipeline.py`
- `tests/test_suspected_infection_strategy.py`

### Composition

- `main_strategy.py`
- `AI_logs/2026-08-04-flag-sirs-suspected-infection-implementation.md`

## Assumptions and Open Questions

1. Null-valued flag-grouper rows are valid evidence that the flagged event occurred.
2. An explicit false or termination event clears a flag; same-instant unresolved conflicts favor false.
3. Missing SIRS evidence contributes zero to the score but remains visible as a null criterion flag.
4. The SIRS score is a 0–4 score; `>=2` is applied downstream and is not collapsed inside the SIRS module.
5. The old implementation's earliest-pair reduction remains the current suspected-infection parity target, although future episode retention is required.
6. Culture-order distinctness and medication normalization still need source/clinical confirmation.

---

**Status**: Flag aggregation, SIRS, and suspected-infection strategy modules implemented with focused tests passing; end-to-end clinical classification integration and clinical validation remain pending.  
**Owner**: Project owner to confirm medication semantics, all-episode infection requirements, and validation reference.  
**Reviewer**: AI assistant to review clinical decisions, integration changes, and parity outputs before production use.
