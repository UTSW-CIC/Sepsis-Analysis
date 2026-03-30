import polars as pl

from src.config import PulmonaryConfig

"""

Pulmonary Dysfunction Criteria:
    1. Pulmonary Dysfunction:
       	Last vent change event = "Vent on Documentation" (patient currently on mechanical ventilation)
"""


class PulmonaryDysfunctionCalculator:
    def __init__(self, df_agg: pl.DataFrame, pulmonary_config: PulmonaryConfig):
        self.df_agg = df_agg
        self.pulmonary_config = pulmonary_config

    def calculate_pulmonary_dysfunction_flag(self) -> pl.DataFrame:
        return self.df_agg.with_columns(
            (pl.col(self.pulmonary_config.vent_col) == self.pulmonary_config.vent_on_status).cast(pl.Int64).alias(self.pulmonary_config.flag_col)
        )