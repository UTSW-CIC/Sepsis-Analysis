from pydantic import BaseModel, Field
from typing import List


from .aggregator import FeatureColumn, BaselineColumn
from .dataconfig import DataConfig

class SBP90Criteria(BaseModel):
    sbp_col: FeatureColumn = FeatureColumn.LAST_SBP_8h
    baseline_sbp_col: str = BaselineColumn.BASELINE_SBP
    sbp_threshold: float = 90.0
    flag_col: str = "sbp90_flag"

class SBPDelta40Criteria(BaseModel):
    sbp_col: FeatureColumn = FeatureColumn.LAST_SBP_8h
    baseline_sbp_col: str = BaselineColumn.BASELINE_SBP
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
    vasopressor_cols: List[FeatureColumn] = Field(
        default_factory=lambda: [
            FeatureColumn.LAST_VASOPRESSIN_24H,
            FeatureColumn.LAST_PHENYLEPHRINE_24H,
            FeatureColumn.LAST_NOREPINEPHRINE_24H,
            FeatureColumn.LAST_EPINEPHRINE_24H
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