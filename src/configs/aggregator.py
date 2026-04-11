from enum import Enum, auto
from typing import List, Literal
from pydantic import BaseModel, Field, model_validator
from .dataconfig import DataConfig


class FeatureColumn(str, Enum):
    def _generate_next_value_(name, start, count, last_values):
        return name.lower()
    
    # Temperature
    LAST_TEMP_8H            = auto()
    # MIN_TEMP_24H            = "min_temp_24h"

    # Pulse
    LAST_PULSE_8H           = auto()

    # Respirations
    LAST_RESP_8H            = auto()

    # Blood Pressure
    LAST_SBP_8h            = auto()
    LAST_MAP_8h             = auto()

    # LASTBC
    LAST_WBC_12H             = auto()
    # LAST_WBC_24H             = "min_wbc_24h"

    # LASTenal
    LAST_CREATININE_12H      = auto()
    LAST_EGFR_12H            = auto()

    # LASTepatic
    LAST_BILIRUBIN_12H       = auto()

    # LASTetabolic
    LAST_LACTATE_6H         = auto()

    # LASToagulation
    LAST_PLATELETS_24H       = auto()
    LAST_INR_12H             = auto()
    LAST_APTT_24H            = auto()

    # LASTeurological
    LAST_GCS_12H             = auto()

    # LASTasopressors
    LAST_VASOPRESSIN_24H     = auto()
    LAST_PHENYLEPHRINE_24H   = auto()
    LAST_NOREPINEPHRINE_24H  = auto()
    LAST_EPINEPHRINE_24H     = auto()

    # Pulmonary
    VENT_STATUS_FLAG        = auto()
    VENT_STATUS_TIME        = auto()    
    O2_DELIVERY_FLAG        = auto()



class BaselineColumn(str, Enum):
    BASELINE_CREATININE     = "Baseline_Creatinine"
    BASELINE_SBP            = "Baseline_SBP"
    BASELINE_RESP_RATE      = "Baseline_RespiratoryRate"
    BASELINE_PULSE_RATE     = "Baseline_PulseRate"
    BASELINE_PLATELETS      = "Baseline_Platelets"
    BASELINE_BILIRUBIN      = "Baseline_Bilirubin"
    BASELINE_eGFR           = "Baseline_eGFR"
    BASELINE_WBC            = "Baseline_WBC"

class FeatureDefinition(BaseModel):
    event_grouper: str
    alias: str
    agg: Literal["max", "min", "last", "sum", "mean"]
    lookback_period: float

FEATURE_REGISTRY: dict[FeatureColumn, FeatureDefinition] = {
    # Temperature
    FeatureColumn.LAST_TEMP_8H: FeatureDefinition(
        event_grouper="Temperature",
        alias=FeatureColumn.LAST_TEMP_8H,
        agg="last",
        lookback_period=8*60
    ),
    # FeatureColumn.MIN_TEMP_24H: FeatureDefinition(
    #     event_grouper="Temperature",
    #     alias=FeatureColumn.MIN_TEMP_24H,
    #     agg="last",
    #     lookback_period=24*60
    # ),

    # Pulse
    FeatureColumn.LAST_PULSE_8H: FeatureDefinition(
        event_grouper="Pulse",
        alias=FeatureColumn.LAST_PULSE_8H,
        agg="last",
        lookback_period=8*60
    ),

    # Respirations
    FeatureColumn.LAST_RESP_8H: FeatureDefinition(
        event_grouper="Respirations",
        alias=FeatureColumn.LAST_RESP_8H,
        agg="last",
        lookback_period=8*60
    ),

    # Blood Pressure
    FeatureColumn.LAST_SBP_8h: FeatureDefinition(
        event_grouper="Systolic Blood Pressure",
        alias=FeatureColumn.LAST_SBP_8h,
        agg="last",
        lookback_period=8*60
    ),

    FeatureColumn.LAST_MAP_8h: FeatureDefinition(
        event_grouper="Arterial Blood Pressure Mean",
        alias=FeatureColumn.LAST_MAP_8h,
        agg="last",
        lookback_period=8*60
    ),

    # WBC
    FeatureColumn.LAST_WBC_12H: FeatureDefinition(
        event_grouper="WBC",
        alias=FeatureColumn.LAST_WBC_12H,
        agg="last",
        lookback_period=12*60
    ),
    # FeatureColumn.MIN_WBC_24H: FeatureDefinition(
    #     event_grouper="WBC",
    #     alias=FeatureColumn.MIN_WBC_24H,
    #     agg="last",
    #     lookback_period=24*60
    # ),

    # Renal
    FeatureColumn.LAST_CREATININE_12H: FeatureDefinition(
        event_grouper="Creatinine",
        alias=FeatureColumn.LAST_CREATININE_12H,
        agg="last",
        lookback_period=12*60
    ),
    FeatureColumn.LAST_EGFR_12H: FeatureDefinition(
        event_grouper="eGFR",
        alias=FeatureColumn.LAST_EGFR_12H,
        agg="last",
        lookback_period=12*60
    ),

    # Hepatic
    FeatureColumn.LAST_BILIRUBIN_12H: FeatureDefinition(
        event_grouper="Bilirubin",
        alias=FeatureColumn.LAST_BILIRUBIN_12H,
        agg="last",
        lookback_period=12*60
    ),

    # Metabolic
    FeatureColumn.LAST_LACTATE_6H: FeatureDefinition(
        event_grouper="Lactate",
        alias=FeatureColumn.LAST_LACTATE_6H,
        agg="last",
        lookback_period=6*60
    ),

    # Coagulation
    FeatureColumn.LAST_PLATELETS_24H: FeatureDefinition(
        event_grouper="Platelets",
        alias=FeatureColumn.LAST_PLATELETS_24H,
        agg="last",
        lookback_period=24*60
    ),
    FeatureColumn.LAST_INR_12H: FeatureDefinition(
        event_grouper="INR",
        alias=FeatureColumn.LAST_INR_12H,
        agg="last",
        lookback_period=12*60
    ),
    FeatureColumn.LAST_APTT_24H: FeatureDefinition(
        event_grouper="APTT",
        alias=FeatureColumn.LAST_APTT_24H,
        agg="last",
        lookback_period=24*60
    ),

    # Neurological
    FeatureColumn.LAST_GCS_12H: FeatureDefinition(
        event_grouper="Glasgow Coma Score",
        alias=FeatureColumn.LAST_GCS_12H,
        agg="last",
        lookback_period=12*60
    ),

    # Vasopressors
    # TODO:Question: There are two Event_Names: VASOPRESSIN 20 UNIT/ML, VASOPRESSIN 0.2 UNIT/ML
    # Numeric values vary between 0.0 up to 40
    FeatureColumn.LAST_VASOPRESSIN_24H: FeatureDefinition(
        event_grouper="Vasopressin",
        alias=FeatureColumn.LAST_VASOPRESSIN_24H,
        agg="last",
        lookback_period=24*60
    ),
    # TODO: Question: There are multiple Event_Names for Phenylephrine: PHENYLEPHRINE 10 MG/ML, PHENYLEPHRINE 0.1 MG/ML, PHENYLEPHRINE 1 MG/ML, PHENYLEPHRINE 20 MG/ML, PHENYLEPHRINE 2 MG/ML, PHENYLEPHRINE 5 MG/ML
    FeatureColumn.LAST_PHENYLEPHRINE_24H: FeatureDefinition(
        event_grouper="Phenylephrine",
        alias=FeatureColumn.LAST_PHENYLEPHRINE_24H,
        agg="last",
        lookback_period=24*60
    ),
    
    FeatureColumn.LAST_NOREPINEPHRINE_24H: FeatureDefinition(
        event_grouper="Norepinephrine",
        alias=FeatureColumn.LAST_NOREPINEPHRINE_24H,
        agg="last",
        lookback_period=24*60
    ),
    FeatureColumn.LAST_EPINEPHRINE_24H: FeatureDefinition(
        event_grouper="Epinephrine",
        alias=FeatureColumn.LAST_EPINEPHRINE_24H,
        agg="last",
        lookback_period=24*60
    ),
}

class FeatureConfig(BaseModel):
    selected: List[FeatureColumn] = Field(
        default_factory=lambda: list(FEATURE_REGISTRY.keys())
    )

    @model_validator(mode='after')
    def validate_selected(self) -> "FeatureConfig":
        missing = [col for col in self.selected if col not in FEATURE_REGISTRY]
        if missing:
            raise ValueError(f"Selected features not found in FEATURE_REGISTRY: {missing}")
        return self

    @property
    def rolling_metrics(self) -> List[FeatureDefinition]:
        return [FEATURE_REGISTRY[col] for col in self.selected]

class BloodPressureConfig(BaseModel):
    bp_grouper_val: str = "Blood Pressure"
    bp_val_col: str = "Value"
    sys_col: str = "sys"

class AggregatorConfig(DataConfig):
    evt_val_col: str = "evt_val"
    evt_dt_col: str = "evt_dt"

    blood_pressure_config: BloodPressureConfig = BloodPressureConfig()

class VentConfig(DataConfig):
    vent_on_status: str = "Vent on Documentation"
    vent_off_status: str = "Vent off Documentation"

    o2_grouper_val: str = "O2 Delivery High-Flow"

    evt_val_col: str = "evt_vent"
    evt_dt_col: str = "evt_dt_vent"

    # o2_evt_val_col: str = "evt_o2"
    # o2_evt_dt_col: str = "evt_dt_o2"
    # alias: str = "Last_Vent_Status"
    vent_alias: str = FeatureColumn.VENT_STATUS_FLAG
    vent_dt_alias: str = FeatureColumn.VENT_STATUS_TIME
    o2_alias: str = FeatureColumn.O2_DELIVERY_FLAG


agg_config = AggregatorConfig()
vent_config = VentConfig()
feature_config = FeatureConfig()