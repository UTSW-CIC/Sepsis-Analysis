from enum import Enum
from typing import List

from pydantic import Field, model_validator

from .aggregator import FeatureColumn
from .dataconfig import DataConfig


class SIRSCriterionName(str, Enum):
    TEMPERATURE = "temperature"
    HEART_RATE = "heart_rate"
    RESPIRATORY_RATE = "respiratory_rate"
    WBC = "wbc"


class SIRSConfig(DataConfig):
    """Configuration for SIRS criteria applied to aggregated features."""

    temp_feature_col: FeatureColumn = FeatureColumn.LAST_TEMP_8H
    hr_feature_col: FeatureColumn = FeatureColumn.LAST_PULSE_8H
    resp_feature_col: FeatureColumn = FeatureColumn.LAST_RESP_8H
    wbc_feature_col: FeatureColumn = FeatureColumn.LAST_WBC_12H

    temp_flag_col: str = "Temp_Abnormal_Flag"
    hr_flag_col: str = "HR_High_Flag"
    resp_flag_col: str = "Resp_Rate_High_Flag"
    wbc_flag_col: str = "WBC_Abnormal_Flag"

    temp_lower_threshold: float = 96.8
    temp_upper_threshold: float = 100.4
    hr_upper_threshold: float = 90.0
    resp_upper_threshold: float = 20.0
    wbc_lower_threshold: float = 4.0
    wbc_upper_threshold: float = 12.0

    selected: List[SIRSCriterionName] = Field(
        default_factory=lambda: list(SIRSCriterionName)
    )
    sirs_score_col: str = "sirs_score"

    @model_validator(mode="after")
    def validate_sirs_config(self) -> "SIRSConfig":
        if len(self.selected) != len(set(self.selected)):
            raise ValueError("selected SIRS criteria must be unique")
        if not self.selected:
            raise ValueError("at least one SIRS criterion must be selected")
        if self.temp_lower_threshold >= self.temp_upper_threshold:
            raise ValueError(
                "temp_lower_threshold must be below temp_upper_threshold"
            )
        if self.wbc_lower_threshold >= self.wbc_upper_threshold:
            raise ValueError(
                "wbc_lower_threshold must be below wbc_upper_threshold"
            )
        return self

    @property
    def flag_cols(self) -> List[str]:
        flag_by_criterion = {
            SIRSCriterionName.TEMPERATURE: self.temp_flag_col,
            SIRSCriterionName.HEART_RATE: self.hr_flag_col,
            SIRSCriterionName.RESPIRATORY_RATE: self.resp_flag_col,
            SIRSCriterionName.WBC: self.wbc_flag_col,
        }
        return [flag_by_criterion[name] for name in self.selected]


# Compatibility name for callers that already distinguish post-aggregation SIRS.
SIRSPostAggConfig = SIRSConfig

sirs_config = SIRSConfig()
sirs_postagg_config = sirs_config
