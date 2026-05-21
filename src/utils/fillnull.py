import polars as pl

from src.configs.fillnulls import FillNullsConfig

class NullsFiller:
    def __init__(self, cfg: FillNullsConfig):
        self.cfg = cfg
    
    def _config_to_expression(self) -> pl.Expr:
        expr = pl.lit(None)
        for grouper_val, expiration_val in self.cfg.expiration_registery.items():
            expr = (
                pl.when(
                    pl.col(self.cfg.grouper_col) == grouper_val
                ).then(
                    pl.lit(expiration_val)
                ).otherwise(expr)
            )
        return expr

    def fill_nulls(self, df: pl.DataFrame) -> pl.DataFrame:
        # Implement the logic to fill nulls based on the strategy defined in the configuration
        total_expr = self._config_to_expression()
        if self.cfg.fillna_strategy == "forward":
            return df.sort(by=[self.cfg.encounter_col, self.cfg.event_dt_col]).with_columns(
                total_expr.alias("Total_Flag_Count"),
                pl.when(
                    pl.col(self.cfg.val_col).is_not_null()
                ).then(
                    pl.col(self.cfg.event_dt_col)
                ).otherwise(
                    None
                ).alias("_origin_ts")
            ).with_columns(
                pl.col(self.cfg.val_col).forward_fill().over(self.cfg.encounter_col, self.cfg.grouper_col).alias("_val_ffill"),
                pl.col("_origin_ts").forward_fill().over(self.cfg.encounter_col, self.cfg.grouper_col).alias("_origin_ts_ffill"),
            ).with_columns(
                (pl.col(self.cfg.event_dt_col)-pl.col("_origin_ts_ffill")).dt.total_hours(fractional=True).alias("Hours_Since_Origin"),
                pl.when(
                    (pl.col(self.cfg.event_dt_col)-pl.col("_origin_ts_ffill")).dt.total_hours(fractional=True) <= pl.col("Total_Flag_Count")
                ).then(
                    pl.col("_val_ffill")
                ).otherwise(
                    None
                # ).alias(self.cfg.val_col)
                ).alias("num_val_filled")
                ).with_columns(
                    pl.col("num_val_filled").fill_null(pl.col(self.cfg.val_col))
                ).drop(["Total_Flag_Count", "_origin_ts", "_val_ffill", "_origin_ts_ffill", "Hours_Since_Origin", "num_val_filled"])
        else:
            raise NotImplementedError(f"Fillna strategy {self.cfg.fillna_strategy} not implemented yet.")