from .dataconfig import DataConfig
from pydantic import Field, BaseModel 


SIRS_EXPIRATION_REGISTERY: dict[str, float] = {
    "Pulse": 8.0,
    "Blood Pressure": 8.0,
    "Respirations": 8.0,
    "Temperature": 8.0,
    "WBC": 12.0,
}



class FillNullsConfig(DataConfig):
    fillna_strategy: str = "forward"  # Strategy to fill nulls, e.g., "forward", "backward", "mean", etc.
    expiration_registery: dict[str, float] = SIRS_EXPIRATION_REGISTERY


sirs_expiration_config = FillNullsConfig()