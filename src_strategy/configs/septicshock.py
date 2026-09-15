from enum import Enum
from typing import List

from pydantic import BaseModel, Field, model_validator

from .aggregator import FeatureColumn, BaselineColumn
from .dataconfig import DataConfig


class SepticShockCriterionName(str, Enum):
    SBP_90 = "sbp_90"
    SBP_DELTA_40 = "sbp_delta_40"
    MAP_65 = "map_65"
    LACTATE_4 = "lactate_4"
    VASOPRESSOR = "vasopressor"


class SBP90Criteria(BaseModel):
    sbp_col: FeatureColumn = FeatureColumn.LAST_SBP_8h
    sbp_threshold: float = 90.0
    flag_col: str = "sbp90_flag"


class SBPDelta40Criteria(BaseModel):
    sbp_col: FeatureColumn = FeatureColumn.LAST_SBP_8h
    baseline_sbp_col: BaselineColumn = BaselineColumn.BASELINE_SBP
    sbp_delta_threshold: float = 40.0
    flag_col: str = "sbpdelta40_flag"


class MAP65Criteria(BaseModel):
    map_col: FeatureColumn = FeatureColumn.LAST_MAP_8h
    map_threshold: float = 65.0
    flag_col: str = "map65_flag"


class Lactate4Criteria(BaseModel):
    lactate_col: FeatureColumn = FeatureColumn.LAST_LACTATE_6H
    lactate_threshold: float = 4.0
    flag_col: str = "lactate4_flag"


class VasopressorCriteria(BaseModel):
    event_type_value: str = "Medication Administration"
    grouper_values: List[str] = Field(
        default_factory=lambda: [
            "Vasopressin",
            "Phenylephrine",
            "Norepinephrine",
            "Epinephrine",
        ]
    )
    dose_col: str = "NumericValue"
    qualifying_dose_flag_col: str = "vasopressor_qualifying_dose_flag"
    administered_flag_col: str = "vasopressor_administered_flag"
    evidence_event_count_col: str = "vasopressor_evidence_event_count"
    qualifying_dose_count_col: str = "vasopressor_qualifying_dose_count"
    flag_col: str = "vasopressor_flag"


class SepticShockConfig(DataConfig):
    sbp90_criteria: SBP90Criteria = SBP90Criteria()
    sbpdelta40_criteria: SBPDelta40Criteria = SBPDelta40Criteria()
    map65_criteria: MAP65Criteria = MAP65Criteria()
    lactate4_criteria: Lactate4Criteria = Lactate4Criteria()
    vasopressor_criteria: VasopressorCriteria = VasopressorCriteria()
    selected: List[SepticShockCriterionName] = Field(
        default_factory=lambda: list(SepticShockCriterionName)
    )
    baseline_encounter_row_available_col: str = (
        "septic_shock_baseline_encounter_row_available"
    )
    effective_hypotension_flag_col: str = "effective_hypotension_flag"
    flag_col: str = "septic_shock_flag"

    @model_validator(mode="after")
    def validate_selected(self) -> "SepticShockConfig":
        if len(self.selected) != len(set(self.selected)):
            raise ValueError("selected septic-shock criteria must be unique")
        if not self.selected:
            raise ValueError("at least one septic-shock criterion is required")
        if not self.vasopressor_criteria.grouper_values:
            raise ValueError("at least one vasopressor grouper is required")
        if len(self.vasopressor_criteria.grouper_values) != len(
            set(self.vasopressor_criteria.grouper_values)
        ):
            raise ValueError("vasopressor groupers must be unique")
        return self


septicshock_config = SepticShockConfig()
