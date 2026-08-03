from pydantic import BaseModel, model_validator
from .dataconfig import DataConfig
from typing import List, Optional
from enum import Enum

class ResolutionStrategy(str, Enum):
    MIN = "min"
    MAX = "max"
    WORST = "worst"

class FeatureResolusionConfig(BaseModel):
    type_col_val: str
    grouper_col_val: List[str]
    val_col: str
    strategy: ResolutionStrategy
    lower_bound: Optional[float] = None
    upper_bound: Optional[float] = None

    @model_validator(mode="after")
    def _bounds_required_for_worst(self):
        if self.strategy == ResolutionStrategy.WORST and\
            (self.lower_bound is None or self.upper_bound is None):
            raise ValueError("lower_bound and upper_bound are required for worst strategy")
        return self


FEATURE_RESOLUTION_REGISTERY: dict[str, FeatureResolusionConfig] = {
    "Pulse": FeatureResolusionConfig(type_col_val="Flowsheet", grouper_col_val=["Pulse"], val_col="NumericValue", strategy=ResolutionStrategy.MAX),
    "Respirations": FeatureResolusionConfig(type_col_val="Flowsheet", grouper_col_val=["Respirations"], val_col="NumericValue", strategy=ResolutionStrategy.MAX),
    "Temperature": FeatureResolusionConfig(type_col_val="Flowsheet", grouper_col_val=["Temperature"], val_col="NumericValue", strategy=ResolutionStrategy.WORST, lower_bound=96.8, upper_bound=100.4),
    "WBC": FeatureResolusionConfig(type_col_val="Lab Results", grouper_col_val=["WBC"], val_col="NumericValue", strategy=ResolutionStrategy.WORST, lower_bound=4, upper_bound=12),
    "sys": FeatureResolusionConfig(type_col_val="Flowsheet", grouper_col_val=["Blood Pressure"], val_col="sys", strategy=ResolutionStrategy.MIN),
    "Glasgow Coma Score": FeatureResolusionConfig(type_col_val="Flowsheet", grouper_col_val=["Glasgow Coma Score"], val_col="NumericValue", strategy=ResolutionStrategy.MIN),   
    "Platelets": FeatureResolusionConfig(type_col_val="Lab Results", grouper_col_val=["Platelets"], val_col="NumericValue", strategy=ResolutionStrategy.MIN),
    "INR": FeatureResolusionConfig(type_col_val="Lab Results", grouper_col_val=["INR"], val_col="NumericValue", strategy=ResolutionStrategy.MAX),
    "Bilirubin": FeatureResolusionConfig(type_col_val="Lab Results", grouper_col_val=["Bilirubin"], val_col="NumericValue", strategy=ResolutionStrategy.MAX),
    "eGFR": FeatureResolusionConfig(type_col_val="Lab Results", grouper_col_val=["eGFR"], val_col="NumericValue", strategy=ResolutionStrategy.MIN),
    # "map": FeatureResolusionConfig(type_col_val="Flowsheet", grouper_col_val=["Arterial Blood Pressure Mean", "Blood Pressure"], val_col="map", strategy=ResolutionStrategy.MIN),
    "map": FeatureResolusionConfig(type_col_val="Flowsheet", grouper_col_val=["Blood Pressure"], val_col="map", strategy=ResolutionStrategy.MIN),
    "Lactate": FeatureResolusionConfig(type_col_val="Lab Results", grouper_col_val=["Lactate"], val_col="NumericValue", strategy=ResolutionStrategy.MAX),
    "PAO2": FeatureResolusionConfig(type_col_val="Lab Results", grouper_col_val=["PAO2"], val_col="NumericValue", strategy=ResolutionStrategy.MIN),
    "Creatinine": FeatureResolusionConfig(type_col_val="Lab Results", grouper_col_val=["Creatinine"], val_col="NumericValue", strategy=ResolutionStrategy.MAX),

}

class CollisionConfig(DataConfig):
    features_resolutions_dict: dict[str, FeatureResolusionConfig] = FEATURE_RESOLUTION_REGISTERY


collision_config = CollisionConfig()
    
