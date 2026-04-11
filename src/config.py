from pydantic import  BaseModel, Field, model_validator
from typing import Literal, List
from enum import Enum
from pathlib import Path

#==============================================================================================================================
# Input/Output Configurations
#==============================================================================================================================
class InputFileNames(BaseModel):
    ENCOUNTER_BASELINE_SCORES: str = "Encounters - Mar 2025 - Feb 2026 - 3.31.26.csv"
    FLOWSHEETS: str = "Flowsheet Events Feb 2025 - Mar 2026 - 3.31.26.csv"
    LABS: str = "Lab Results - 3.9.26.csv"
    MEDS: str = "Med Admin - 3.9.26.csv"
    PROCEDURES: str = "Procedure Orders - 3.9.26.csv"
    DIAGNOSIS: str = "Diagnoses - 3.9.26.csv"

class DataInputOutputConfig(BaseModel):
    data_path: str = Field(..., description="Path to the data directory")
    output_path: str = Field("", description="Path to the output directory")
    logger_dir: str = Field("./logs", description="Directory to write logs to")
    input_file_names: InputFileNames = InputFileNames()

    @model_validator(mode="after")
    def set_output_path(self) -> "DataInputOutputConfig":
        if not self.output_path:
            phase_experiment_id = Path(self.data_path).name
            parent_dir = Path(self.data_path).parent
            # self.output_path = f"./data/output/{phase_experiment_id}"
            self.output_path = f"{str(parent_dir)}/output/{phase_experiment_id}"
        Path(self.output_path).mkdir(parents=True, exist_ok=True)
        return self

    @model_validator(mode="after")
    def ensure_files_exist(self) -> "DataInputOutputConfig":
        for filename in self.input_file_names.model_dump().values():
            file_path = Path(self.data_path) / filename
            if not file_path.is_file():
                raise FileNotFoundError(f"Required input file '{filename}' not found in '{self.data_path}'")
        return self


#==============================================================================================================================
# General Data Configurations
#==============================================================================================================================
class DataConfig(BaseModel):
    encounter_col: str = "EncounterEpicCsn"
    event_dt_col: str = "Event_DateTime"
    event_name_col: str = "Event_Name"
    grouper_col: str = "Event_Grouper"
    val_col: str = "NumericValue"
    
#==============================================================================================================================
# SIRS Calculator Configurations
#==============================================================================================================================
class SIRSConfig(DataConfig):
    # Grouper values for each SIRS criterion
    temp_grouper_val: str = "Temperature"
    hr_grouper_val: str = "Pulse"
    resp_grouper_val: str = "Respirations"
    wbc_grouper_val: str = "WBC"
    
    # Flag column names
    temp_flag_col: str = "Temp_Abnormal_Flag"
    hr_flag_col: str = "HR_High_Flag"
    resp_flag_col: str = "Resp_Rate_High_Flag"
    wbc_flag_col: str = "WBC_Abnormal_Flag"
    
    # Thresholds for abnormal flags
    temp_lower_threshold: float=96.8
    temp_upper_threshold: float=100.4
    hr_lower_threshold: float=90
    resp_lower_threshold: float=20
    wbc_lower_threshold: float=4
    wbc_upper_threshold: float=12
    
    @property
    def selected_cols(self) -> List[str]:
        return [self.encounter_col, self.event_dt_col, self.event_name_col, self.val_col]

    @property
    def flag_cols(self) -> List[str]:
        return [self.temp_flag_col, self.hr_flag_col, self.resp_flag_col, self.wbc_flag_col]
    
#==============================================================================================================================
# Labs and vitals config for feature aggregation
#==============================================================================================================================
class FeatureColumn(str, Enum):
    # Temperature
    MAX_TEMP_24H            = "max_temp_24h"
    MIN_TEMP_24H            = "min_temp_24h"

    # Pulse
    MAX_PULSE_24H           = "max_pulse_24h"

    # Respirations
    MAX_RESP_24H            = "max_resp_24h"

    # Blood Pressure
    MAX_SBP_15M             = "max_sbp_15m"
    MAX_MAP_15M             = "max_map_15m"

    # WBC
    MAX_WBC_24H             = "max_wbc_24h"
    MIN_WBC_24H             = "min_wbc_24h"

    # Renal
    MAX_CREATININE_24H      = "max_creatinine_24h"
    MAX_EGFR_24H            = "max_egfr_24h"

    # Hepatic
    MAX_BILIRUBIN_24H       = "max_bilirubin_24h"

    # Metabolic
    MAX_LACTATE_24H         = "max_lactate_24h"

    # Coagulation
    MIN_PLATELETS_24H       = "min_platelets_24h"
    MAX_INR_24H             = "max_inr_24h"
    MAX_APTT_24H            = "max_aptt_24h"

    # Neurological
    MIN_GCS_24H             = "min_gcs_24h"

    # Vasopressors
    MAX_VASOPRESSIN_24H     = "max_vasopressin_24h"
    MAX_PHENYLEPHRINE_24H   = "max_phenylephrine_24h"
    MAX_NOREPINEPHRINE_24H  = "max_norepinephrine_24h"
    MAX_EPINEPHRINE_24H     = "max_epinephrine_24h"

    # Pulmonary
    VENT_STATUS_FLAG        = "vent_status_flag"
    O2_DELIVERY_FLAG        = "max_o2_delivery_flag"


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
    FeatureColumn.MAX_TEMP_24H: FeatureDefinition(
        event_grouper="Temperature",
        alias=FeatureColumn.MAX_TEMP_24H,
        agg="max",
        lookback_period=24*60
    ),
    FeatureColumn.MIN_TEMP_24H: FeatureDefinition(
        event_grouper="Temperature",
        alias=FeatureColumn.MIN_TEMP_24H,
        agg="min",
        lookback_period=24*60
    ),

    # Pulse
    FeatureColumn.MAX_PULSE_24H: FeatureDefinition(
        event_grouper="Pulse",
        alias=FeatureColumn.MAX_PULSE_24H,
        agg="max",
        lookback_period=24*60
    ),

    # Respirations
    FeatureColumn.MAX_RESP_24H: FeatureDefinition(
        event_grouper="Respirations",
        alias=FeatureColumn.MAX_RESP_24H,
        agg="max",
        lookback_period=24*60
    ),

    # Blood Pressure
    FeatureColumn.MAX_SBP_15M: FeatureDefinition(
        event_grouper="Systolic Blood Pressure",
        alias=FeatureColumn.MAX_SBP_15M,
        agg="max",
        lookback_period=15
    ),

    FeatureColumn.MAX_MAP_15M: FeatureDefinition(
        event_grouper="Arterial Blood Pressure Mean",
        alias=FeatureColumn.MAX_MAP_15M,
        agg="max",
        lookback_period=15
    ),

    # WBC
    FeatureColumn.MAX_WBC_24H: FeatureDefinition(
        event_grouper="WBC",
        alias=FeatureColumn.MAX_WBC_24H,
        agg="max",
        lookback_period=24*60
    ),
    FeatureColumn.MIN_WBC_24H: FeatureDefinition(
        event_grouper="WBC",
        alias=FeatureColumn.MIN_WBC_24H,
        agg="min",
        lookback_period=24*60
    ),

    # Renal
    FeatureColumn.MAX_CREATININE_24H: FeatureDefinition(
        event_grouper="Creatinine",
        alias=FeatureColumn.MAX_CREATININE_24H,
        agg="max",
        lookback_period=24*60
    ),
    FeatureColumn.MAX_EGFR_24H: FeatureDefinition(
        event_grouper="eGFR",
        alias=FeatureColumn.MAX_EGFR_24H,
        agg="max",
        lookback_period=24*60
    ),

    # Hepatic
    FeatureColumn.MAX_BILIRUBIN_24H: FeatureDefinition(
        event_grouper="Bilirubin",
        alias=FeatureColumn.MAX_BILIRUBIN_24H,
        agg="max",
        lookback_period=24*60
    ),

    # Metabolic
    FeatureColumn.MAX_LACTATE_24H: FeatureDefinition(
        event_grouper="Lactate",
        alias=FeatureColumn.MAX_LACTATE_24H,
        agg="max",
        lookback_period=24*60
    ),

    # Coagulation
    FeatureColumn.MIN_PLATELETS_24H: FeatureDefinition(
        event_grouper="Platelets",
        alias=FeatureColumn.MIN_PLATELETS_24H,
        agg="min",
        lookback_period=24*60
    ),
    FeatureColumn.MAX_INR_24H: FeatureDefinition(
        event_grouper="INR",
        alias=FeatureColumn.MAX_INR_24H,
        agg="max",
        lookback_period=24*60
    ),
    FeatureColumn.MAX_APTT_24H: FeatureDefinition(
        event_grouper="APTT",
        alias=FeatureColumn.MAX_APTT_24H,
        agg="max",
        lookback_period=24*60
    ),

    # Neurological
    FeatureColumn.MIN_GCS_24H: FeatureDefinition(
        event_grouper="Glasgow Coma Score",
        alias=FeatureColumn.MIN_GCS_24H,
        agg="min",
        lookback_period=24*60
    ),

    # Vasopressors
    # TODO:Question: There are two Event_Names: VASOPRESSIN 20 UNIT/ML, VASOPRESSIN 0.2 UNIT/ML
    # Numeric values vary between 0.0 up to 40
    FeatureColumn.MAX_VASOPRESSIN_24H: FeatureDefinition(
        event_grouper="Vasopressin",
        alias=FeatureColumn.MAX_VASOPRESSIN_24H,
        agg="max",
        lookback_period=24*60
    ),
    # TODO: Question: There are multiple Event_Names for Phenylephrine: PHENYLEPHRINE 10 MG/ML, PHENYLEPHRINE 0.1 MG/ML, PHENYLEPHRINE 1 MG/ML, PHENYLEPHRINE 20 MG/ML, PHENYLEPHRINE 2 MG/ML, PHENYLEPHRINE 5 MG/ML
    FeatureColumn.MAX_PHENYLEPHRINE_24H: FeatureDefinition(
        event_grouper="Phenylephrine",
        alias=FeatureColumn.MAX_PHENYLEPHRINE_24H,
        agg="max",
        lookback_period=24*60
    ),
    
    FeatureColumn.MAX_NOREPINEPHRINE_24H: FeatureDefinition(
        event_grouper="Norepinephrine",
        alias=FeatureColumn.MAX_NOREPINEPHRINE_24H,
        agg="max",
        lookback_period=24*60
    ),
    FeatureColumn.MAX_EPINEPHRINE_24H: FeatureDefinition(
        event_grouper="Epinephrine",
        alias=FeatureColumn.MAX_EPINEPHRINE_24H,
        agg="max",
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
    evt_dt_col: str = "evt_dt"
    # alias: str = "Last_Vent_Status"
    vent_alias: str = FeatureColumn.VENT_STATUS_FLAG
    o2_alias: str = FeatureColumn.O2_DELIVERY_FLAG

# class O2DeliveryConfig(DataConfig):
#     o2_val_col: str = "Value"
#     evt_dt_col: str = "Event_DateTime"
#     alias: str = "max_o2_delivery_24h"

#==============================================================================================================================
# Organ Dysfunction Configurations
#==============================================================================================================================
class CardiovascularConfig(BaseModel):
    lactate_col: FeatureColumn      = FeatureColumn.MAX_LACTATE_24H
    lactate_threshold: float            = 2
    flag_col: str = "cardiovascular_failure_flag"

class RenalConfig(BaseModel):
    creatinine_col: FeatureColumn   = FeatureColumn.MAX_CREATININE_24H
    egfr_col: FeatureColumn         = FeatureColumn.MAX_EGFR_24H
    baseline_creatinine_col: str    = BaselineColumn.BASELINE_CREATININE
    baseline_egfr_col: str          = BaselineColumn.BASELINE_eGFR
    creatinine_threshold: float     = 2.0
    egfr_multiplier: float             = 0.5
    creatinine_multiplier: float    = 2.0
    flag_col: str = "renal_failure_flag"

class HepaticConfig(BaseModel):
    bilirubin_col: FeatureColumn    = FeatureColumn.MAX_BILIRUBIN_24H
    baseline_bilirubin_col: BaselineColumn     = BaselineColumn.BASELINE_BILIRUBIN
    bilirubin_threshold: float      = 2.0
    bilirubin_multiplier: float     = 2.0
    flag_col: str = "hepatic_failure_flag"

class CoagulationConfig(BaseModel):
    platelets_col: FeatureColumn    = FeatureColumn.MIN_PLATELETS_24H
    inr_col: FeatureColumn          = FeatureColumn.MAX_INR_24H
    aptt_col: FeatureColumn         = FeatureColumn.MAX_APTT_24H
    baseline_platelets_col: BaselineColumn     = BaselineColumn.BASELINE_PLATELETS
    platelets_threshold: float      = 100.0
    inr_threshold: float            = 1.5
    aptt_threshold: float           = 60.0
    platelets_multiplier: float        = 0.5
    # Flags
    inr_flag: str = "inr_criteria_flag"
    aptt_flag: str = "aptt_criteria_flag"
    platelets50_flag: str = "platelets50_criteria_flag"
    platelets100_flag: str = "platelets100_criteria_flag"

    # Final flag
    flag_col: str = "coagulation_failure_flag"

class NeurologicalConfig(BaseModel):
    gcs_col: FeatureColumn          = FeatureColumn.MIN_GCS_24H
    gcs_threshold: float            = 15.0
    flag_col: str = "neurological_failure_flag"

class PulmonaryConfig(BaseModel):
    vent_col: FeatureColumn         = FeatureColumn.VENT_STATUS_FLAG
    vent_on_status: str = "Vent on Documentation"
    vent_off_status: str = "Vent off Documentation"
    flag_col: str = "pulmonary_failure_flag"

class BaselineConfig(BaseModel):
    baseline_creatinine_col: str = "Baseline_Creatinine"
    baseline_egfr_col: str = "Baseline_eGFR"
    baseline_bilirubin_col: str = "Baseline_Bilirubin"
    baseline_platelets_col: str = "Baseline_Platelets"
    # baseline_inr_col: str = "Baseline_INR"
    baseline_SBP_col: str ="Baseline_SBP"
    baseline_resp_rate_col: str = "Baseline_RespiratoryRate"
    baseline_pulse_col: str = "Baseline_PulseRate"
    baseline_wbc_col: str = "Baseline_WBC"

    @property
    def columns(self) -> List[str]:
        return [
            self.baseline_creatinine_col,
            self.baseline_egfr_col,
            self.baseline_bilirubin_col,
            self.baseline_platelets_col,
            # self.baseline_inr_col,
            self.baseline_SBP_col,
            self.baseline_resp_rate_col,
            self.baseline_pulse_col,
            self.baseline_wbc_col
        ]

class OrganDysfunctionConfig(DataConfig):
    cardiovascular: CardiovascularConfig    = CardiovascularConfig()
    renal: RenalConfig                      = RenalConfig()
    hepatic: HepaticConfig                  = HepaticConfig()
    coagulation: CoagulationConfig          = CoagulationConfig()
    neurological: NeurologicalConfig        = NeurologicalConfig()
    pulmonary: PulmonaryConfig              = PulmonaryConfig()
    baseline: BaselineConfig                = BaselineConfig()
    flag_col: str = "organ_dysfunction_total"

#==============================================================================================================================
# Pipeline Configurations that merge FeatureConfig and OrganDysfunctionConfig to demonstrate the dependency
#==============================================================================================================================
class PipelineConfig(BaseModel):
    features: FeatureConfig             = FeatureConfig()
    organ: OrganDysfunctionConfig       = OrganDysfunctionConfig()

    @model_validator(mode='after')
    def validate_contract(self) -> "PipelineConfig":
        produced = set(self.features.selected)

        required = {
            # Cardiovascular
            self.organ.cardiovascular.lactate_col,

            # Renal
            self.organ.renal.creatinine_col,
            self.organ.renal.egfr_col,
            # Hepatic
            self.organ.hepatic.bilirubin_col,
            # Coagulation
            self.organ.coagulation.platelets_col,
            self.organ.coagulation.inr_col,
            self.organ.coagulation.aptt_col,
            # Neurological
            self.organ.neurological.gcs_col,
        }

        missing = required - produced
        if missing:
            raise ValueError(
                f"OrganDysfunctionConfig requires the following features "
                f"that are not selected in FeatureConfig: {missing}"
            )
        return self


#==============================================================================================================================
# Sepstic Shock Configurations
#==============================================================================================================================
class SBP90Criteria(BaseModel):
    sbp_col: FeatureColumn = FeatureColumn.MAX_SBP_15M
    baseline_sbp_col: str = BaselineColumn.BASELINE_SBP
    sbp_threshold: float = 90.0
    flag_col: str = "sbp90_flag"

class SBPDelta40Criteria(BaseModel):
    sbp_col: FeatureColumn = FeatureColumn.MAX_SBP_15M
    baseline_sbp_col: str = BaselineColumn.BASELINE_SBP
    sbp_delta_threshold: float = 40.0
    flag_col: str = "sbpdelta40_flag"

class MAP65Criteria(BaseModel):
    map_col: FeatureColumn = FeatureColumn.MAX_MAP_15M
    map_threshold: float = 65.0
    flag_col: str = "map65_flag"

class Lactate4Criteria(BaseModel):
    lactate_col: FeatureColumn = FeatureColumn.MAX_LACTATE_24H
    lactate_threshold: float = 4.0
    flag_col: str = "lactate4_flag"

class VasopressorCriteria(BaseModel):
    vasopressor_cols: List[FeatureColumn] = Field(
        default_factory=lambda: [
            FeatureColumn.MAX_VASOPRESSIN_24H,
            FeatureColumn.MAX_PHENYLEPHRINE_24H,
            FeatureColumn.MAX_NOREPINEPHRINE_24H,
            FeatureColumn.MAX_EPINEPHRINE_24H
        ]
    )
    flag_col: str = "vasopressor_flag"

class SepticShockConfig(DataConfig):
    sbp90_criteria: SBP90Criteria = SBP90Criteria()
    sbpdelta40_criteria: SBPDelta40Criteria = SBPDelta40Criteria()
    map65_criteria: MAP65Criteria = MAP65Criteria()
    lactate4_criteria: Lactate4Criteria = Lactate4Criteria()
    vasopressor_criteria: VasopressorCriteria = VasopressorCriteria()

    flag_col: str = "septic_shock_flag"

septicshock_config = SepticShockConfig()
    

#==============================================================================================================================
# Instance Initializations
#==============================================================================================================================
input_output_config = DataInputOutputConfig(
    data_path="../Sepsis-data/data/raw_data_phase2_v2"
)
data_config = DataConfig()
sirs_config = SIRSConfig()


agg_config = AggregatorConfig()
vent_config = VentConfig()

feature_config = FeatureConfig()

organdysfunction_config = OrganDysfunctionConfig()

pipeline_config = PipelineConfig()

