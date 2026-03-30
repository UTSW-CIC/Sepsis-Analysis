import polars as pl

from src.config import HepaticConfig

"""

Hepatic Dysfunction Criteria:
    1. Bilirubin 2x Baseline:
    	Most recent bilirubin > 2.0 mg/dL AND Most recent bilirubin > (baseline bilirubin × 2)
    2. Bilirubin > 2:
        Most recent bilirubin > 2.0 mg/dL and no baseline bilirubin data available
"""


class HepaticDysfunctionCalculator:
    def __init__(self,
                  df_agg: pl.DataFrame,
                 hepatic_config: HepaticConfig):
        self.df_agg = df_agg
        self.hepatic_config = hepatic_config

    def calculate_hepatic_dysfunction_flag(self) -> pl.DataFrame:
        return self.df_agg.with_columns(
            pl.when(
                (   pl.col(self.hepatic_config.baseline_bilirubin_col).is_null()&
                    ( pl.col(self.hepatic_config.bilirubin_col) > self.hepatic_config.bilirubin_threshold)
                )|
                (
                    ( pl.col(self.hepatic_config.baseline_bilirubin_col).is_not_null())&
                    ( pl.col(self.hepatic_config.bilirubin_col) > self.hepatic_config.bilirubin_threshold)&
                    ( (pl.col(self.hepatic_config.baseline_bilirubin_col) * self.hepatic_config.bilirubin_multiplier) < pl.col(self.hepatic_config.bilirubin_col))
                )
            ).then(pl.lit(1)).otherwise(pl.lit(0)).alias(self.hepatic_config.flag_col)
        )
