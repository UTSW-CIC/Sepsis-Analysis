import polars as pl
from src.config import CardiovascularConfig

"""
Cardiac Dysfunction Criteria:
 1. Lactate > 2	Most recent lactate > 2.0 mmol/L
"""

class CardiovascularDysfunctionCalculator:
    def __init__(self,
                  df_agg: pl.DataFrame, cardiovascular_config: CardiovascularConfig):
        self.df_agg = df_agg
        self.cardiovascular_config = cardiovascular_config

    def calculate_cardiovascular_dysfunction_flag(self) -> pl.DataFrame:
        return self.df_agg.with_columns(
            pl.when(
                pl.col(self.cardiovascular_config.lactate_col) > self.cardiovascular_config.lactate_threshold
            ).then(pl.lit(1)).otherwise(pl.lit(0)).alias(self.cardiovascular_config.flag_col)
        )