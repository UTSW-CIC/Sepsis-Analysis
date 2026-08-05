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
    antibiotic_type_prefix: str = "IV Antibiotics"
    antibiotic_excluded_type_prefixes: List[str] = Field(
        default_factory=lambda: ["Perioperative Antibiotics"]
    )
    blood_culture_grouper_val: str = "Blood Culture Order"

    culture_before_antibiotic_minutes: int = 72 * 60
    culture_after_antibiotic_minutes: int = 24 * 60

    antibiotic_datetime_col: str = "iv_dt"
    blood_culture_datetime_col: str = "culture_dt"
    long_value: str = "IV+Culture"


class LactateBloodCultureConfig(BaseModel):
    lactate_grouper_val: str = "Lactate"
    blood_culture_grouper_val: str = "Blood Culture Order"

    tolerance_minutes: int = 6 * 60
    minimum_culture_orders: int = Field(default=2, ge=2)

    lactate_datetime_col: str = "lactate_dt"
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

    @model_validator(mode="after")
    def validate_suspected_infection_config(self) -> "SuspectedInfectionConfig":
        if len(self.selected) != len(set(self.selected)):
            raise ValueError("selected suspected-infection criteria must be unique")
        if not self.selected:
            raise ValueError(
                "at least one suspected-infection criterion must be selected"
            )

        antibiotic = self.antibiotic_blood_culture_config
        if not antibiotic.antibiotic_type_prefix:
            raise ValueError("antibiotic_type_prefix must not be empty")
        if antibiotic.culture_before_antibiotic_minutes < 0:
            raise ValueError(
                "culture_before_antibiotic_minutes must be non-negative"
            )
        if antibiotic.culture_after_antibiotic_minutes < 0:
            raise ValueError(
                "culture_after_antibiotic_minutes must be non-negative"
            )

        lactate = self.lactate_culture_config
        if lactate.tolerance_minutes < 0:
            raise ValueError("tolerance_minutes must be non-negative")
        return self

    @property
    def long_frame_columns(self) -> List[str]:
        return [
            self.encounter_col,
            self.variable_name_col,
            self.value_name_dt_col,
            self.value_type_col,
        ]

    @property
    def dt_columns(self) -> List[str]:
        return [
            self.antibiotic_blood_culture_config.antibiotic_datetime_col,
            self.antibiotic_blood_culture_config.blood_culture_datetime_col,
            self.lactate_culture_config.lactate_datetime_col,
            self.lactate_culture_config.blood_culture_datetime_col,
            self.code_sepsis_config.datetime_col,
            self.suspected_infection_flowsheet_config.datetime_col,
        ]


suspected_infection_config = SuspectedInfectionConfig()
