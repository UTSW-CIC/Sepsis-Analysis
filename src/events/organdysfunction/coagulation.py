import polars as pl
from src.config import CardiovascularConfig

"""
Coagulation Criteria:
    1. Platelet Drop by 50%:
        Most recent platelets < 100 AND baseline platelets > 100 AND Most recent < (baseline platelets / 2)
    2. Platelets < 100:
        Most recent platelets < 100 and no baseline platelet data available
    3. INR > 1.5:
        Most recent INR > 1.5 and no baseline platelet data available
    4. aPTT > 60:
        Most recent aPTT > 60 seconds and no baseline platelet data available
"""

class CoagulationDysfunctionCalculator:
    def __init__(self,
                  df_agg: pl.DataFrame,
                 coagulation_config: CardiovascularConfig):
        self.df_agg = df_agg
        self.coagulation_config = coagulation_config

    def _calculate_inr_expression(self) -> pl.Expr:
        return pl.when(
                pl.col(self.coagulation_config.inr_col) > self.coagulation_config.inr_threshold
            ).then(pl.lit(1)).otherwise(pl.lit(0)).alias(self.coagulation_config.inr_flag)
        
    
    def _calculate_aptt_expression(self) -> pl.Expr:
        return pl.when(
                pl.col(self.coagulation_config.aptt_col) > self.coagulation_config.aptt_threshold
            ).then(pl.lit(1)).otherwise(pl.lit(0)).alias(self.coagulation_config.aptt_flag)
        
    def _calculate_platelets100_expression(self) -> pl.Expr:
        return pl.when(
                (pl.col(self.coagulation_config.platelets_col) < self.coagulation_config.platelets_threshold) &
                (pl.col(self.coagulation_config.baseline_platelets_col).is_null())
            ).then(pl.lit(1)).otherwise(pl.lit(0)).alias(self.coagulation_config.platelets100_flag)

    def _calculate_platelets50_expression(self) -> pl.Expr:
        return pl.when(
                (pl.col(self.coagulation_config.baseline_platelets_col).is_not_null())&
                (pl.col(self.coagulation_config.baseline_platelets_col) > self.coagulation_config.platelets_threshold) &
                (pl.col(self.coagulation_config.platelets_col) < self.coagulation_config.platelets_threshold) & 
                ((self.coagulation_config.platelets_multiplier*pl.col(self.coagulation_config.baseline_platelets_col))> pl.col(self.coagulation_config.platelets_col))
            ).then(pl.lit(1)).otherwise(pl.lit(0)).alias(self.coagulation_config.platelets50_flag)

    def calculate_coagulation_dysfunction_flag(self) -> pl.DataFrame:
        return self.df_agg.with_columns(
            self._calculate_inr_expression(),
            self._calculate_aptt_expression(),
            self._calculate_platelets50_expression(),
            self._calculate_platelets100_expression(),
        ).with_columns(
            pl.when(
                (pl.col(self.coagulation_config.inr_flag) == 1)|
                (pl.col(self.coagulation_config.aptt_flag) == 1)|
                (pl.col(self.coagulation_config.platelets50_flag) == 1)|
                (pl.col(self.coagulation_config.platelets100_flag) == 1)
            ).then(pl.lit(1)).otherwise(pl.lit(0)).alias(self.coagulation_config.flag_col)
        )