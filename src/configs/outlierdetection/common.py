from pydantic import BaseModel, Field, model_validator
from typing import Dict
from ..dataconfig import DataConfig  

# Used for layer1 (Physiological bound)
class BoundConfig(BaseModel):
    lower_bound: float = Field(default=0.0)
    upper_bound: float = Field(default=1.0)

    @model_validator(mode="after")
    def validate_bounds(self):
        if self.lower_bound >= self.upper_bound:
            raise ValueError(
                f"lower_bound ({self.lower_bound}) must be < "
                f"upper_bound ({self.upper_bound})."
            )
        return self

# Used for layer2 (Velocity Bound)
class RateOfChangeConfig(BaseModel):
    max_velocity_per_hour: float
    max_absolute_step: float
    validity_window_hours: float

    @model_validator(mode='after')
    def validate_params(self) -> "RateOfChangeConfig":
        if self.max_velocity_per_hour <= 0:
            raise ValueError("max_velocity_per_hour must be > 0")
        if self.max_absolute_step <= 0:
            raise ValueError("max_absolute_step must be > 0")
        if self.validity_window_hours <= 0:
            raise ValueError("validity_window_hours must be > 0")
        return self


# Used for layer1 (Physiological bound)
class ThresholdingConfig(DataConfig):
    """Generic threshold-based outlier detection config.
    
    Can be used directly for ad-hoc thresholding or subclassed
    for domain-specific use cases with required signals and defaults.
    """
    thresholds: Dict[str, BoundConfig] = Field(default_factory=dict)

# Used for layer2 (Velocity Bound)
class VelocityStepConfig(DataConfig):
    thresholds: Dict[str, RateOfChangeConfig] = Field(default_factory=dict)




