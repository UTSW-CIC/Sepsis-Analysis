from pydantic import BaseModel, Field
from .dataconfig import DataConfig
from typing import List

class VitalImputer(BaseModel):
    type_val: str = Field(default="Flowsheet")
    lookback_window_hours: int = Field(default=8)
    grouper_val: str= Field(default="")

class TemperatureImputer(VitalImputer):
    grouper_val: str = Field(default='Temperature')

class Pulse(VitalImputer):
    grouper_val: str = Field(default='Pulse')

class Respiration(VitalImputer):
    grouper_val: str = Field(default='Respirations')

class BloodPressure(VitalImputer):
    grouper_val: str = Field(default='Blood Pressure')

class VitalsImputerList(BaseModel):
    vitals_imputers: List[VitalImputer] = Field(
        default_factory=lambda: [
            TemperatureImputer(),
            Respiration(),
            Pulse(),
            BloodPressure(),
        ]
    )

class ImputerConfig(DataConfig):
    allow_backward_filling: bool = Field(default=False, description="Used to allow imputing data from future reading")
    vitals_imputers: VitalsImputerList = VitalsImputerList()


imputer_config = ImputerConfig()