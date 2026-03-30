import polars as pl

from src.config import NeurologicalConfig

"""

Neurological Dysfunction Criteria:
    1. Neurological Dysfunction:
        Most recent Glasgow Coma Score < 15
"""


class NeurologicalDysfunctionCalculator:
    def __init__(self, df_agg: pl.DataFrame, neurological_config: NeurologicalConfig):
        self.df_agg = df_agg
        self.neurological_config = neurological_config
    
    def calculate_neurological_dysfunction_flag(self) -> pl.DataFrame:
        return self.df_agg.with_columns(
            (pl.col(self.neurological_config.gcs_col) < self.neurological_config.gcs_threshold).cast(pl.Int64).alias(self.neurological_config.flag_col)
        )
        
