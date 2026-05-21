from pydantic import BaseModel, Field, model_validator
from .common import ThresholdingConfig, BoundConfig
from typing import ClassVar

class Layer1Config(ThresholdingConfig):
    REQUIRED_SIGNALS:ClassVar[set] = {"Pulse", "Blood Pressure", "Respirations", "Temperature"}

    @model_validator(mode="after")
    def validate_signals(self) -> "Layer1Config":
        missing = self.REQUIRED_SIGNALS - set(self.thresholds.keys())
        if missing:
            raise ValueError(
                f"Layer1Config requires the following signals "
                f"that are not selected in ThresholdingConfig: {missing}"
            )
        return self
    
    @classmethod
    def with_defaults(cls, **overrides) -> "Layer1Config":
        defaults = {
            "Pulse": BoundConfig(upper_bound=250, lower_bound=20),
            "Blood Pressure": BoundConfig(upper_bound=300, lower_bound=40),
            "Respirations": BoundConfig(upper_bound=60, lower_bound=4),
            "Temperature": BoundConfig(upper_bound=113, lower_bound=77), # In Fahrenheit
        }
        defaults.update(overrides)
        return cls(thresholds=defaults)

    # pulse: BoundConfig = Field(default_factory=lambda: BoundConfig(upper_bound=250, lower_bound=20))
    # bp: BoundConfig = Field(default_factory=lambda: BoundConfig(upper_bound=300, lower_bound=40))
    # respiration: BoundConfig = Field(default_factory=lambda: BoundConfig(upper_bound=60, lower_bound=4))
    # temperature: BoundConfig = Field(default_factory=lambda: BoundConfig(upper_bound=113, lower_bound=77)) # In Fahrenheit

physiological_bounds_config = Layer1Config.with_defaults(
    **{
        "Pulse": BoundConfig(upper_bound=250, lower_bound=20),
        "Blood Pressure": BoundConfig(upper_bound=300, lower_bound=40),
        "Respirations": BoundConfig(upper_bound=60, lower_bound=4),
        "Temperature": BoundConfig(upper_bound=113, lower_bound=77),
    }
)                                                
x = 0
