# Clinical Feature Pipeline — Session Summary

## Project Overview

A Python pipeline that processes transactional EHR data to compute SIRS scores, rolling
vital/lab features, and organ dysfunction flags. The input is a long-format events table
(one row per clinical event per patient encounter), and the output is a wide feature matrix
aligned to a common timeline of (encounter, timestamp) pairs.

---

## Architectural Overview

### Folder Structure

```
project/
    data/
        raw_data_phase_2_v2/        # input — folder name becomes the experiment ID
        output/
            raw_data_phase_2_v2/    # output path is auto-derived from input folder name
    logs/
        pipeline.log                # INFO and above
        errors.log                  # ERROR and above
    src/
        config.py                   # all Pydantic config classes
        main.py                     # entry point — wires everything, sets up logger once
        features/
            event_aggregator.py     # loops over FeatureConfig, calls rolling_agg per metric
            rolling_agg.py          # single DuckDB rolling window join + SBP extraction
        sirs/
            sirs_calculator.py      # computes SIRS flags and score per encounter
        organ_dysfunction/
            organ_dysfunction.py    # computes organ dysfunction flags — NEXT TO IMPLEMENT
        utils/
            logger.py               # setup_root_logger() + get_logger()
```

### Data Flow

```
df_all (transactional, one row per event)
    │
    ├──► SIRSCalculator.calculate()
    │         └── aggregates to one row per encounter
    │
    ├──► EventAggregator.aggregate()
    │         ├── builds reference table (unique encounter + timestamp pairs)
    │         ├── loops over FeatureConfig.features
    │         └── returns reference + one column per rolling metric
    │
    └──► OrganDysfunction.calculate()       ← NEXT TO IMPLEMENT
              ├── joins df_agg + df_baseline once in __init__
              ├── one private method per organ system
              └── returns df with per-system flags + organ_dysfunction summary flag
```

---

## Key Files

### `src/config.py`

The config layer has five distinct classes. Their relationships matter:

- `SIRSConfig` **inherits** from `DataConfig` (is-a relationship — it is a more specific DataConfig)
- `FeatureConfig` **contains** a list of `RollingMetric` objects (has-a relationship)
- `OrganDysfunctionConfig` **contains** one config object per organ system
- `DataInputOutputConfig` auto-derives `output_path` from `data_path` via `@model_validator`

```python
class DataConfig(BaseModel):
    encounter_col: str = "EncounterEpicCsn"
    event_dt_col: str = "Event_DateTime"
    event_name_col: str = "Event_Name"
    grouper_col: str = "Event_Grouper"
    val_col: str = "NumericValue"


class SIRSConfig(DataConfig):           # inherits all DataConfig fields
    temp_grouper_val: str = "Temperature"
    hr_grouper_val: str = "Pulse"
    resp_grouper_val: str = "Respirations"
    wbc_grouper_val: str = "WBC"
    temp_flag_col: str = "Temp_Abnormal_Flag"
    hr_flag_col: str = "HR_High_Flag"
    resp_flag_col: str = "Resp_Rate_High_Flag"
    wbc_flag_col: str = "WBC_Abnormal_Flag"
    temp_lower_threshold: float = 96.8
    temp_upper_threshold: float = 100.4
    hr_lower_threshold: float = 90.0
    resp_lower_threshold: float = 20.0
    wbc_lower_threshold: float = 4.0
    wbc_upper_threshold: float = 12.0

    @property
    def selected_cols(self) -> list[str]:
        return [self.encounter_col, self.event_dt_col, self.event_name_col]

    @property
    def flag_cols(self) -> list[str]:
        return [self.temp_flag_col, self.hr_flag_col,
                self.resp_flag_col, self.wbc_flag_col]


class RollingMetric(BaseModel):
    event_grouper: str
    alias: str
    agg: Literal["max", "min", "mean", "sum"]
    lookback_h: float       # float to support 0.25 (15 minutes)


class FeatureConfig(BaseModel):
    features: list[RollingMetric] = [
        RollingMetric(event_grouper="Temperature",                  alias="max_temp_24h",            agg="max", lookback_h=24),
        RollingMetric(event_grouper="Temperature",                  alias="min_temp_24h",            agg="min", lookback_h=24),
        RollingMetric(event_grouper="Pulse",                        alias="max_pulse_24h",           agg="max", lookback_h=24),
        RollingMetric(event_grouper="Respirations",                 alias="max_resp_24h",            agg="max", lookback_h=24),
        RollingMetric(event_grouper="WBC",                          alias="max_wbc_24h",             agg="max", lookback_h=24),
        RollingMetric(event_grouper="WBC",                          alias="min_wbc_24h",             agg="min", lookback_h=24),
        RollingMetric(event_grouper="Creatinine",                   alias="max_creatinine_24h",      agg="max", lookback_h=24),
        RollingMetric(event_grouper="eGFR",                         alias="max_egfr_24h",            agg="max", lookback_h=24),
        RollingMetric(event_grouper="Bilirubin",                    alias="max_bilirubin_24h",       agg="max", lookback_h=24),
        RollingMetric(event_grouper="Lactate",                      alias="max_lactate_24h",         agg="max", lookback_h=24),
        RollingMetric(event_grouper="Platelets",                    alias="min_platelets_24h",       agg="min", lookback_h=24),
        RollingMetric(event_grouper="INR",                          alias="max_inr_24h",             agg="max", lookback_h=24),
        RollingMetric(event_grouper="APTT",                         alias="max_aptt_24h",            agg="max", lookback_h=24),
        RollingMetric(event_grouper="Glascow Coma Score",           alias="min_gcs_24h",             agg="min", lookback_h=24),
        RollingMetric(event_grouper="Vasopressin",                  alias="max_vasopressin_dose",    agg="max", lookback_h=24),
        RollingMetric(event_grouper="Phenylephrine",                alias="max_phenylephrine_dose",  agg="max", lookback_h=24),
        RollingMetric(event_grouper="Norepinephrine",               alias="max_norepinephrine_dose", agg="max", lookback_h=24),
        RollingMetric(event_grouper="Epinephrine",                  alias="max_epinephrine_dose",    agg="max", lookback_h=24),
        RollingMetric(event_grouper="Arterial Blood Pressure Mean", alias="max_map_15m",             agg="max", lookback_h=0.25),
        RollingMetric(event_grouper="Systolic Blood Pressure",      alias="max_sbp_15m",             agg="max", lookback_h=0.25),
    ]


# Organ dysfunction — one config class per organ system
class CardiovascularConfig(BaseModel):
    sbp_col: str = "max_sbp_15m"
    map_col: str = "max_map_15m"
    avg_sbp_col: str = "avg_sbp_24h"
    sbp_threshold: float = 90.0
    map_threshold: float = 65.0
    sbp_delta_threshold: float = 40.0

class RenalConfig(BaseModel):
    creatinine_col: str = "max_creatinine_24h"
    egfr_col: str = "max_egfr_24h"
    baseline_creatinine_col: str = "baseline_creatinine"
    baseline_egfr_col: str = "baseline_egfr"
    creatinine_threshold: float = 2.0
    egfr_divisor: float = 2.0
    creatinine_multiplier: float = 2.0

class HepaticConfig(BaseModel):
    bilirubin_col: str = "max_bilirubin_24h"
    baseline_bilirubin_col: str = "baseline_bilirubin"
    bilirubin_threshold: float = 2.0
    bilirubin_multiplier: float = 2.0

class CoagulationConfig(BaseModel):
    platelets_col: str = "min_platelets_24h"
    inr_col: str = "max_inr_24h"
    aptt_col: str = "max_aptt_24h"
    baseline_platelets_col: str = "baseline_platelets"
    platelets_threshold: float = 100.0
    inr_threshold: float = 1.5
    aptt_threshold: float = 60.0
    platelets_divisor: float = 2.0

class NeurologicalConfig(BaseModel):
    gcs_col: str = "min_gcs_24h"
    gcs_threshold: float = 15.0

class PulmonaryConfig(BaseModel):
    vent_col: str = "vent_status_flag"

class OrganDysfunctionConfig(BaseModel):
    cardiovascular: CardiovascularConfig = CardiovascularConfig()
    renal: RenalConfig = RenalConfig()
    hepatic: HepaticConfig = HepaticConfig()
    coagulation: CoagulationConfig = CoagulationConfig()
    neurological: NeurologicalConfig = NeurologicalConfig()
    pulmonary: PulmonaryConfig = PulmonaryConfig()


class DataInputOutputConfig(BaseModel):
    data_path: str = Field(...)
    output_path: str = Field("")
    logger_dir: str = Field("./logs")

    @model_validator(mode="after")
    def set_output_path_and_create_dirs(self) -> "DataInputOutputConfig":
        if not self.output_path:
            phase_experiment_id = Path(self.data_path).name
            self.output_path = str(Path("./data/output") / phase_experiment_id)
        Path(self.output_path).mkdir(parents=True, exist_ok=True)
        return self
```

### `src/utils/logger.py`

Two functions only. `setup_root_logger` is called once in `main.py`. Every other module
calls `get_logger(__name__)` with no arguments.

```python
def setup_root_logger(log_dir: str = "./logs") -> logging.Logger:
    # configures root logger with pipeline.log (INFO+) and errors.log (ERROR+)
    ...

def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
```

### `src/features/rolling_agg.py`

The core DuckDB pattern. Critical to get right — wrong join direction causes data leakage.

```python
def rolling_agg(
    reference: pl.DataFrame,   # unique (EncounterEpicCsn, Event_DateTime) — the LEFT table
    events: pl.DataFrame,      # pre-filtered, must have: EncounterEpicCsn, evt_dt, evt_val
    agg_col_name: str,
    agg_func: str = "max",
    lookback_period: float | timedelta = 24.0,  # float = hours
    encounter_col: str = "EncounterEpicCsn",
) -> pl.DataFrame:
```

The SQL pattern (must not change):
```sql
LEFT JOIN events
    ON reference.EncounterEpicCsn = events.EncounterEpicCsn
    AND events.evt_dt < reference.Event_DateTime         -- strictly before, no leakage
    AND events.evt_dt >= reference.Event_DateTime - INTERVAL '{interval_str}'
```

`"Systolic Blood Pressure"` is not a real `Event_Grouper` value — it is parsed from
`"Blood Pressure"` events using `extract_systolic_bp()`, which splits the `"120/80"` string
and returns `(EncounterEpicCsn, evt_dt, evt_val)`.

---

## Design Decisions

### 1. Reference Table as the Join Backbone

`df_all` has multiple rows per timestamp (one per event type). Rolling joins must be driven
by a **reference table of unique (encounter, timestamp) pairs**, not by `df_all` directly.
Rolling over `df_all` directly would produce one result row per event type per timestamp,
making it impossible to sum flags across systems on a single row.

The reference table is built once before the feature loop and passed into `rolling_agg` —
never rebuilt inside the function.

### 2. No Forward Filling Before Rolling

Forward filling temperature (or any sparse signal) before the rolling window fabricates
measurements at timestamps where none existed. This inflates flags and leaks information.
Sparsity is handled honestly: if no measurement falls in the lookback window, the result
is `null`. Downstream consumers decide how to handle nulls.

### 3. SIRS Score is Per-Encounter, Not Per-Row

`df_all` is transactional — a temperature row and a WBC row for the same patient are never
on the same row. Summing flags row-by-row would cap the score at 1 (or 2 if two event types
share an exact timestamp). The correct approach is to aggregate each flag to encounter level
with `max()` first, then sum across flag columns.

### 4. Organ Dysfunction Joins Baseline Once in `__init__`

Several dysfunction criteria are relative to baseline (creatinine 2x, bilirubin 2x, etc.).
`df_baseline` (one row per encounter) is joined onto `df_agg` once in `__init__`, making
both rolling aggregates and baseline values available to all private methods via `self.df`.
This avoids repeating the join inside each method.

### 5. Config Inheritance vs Composition

`SIRSConfig` **inherits** from `DataConfig` because it is a more specific version of it —
anywhere a `DataConfig` is expected, a `SIRSConfig` can be substituted. `FeatureConfig`
**contains** a list of `RollingMetric` objects because it is not a DataConfig — it has a
different concern entirely. Mixing inheritance and composition here would be wrong.

### 6. Responsibility Boundaries

| Responsibility | Owner |
|---|---|
| Column name definitions | `DataConfig` |
| Output path derivation + folder creation | `DataInputOutputConfig` via `@model_validator` |
| Log folder creation | `setup_root_logger` in `logger.py` |
| Logger configuration (once) | `main.py` via `setup_root_logger` |
| Logger access (per module) | Each module via `get_logger(__name__)` |
| SBP parsing from "120/80" format | `extract_systolic_bp()` in `rolling_agg.py` |
| Rolling window SQL | `rolling_agg()` |
| Feature loop + routing | `EventAggregator` |

---
## Next Step

Implement `OrganDysfunction` private methods. The pattern for each method is:
1. Read relevant columns from `self.df` (which already has baseline joined)
2. Compute atomic flags using `pl.when().then().otherwise()`
3. Compute composite flag as OR of atomic flags within the system
4. Return a dataframe with `(EncounterEpicCsn, Event_DateTime, *flag_cols)`

The `calculate()` method joins all system results and computes the final `organ_dysfunction`
flag as OR across all composite flags.