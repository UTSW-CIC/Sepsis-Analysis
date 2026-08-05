from abc import ABC, abstractmethod
from typing import Any, Literal

import polars as pl


class Criterion(ABC):
    """Strategy contract for one clinical criterion."""

    role: Literal["positive", "termination"] = "positive"

    def __init__(self, config: Any):
        self.config = config

    @property
    def enabled(self) -> bool:
        return getattr(self.config, "enabled", True)

    @property
    @abstractmethod
    def flag_col(self) -> str:
        """Name of the evidence flag emitted by this criterion."""

    def prepare(self, df: pl.DataFrame) -> pl.DataFrame:
        return df

    def expressions(self, available: set[str]) -> list[pl.Expr]:
        return []
