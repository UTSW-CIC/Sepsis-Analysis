import polars as pl

from src.config import RenalConfig

"""

Renal Dysfunction Criteria:
    1. Creatinine 2x Baseline:
        Most recent creatinine > (baseline creatinine × 2)
    2. Creatinine > 2:
        Most recent creatinine > 2.0 mg/dL and no baseline creatinine data available
    3. eGFR Decline by 50%:
        Most recent eGFR < (baseline eGFR / 2)
"""


class RenalDysfunctionCalculator:
    def __init__(self, df_agg: pl.DataFrame, renal_config: RenalConfig):
        self.df_agg = df_agg
        self.renal_config = renal_config

    def calculate_renal_dysfunction_flag(self) -> pl.DataFrame:
        return self.df_agg.with_columns(
            pl.when(
            # Highest creatinine in 24 hours > 2
            (
                (pl.col(self.renal_config.creatinine_col) > self.renal_config.creatinine_threshold)&
                (pl.col(self.renal_config.baseline_creatinine_col).is_null()) 
            )|
            # Baseline creatinine * 2 < highest creatinine in 24 hours
            (
                (pl.col(self.renal_config.baseline_creatinine_col).is_not_null())&
                ((self.renal_config.creatinine_multiplier*pl.col(self.renal_config.baseline_creatinine_col)) < pl.col(self.renal_config.creatinine_col))
            )|
            (
                (pl.col(self.renal_config.baseline_egfr_col).is_not_null())&
                ( (self.renal_config.egfr_multiplier*pl.col(self.renal_config.baseline_egfr_col)) > pl.col(self.renal_config.egfr_col) )
            )
        ).then(pl.lit(1)).otherwise(pl.lit(0)).alias(self.renal_config.flag_col) )
