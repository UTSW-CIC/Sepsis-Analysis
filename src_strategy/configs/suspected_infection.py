from enum import Enum
from typing import List

from pydantic import BaseModel, Field, model_validator

from .dataconfig import DataConfig


class SuspectedInfectionCriterionName(str, Enum):
    ANTIBIOTIC_CULTURE = "antibiotic_culture"
    LACTATE_CULTURE = "lactate_culture"
    CODE_SEPSIS = "code_sepsis"
    FLOWSHEET = "flowsheet"


class AntibioticBloodCultureConfig(BaseModel):
    # antibiotic_type_prefix: str = "IV Antibiotics"
    antibiotic_grouper: List[str] = Field(
        default_factory=lambda: [
            "Antibiotics",
            "IV Antibiotics",
            "IV Antibiotics - First",
            "IV Antibiotics - Confirmed Infection",
            "IV Antibiotics - Single",
            "IV Antibiotics - Last",
            "Sepsis Antibiotics Ordered Event",
        ]
    )
    antibiotic_excluded_type_prefixes: List[str] = Field(
        default_factory=lambda: ["Perioperative Antibiotics"]
    )
    antibiotic_administration_type: str = "Medication Administration"
    antibiotic_order_type: str = "Medication Order"

    culture_before_antibiotic_minutes: int = 72 * 60
    culture_after_antibiotic_minutes: int = 24 * 60

    antibiotic_datetime_col: str = "iv_dt"
    administration_datetime_col: str = "admin_dt"
    antibiotic_time_source_col: str = "infect_dt_source"
    blood_culture_datetime_col: str = "culture_dt"
    long_value: str = "IV+Culture"


class LactateBloodCultureConfig(BaseModel):
    lactate_grouper_val: str = "Lactate"
    lactate_order_type: str = "Procedure Order"
    lactate_order_grouper_val: str = "Lab"
    lactate_order_event_names: List[str] = Field(
        default_factory=lambda: [
            "LACTATE (LACTIC ACID) SERUM",
            "LACTATE (LACTIC ACID) POC ABL",
            "LACTATE (LACTIC ACID) POC ISTAT",
        ]
    )
    lactate_result_type: str = "Lab Results"

    tolerance_minutes: int = 6 * 60
    minimum_culture_orders: int = Field(default=2, ge=2)

    lactate_datetime_col: str = "lactate_dt"
    lactate_result_datetime_col: str = "lactate_result_dt"
    lactate_result_value_col: str = "lactate_result_value"
    blood_culture_datetime_col: str = "culture_dt"
    long_value: str = "LACTATE+CULTURE"


class CodeSepsisConfig(BaseModel):
    grouper_val: str = "Code Sepsis Page"
    datetime_col: str = "first_ev_time_codesepsis"
    long_value: str = "CODE_SEPSIS_ORDER"


class SuspectedInfectionFlowsheetConfig(BaseModel):
    grouper_val: str = "Suspected Infection"
    qualifying_value: str = "Yes"
    datetime_col: str = "first_ev_time_flowsheet"
    long_value: str = "FLOWSHEET_SUSPECTED_INFECTION"


class SuspectedInfectionConfig(DataConfig):
    blood_culture_groupers: List[str] = Field(
        default_factory=lambda: [
            "Blood Culture Order",
            "Blood Culture Results",
            "Other Body Fluid Culture Order",
            "Other Body Fluid Culture Orders",
            "Sepsis Body Fluid Culture Order",
            "Sepsis Body Fluid Culture Orders",
        ]
    )
    blood_culture_order_type: str = "Procedure Order"
    blood_culture_result_type: str = "Lab Results"
    culture_result_datetime_col: str = "culture_result_dt"
    culture_result_status_col: str = "culture_result_status"
    culture_negative_event_names: List[str] = Field(
        default_factory=lambda: ["CULTURE"]
    )
    culture_negative_value_pattern: str = (
        r"(?i)(^\s*NEGATIVE\s*$|\bNO GROWTH\b|\bNO .+ ISOLATED\b)"
    )
    culture_positive_value_pattern: str = (
        r"(?i)(\bPOSITIVE\b|^\s*DETECTED\s*$)"
    )
    culture_positive_event_name_pattern: str = (
        r"(?i)(CULTURE|GRAM ST|BCID|GENE|PCR|SMEAR)"
    )
    culture_contaminant_value_pattern: str = r"(?i)\bCONTAMIN(?:ANT|ATION|ATED)\b"
    antibiotic_blood_culture_config: AntibioticBloodCultureConfig = Field(
        default_factory=AntibioticBloodCultureConfig
    )
    lactate_culture_config: LactateBloodCultureConfig = Field(
        default_factory=LactateBloodCultureConfig
    )
    code_sepsis_config: CodeSepsisConfig = Field(
        default_factory=CodeSepsisConfig
    )
    suspected_infection_flowsheet_config: SuspectedInfectionFlowsheetConfig = Field(
        default_factory=SuspectedInfectionFlowsheetConfig
    )

    selected: List[SuspectedInfectionCriterionName] = Field(
        default_factory=lambda: list(SuspectedInfectionCriterionName)
    )

    variable_name_col: str = "criterion"
    value_name_dt_col: str = "infect_dt"
    value_type_col: str = "suspicion_infection_type"
    infection_episode_id_col: str = "infection_episode_id"
    criterion_met_datetime_col: str = "criterion_met_dt"
    evidence_datetime_col: str = "evidence_dt"

    @model_validator(mode="after")
    def validate_suspected_infection_config(self) -> "SuspectedInfectionConfig":
        if len(self.selected) != len(set(self.selected)):
            raise ValueError("selected suspected-infection criteria must be unique")
        if not self.selected:
            raise ValueError(
                "at least one suspected-infection criterion must be selected"
            )
        if not self.blood_culture_groupers:
            raise ValueError("blood_culture_groupers must not be empty")
        if len(self.blood_culture_groupers) != len(
            set(self.blood_culture_groupers)
        ):
            raise ValueError("blood_culture_groupers must be unique")
        if not self.culture_negative_event_names:
            raise ValueError("culture_negative_event_names must not be empty")

        antibiotic = self.antibiotic_blood_culture_config
        if not antibiotic.antibiotic_grouper:
            raise ValueError("antibiotic_grouper must not be empty")
        if antibiotic.culture_before_antibiotic_minutes < 0:
            raise ValueError(
                "culture_before_antibiotic_minutes must be non-negative"
            )
        if antibiotic.culture_after_antibiotic_minutes < 0:
            raise ValueError(
                "culture_after_antibiotic_minutes must be non-negative"
            )

        lactate = self.lactate_culture_config
        if not lactate.lactate_order_event_names:
            raise ValueError("lactate_order_event_names must not be empty")
        if lactate.tolerance_minutes < 0:
            raise ValueError("tolerance_minutes must be non-negative")
        return self

    @property
    def long_frame_columns(self) -> List[str]:
        return [
            self.encounter_col,
            self.infection_episode_id_col,
            self.variable_name_col,
            self.value_name_dt_col,
            self.criterion_met_datetime_col,
            self.evidence_datetime_col,
            self.value_type_col,
            self.antibiotic_blood_culture_config.administration_datetime_col,
            self.antibiotic_blood_culture_config.antibiotic_time_source_col,
            self.culture_result_datetime_col,
            self.culture_result_status_col,
            self.lactate_culture_config.lactate_result_datetime_col,
            self.lactate_culture_config.lactate_result_value_col,
        ]

    @property
    def dt_columns(self) -> List[str]:
        return [
            self.value_name_dt_col,
            self.criterion_met_datetime_col,
            self.evidence_datetime_col,
            self.antibiotic_blood_culture_config.antibiotic_datetime_col,
            self.antibiotic_blood_culture_config.administration_datetime_col,
            self.antibiotic_blood_culture_config.blood_culture_datetime_col,
            self.lactate_culture_config.lactate_datetime_col,
            self.lactate_culture_config.lactate_result_datetime_col,
            self.lactate_culture_config.blood_culture_datetime_col,
            self.code_sepsis_config.datetime_col,
            self.suspected_infection_flowsheet_config.datetime_col,
            self.culture_result_datetime_col,
        ]


suspected_infection_config = SuspectedInfectionConfig()
