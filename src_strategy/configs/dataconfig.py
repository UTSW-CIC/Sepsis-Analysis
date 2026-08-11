from pydantic import BaseModel, Field, model_validator, computed_field
from pathlib import Path
from enum import Enum
from .envconfig import env_settings
import polars as pl
from typing import List

#==============================================================================================================================
# Input/Output Configurations
#==============================================================================================================================
# class InputFileNames(BaseModel):
#     # ENCOUNTER_BASELINE_SCORES: str = "Encounters - Mar 2025 - Feb 2026 - 3.31.26.csv"
#     # ENCOUNTER_BASELINE_SCORES: str = "Encounter Table with Baseline Values - Mar 2025 - Feb 2026 - 4.2.26.csv"
#     # ENCOUNTER_BASELINE_SCORES: str = "Encounter Table with Baseline Values - Mar 2025 - Feb 2026 - 4.13.26.csv" 
#     ENCOUNTER_BASELINE_SCORES: str = "Encounter Table with Baseline Values - Mar 2025 - Feb 2026 - 4.13.26 v2.csv" 
#     # FLOWSHEETS: str = "Flowsheet Events Feb 2025 - Mar 2026 - 3.31.26.csv"
#     FLOWSHEETS: str = "Flowsheets - Mar 2025 - Feb 2026 - 4.9.26.csv"
#     # LABS: str = "Lab Results - 3.9.26.csv"
#     LABS: str = "Lab Results - Mar 2025 - Feb 2026 - 4.8.26.csv"
#     # MEDS: str = "Med Admin - 3.9.26.csv"
#     MEDS: str = "Med Admin - Mar 2025 - Feb 2026 - 4.8.26.csv"
#     # PROCEDURES: str = "Procedure Orders - 3.9.26.csv"
#     PROCEDURES: str = "Procedure Orders - Mar 2025 - Feb 2026 - 4.9.26.csv"
#     DIAGNOSIS: str = "Diagnoses - 3.9.26.csv"

class InputFileNames(BaseModel):
    ENCOUNTER_BASELINE_SCORES: str = "Encounter Table with Baseline Values - June 2022 - May 2026 - 6.5.26.csv" 
    # FLOWSHEETS: str = "Flowsheet Events Feb 2025 - Mar 2026 - 3.31.26.csv"
    FLOWSHEETS: str = "Flowsheet Events - 6.5.26.csv"
    # LABS: str = "Lab Results - 3.9.26.csv"
    LABS: str = "Lab Results - 6.5.26.csv"
    # MEDS: str = "Med Admin - 3.9.26.csv"
    MEDS: str = "Med Admin Events - 6.5.26.csv"
    # PROCEDURES: str = "Procedure Orders - 3.9.26.csv"
    PROCEDURES: str = "Procedure Order Events - 6.5.26.csv"
    DIAGNOSIS: str = "Diagnoses - 6.5.26.csv"

class DataConfig(BaseModel):
    encounter_col: str = Field(default="EncounterEpicCsn", description="Column name for encounter identifier")
    event_dt_col: str = Field(default="Event_DateTime", description="Column name for timestamp")
    event_name_col: str = Field(default="Event_Name", description="Column name for name")
    grouper_col: str = Field(default="Event_Grouper", description="Column name for grouper")
    type_col: str = Field(default="Type", description="Column name for events type")
    val_col: str = Field(default="NumericValue", description="Column name for value")
    raw_val_col: str = Field(default="Value", description="Column name for raw value (Numeric and non-numeric values)")
    BASELINE_CREATININE: str     = Field(default="Baseline_Creatinine", description="Baseline Creatinine")
    BASELINE_SBP: str            = Field(default="Baseline_SBP", description="Baseline Systolic Blood Pressure")
    BASELINE_RESP_RATE: str      = Field(default="Baseline_RespiratoryRate", description="Baseline Respiratory Rate")
    BASELINE_PULSE_RATE: str     = Field(default="Baseline_PulseRate", description="Baseline Pulse Rate")
    BASELINE_PLATELETS: str      = Field(default="Baseline_Platelets", description="Baseline Platelets")
    BASELINE_BILIRUBIN: str      = Field(default="Baseline_Bilirubin", description="Baseline Bilirubin")
    BASELINE_eGFR: str           = Field(default="Baseline_eGFR", description="Baseline eGFR")
    BASELINE_WBC: str            = Field(default="Baseline_WBC", description="Baseline WBC")

    @computed_field
    @property
    def unique_subset_with_grouper(self) -> List[str]:
        return [self.encounter_col, self.event_dt_col, self.grouper_col, self.raw_val_col]

    @computed_field
    @property
    def unique_subset_with_type(self) -> List[str]:
        return [self.encounter_col, self.event_dt_col, self.type_col, self.raw_val_col]

    @computed_field
    @property
    def unique_subset_with_eventname(self) -> List[str]:
        return [self.encounter_col, self.event_dt_col, self.event_name_col, self.raw_val_col]

    @computed_field
    @property
    def unique_subset_with_all(self) -> List[str]:
        return [self.encounter_col, self.event_dt_col, self.type_col, self.grouper_col, self.event_name_col, self.raw_val_col]

    @computed_field
    @property
    def base_cols(self) -> List[str]:
        return [self.encounter_col, self.event_dt_col, self.type_col,
                 self.grouper_col, self.event_name_col, self.val_col, self.raw_val_col]


class DataInputOutputConfig(DataConfig):
    data_path: str = Field(..., description="Path to the data directory")
    output_path: str = Field("", description="Path to the output directory")
    meta_output_path: str = Field("", description="Path to the meta output directory that contains configs, thresholds, monitored tables, etc.")
    meta_outlier_path: str = Field("", description="Path to the meta outlier directory that contains outlier tables")
    meta_ingest_path: str = Field("", description="Path to the meta outlier directory that contains outlier tables")
    logger_dir: str = Field("./logs", description="Directory to write logs to")
    input_file_names: InputFileNames = InputFileNames()
    convert_bp_to_sbp: bool = True

    cast_schema: dict = Field(default_factory=lambda: {
        "EncounterEpicCsn": pl.Int64,
        "NumericValue": pl.Float64,
        "Event_DateTime": ("datetime", "%Y-%m-%d %H:%M:%S%.f"),
        "PrimaryMrn": pl.Int64,
        "Death_Flag": pl.Int64,
        "Arrival_Instant": ("datetime", "%Y-%m-%d %H:%M:%S%.f"),
        "FirstAdmissionOrderInstant": ("datetime", "%Y-%m-%d %H:%M:%S%.f"),
        "InpatientAdmissionInstant": ("datetime", "%Y-%m-%d %H:%M:%S%.f"),
        "AdmissionDateValue": ("date", "%Y-%m-%d"),
        "DischargeDateValue": ("date", "%Y-%m-%d"),
        "LengthOfStayInDays": pl.Int64,
        "PatientAgeAtAdmission": pl.Float64,
        "Immunocrompromised_Registry_YN": pl.Int64,
        "CKD_Dialysis_Registry_YN": pl.Int64,
        "Solid_Organs_Transplant_Registry_YN": pl.Int64,
        "Pregnancy_Registry_YN": pl.Int64,

    }, description="Schema for the data")

    @model_validator(mode="after")
    def set_output_path(self) -> "DataInputOutputConfig":
        if not self.output_path:
            phase_experiment_id = Path(self.data_path).name
            parent_dir = Path(self.data_path).parent
            # self.output_path = f"./data/output/{phase_experiment_id}"
            self.output_path = f"{str(parent_dir)}/output/{phase_experiment_id}"
        Path(self.output_path).mkdir(parents=True, exist_ok=True)

        self.meta_output_path = f"{self.output_path}/meta"
        Path(self.meta_output_path).mkdir(parents=True, exist_ok=True)

        self.meta_outlier_path = f"{self.meta_output_path}/outliers"
        Path(self.meta_outlier_path).mkdir(parents=True, exist_ok=True)

        self.meta_ingest_path = f"{self.meta_output_path}/ingest"
        Path(self.meta_ingest_path).mkdir(parents=True, exist_ok=True)
        return self

    @model_validator(mode="after")
    def ensure_files_exist(self) -> "DataInputOutputConfig":
        for filename in self.input_file_names.model_dump().values():
            file_path = Path(self.data_path) / filename
            if not file_path.is_file():
                raise FileNotFoundError(f"Required input file '{filename}' not found in '{self.data_path}'")
        return self


class BloodPressureConfig(DataConfig):
    bp_grouper_val: str = Field(default="Blood Pressure", description="Grouper value for blood pressure") #
    bp_val_col: str = Field(default="Value", description="Column name for value") 
    sys_col: str = Field(default="sys", description="Column name for systolic blood pressure") 
    dia_col: str = Field(default="dia", description="Column name for diastolic blood pressure") 
    map_col: str = Field(default="map", description="Column name for mean arterial pressure")
    map_event_grouper: str = Field(default="Arterial Blood Pressure Mean", description="Grouper value for mean arterial pressure")
    calculate_map: bool = False



class VasopressorsConfig(DataConfig):
    grouper_vals: list[str] = Field(default_factory=lambda: ["Norepinephrine", "Epinephrine", "Vasopressin", "Dopamine", "Phenylephrine", "Dobutamine"],
                                     description="Grouper values for vasopressors")
    flag_col: str = Field(default="NumericValue", description="Column name for vasopressor flag (1 if vasopressor administered, 0 otherwise)")

#==============================================================================================================================
# config instances
#==============================================================================================================================
# input_output_config = DataInputOutputConfig(
#     data_path=f"{env_settings.DATA_ABS_PATH}/data/raw_data_phase2_v2"
# )


input_filenames_v2 = InputFileNames(
    ENCOUNTER_BASELINE_SCORES = "Encounter Table with Baseline Values - Mar 2025 - Feb 2026 - 4.13.26 v2.csv" ,
    FLOWSHEETS = "Flowsheets - Mar 2025 - Feb 2026 - 4.9.26.csv",
    PROCEDURES  = "Procedure Orders - Mar 2025 - Feb 2026 - 4.9.26.csv",
    DIAGNOSIS  = "Diagnoses - 3.9.26.csv",
    MEDS = "Med Admin - Mar 2025 - Feb 2026 - 4.8.26.csv",
    LABS = "Lab Results - Mar 2025 - Feb 2026 - 4.8.26.csv"
)
input_output_config_2 = DataInputOutputConfig(
    data_path=f"{env_settings.DATA_ABS_PATH}/data/raw_data_phase2_v2",
    output_path=f'{env_settings.DATA_ABS_PATH}/data/output_data_phase2_v2_iteration2',
    input_file_names=input_filenames_v2
)


input_filenames_v3 = InputFileNames(
    ENCOUNTER_BASELINE_SCORES = "Encounter Table with Baseline Values - June 2022 - May 2026 - 6.5.26.csv",
    FLOWSHEETS = "flowsheets_bp - 6.8.26.csv", # Created in notebooks/18_eda_datasetv3.ipynb
    LABS = "labs_with_fio2 - 6.9.26.csv", # Created in notebooks/18_eda_datasetv3.ipynb
    MEDS = "Med Admin Events - 6.5.26.csv",
    PROCEDURES = "Procedure Order Events - 6.5.26.csv",
    DIAGNOSIS = "Diagnoses - 6.5.26.csv",
)

input_output_config_3 = DataInputOutputConfig(
    data_path=f"{env_settings.DATA_ABS_PATH}/data/raw_data_phase3",
    output_path=f'{env_settings.DATA_ABS_PATH}/data/output/output_data_phase3',
    input_file_names=input_filenames_v3
)

input_output_config_3_1 = DataInputOutputConfig(
    data_path=f"{env_settings.DATA_ABS_PATH}/data/raw_data_phase3",
    output_path=f'{env_settings.DATA_ABS_PATH}/data/output/output_data_phase3_1',
    input_file_names=input_filenames_v3
)
data_config = DataConfig()

bp_config = BloodPressureConfig()

vasopressors_config = VasopressorsConfig()