import polars as pl

from src.configs.imputer import ImputerConfig, VitalImputer


class Imputer:
    def __init__(self, imputer_config: ImputerConfig):
        self.imputer_config = imputer_config

    def _impute_vital(self, df: pl.DataFrame, vital_imputer:VitalImputer):
        type_col = self.imputer_config.type_col
        grouper_col = self.imputer_config.grouper_col
        val_col = self.imputer_config.val_col
        datetime_col = self.imputer_config.event_dt_col

        df_vital = df.filter(
            (pl.col(type_col) == vital_imputer.type_val)&
            (pl.col(grouper_col) == vital_imputer.grouper_val)
        ).with_columns(
            pl.
        )
        

    def impute(self, df: pl.DataFrame):
        for vital_imputer in self.imputer_config.vitals_imputers:


