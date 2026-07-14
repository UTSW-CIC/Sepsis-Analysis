from .dataconfig import DataConfig
from pydantic import BaseModel, Field
from typing import List


class Sepsis1Config(DataConfig):
    sirs_score_threshold: int = Field(default=2, description="Threshold for SIRS score to indicate sepsis.")
    sirs_col: str = Field(default="sirs_score", description="Column name for SIRS score in the dataframe.")
    


class Sepsis2Config(DataConfig):
    pass


class Sepsis3Config(DataConfig):
    pass