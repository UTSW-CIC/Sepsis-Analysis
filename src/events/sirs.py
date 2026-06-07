import polars as pl
from typing import List, Optional
# from ..config import SIRSConfig
from src.configs.sirscalculator import SIRSConfig, SIRSPostAggConfig

class SIRSCalculator:
    def __init__(self, df_all: pl.DataFrame,
        config: SIRSConfig|SIRSPostAggConfig 
        ):
        self.df_all = df_all
        self.cfg = config
        if isinstance(config, SIRSConfig):
            self.post_agg = False
        elif isinstance(config, SIRSPostAggConfig):
            self.post_agg = True
        else: 
            raise ValueError("Config must be either SIRSConfig or SIRSPostAggConfig")

    def _temp_flag(self):
        df_temp_abnormal = self.df_all.filter(
            (pl.col(self.cfg.grouper_col) == self.cfg.temp_grouper_val)&
            (
                (pl.col(self.cfg.val_col) < self.cfg.temp_lower_threshold)|
                (pl.col(self.cfg.val_col) > self.cfg.temp_upper_threshold)
            )
        ).select(
            self.cfg.selected_cols
        ).with_columns(
            pl.lit(1).alias(self.cfg.temp_flag_col)
        )
        return df_temp_abnormal

    def _hr_flag(self):
        df_pulse_abnormal = self.df_all.filter(
            (pl.col(self.cfg.grouper_col) == self.cfg.hr_grouper_val)&
            (
                (pl.col(self.cfg.val_col) > self.cfg.hr_upper_threshold)
            )
        ).select(
            self.cfg.selected_cols
        ).with_columns(
            pl.lit(1).alias(self.cfg.hr_flag_col)
        )
        return df_pulse_abnormal

    def _resp_flag(self):
        df_resp_abnormal = self.df_all.filter(
            (pl.col(self.cfg.grouper_col) == self.cfg.resp_grouper_val)&
            (
                (pl.col(self.cfg.val_col) > self.cfg.resp_upper_threshold)
            )
        ).select(
            self.cfg.selected_cols
        ).with_columns(
            pl.lit(1).alias(self.cfg.resp_flag_col)
        )
        return df_resp_abnormal

    def _wbc_flag(self):
        df_wbc_abnormal = self.df_all.filter(
            (pl.col(self.cfg.grouper_col) == self.cfg.wbc_grouper_val)&
            (
                (pl.col(self.cfg.val_col) < self.cfg.wbc_lower_threshold)|
                (pl.col(self.cfg.val_col) > self.cfg.wbc_upper_threshold)
            )
        ).select(
            self.cfg.selected_cols
        ).with_columns(
            pl.lit(1).alias(self.cfg.wbc_flag_col)
        )
        return df_wbc_abnormal


    def _wbc_flag_postagg(self, df_agg: pl.DataFrame):
        return df_agg.with_columns(
            pl.when(
                (pl.col(self.cfg.wbc_grouper_val) < self.cfg.wbc_lower_threshold)|
                (pl.col(self.cfg.wbc_grouper_val) > self.cfg.wbc_upper_threshold)
            ).then(pl.lit(1)).otherwise(pl.lit(0)).alias(self.cfg.wbc_flag_col)
        )

    def _hr_flag_postagg(self, df_agg: pl.DataFrame):
        return df_agg.with_columns(
            pl.when(
                (pl.col(self.cfg.hr_grouper_val) > self.cfg.hr_upper_threshold)
            ).then(pl.lit(1)).otherwise(pl.lit(0)).alias(self.cfg.hr_flag_col)
        )

    def _resp_flag_postagg(self, df_agg: pl.DataFrame):
        return df_agg.with_columns(
            pl.when(
                (pl.col(self.cfg.resp_grouper_val) > self.cfg.resp_upper_threshold)
            ).then(pl.lit(1)).otherwise(pl.lit(0)).alias(self.cfg.resp_flag_col)
        )
    
    def _temp_flag_postagg(self, df_agg: pl.DataFrame):
        return df_agg.with_columns(
            pl.when(
                (pl.col(self.cfg.temp_grouper_val) < self.cfg.temp_lower_threshold)|
                (pl.col(self.cfg.temp_grouper_val) > self.cfg.temp_upper_threshold)
            ).then(pl.lit(1)).otherwise(pl.lit(0)).alias(self.cfg.temp_flag_col)
        )

    def _join_tables(self, df_all: pl.DataFrame,
                     list_of_flag_dfs: List[pl.DataFrame],
                     on_cols: List[str] = ["EncounterEpicCsn", "Event_DateTime", "Event_Name"],
                     how: str = 'left'):
        for df_flag in list_of_flag_dfs:
            df_all = df_all.join(
                df_flag,
                on=on_cols,
                how=how
            ).drop([f"{self.cfg.val_col}_right"])

        df_all = df_all.sort(by=[self.cfg.encounter_col, self.cfg.event_dt_col]).with_columns(
        # TODO: Fix the Literal search for columns ending with Abnormal_Flag or High_Flag
        [pl.col(c).fill_null(strategy="forward").over(self.cfg.encounter_col).fill_null(0) for c in df_all.columns if c.endswith("Abnormal_Flag") or c.endswith("High_Flag")]
        )

        return df_all
    
    def calculate_sirs_flags(self):
        if self.post_agg:
            df_flags = self._temp_flag_postagg(self.df_all)
            df_flags = self._hr_flag_postagg(df_flags)
            df_flags = self._resp_flag_postagg(df_flags)
            df_all_abnormal_flags = self._wbc_flag_postagg(df_flags)
        else:
            df_temp = self._temp_flag()
            df_hr = self._hr_flag()
            df_resp = self._resp_flag()
            df_wbc = self._wbc_flag()
            # Combine all flags into one DataFrame
            df_all_abnormal_flags = self._join_tables(self.df_all, [df_wbc, df_temp, df_resp, df_hr],
                                                    on_cols=[self.cfg.encounter_col, self.cfg.event_dt_col, self.cfg.event_name_col],
                                                    how='left')


        # Propagate nulls
        # df_all_abnormal_flags = df_all_abnormal_flags.with_columns(
        #     (pl.col(self.cfg.wbc_flag_col)+pl.col(self.cfg.temp_flag_col)+
        #     pl.col(self.cfg.resp_flag_col)+pl.col(self.cfg.hr_flag_col)).alias(self.cfg.sirs_score_col)
        # )

        # Treat nulls as zeros
        df_all_abnormal_flags = df_all_abnormal_flags.with_columns(
            pl.sum_horizontal(
                [
                    pl.col(self.cfg.wbc_flag_col),
                    pl.col(self.cfg.temp_flag_col),
                    pl.col(self.cfg.resp_flag_col),
                    pl.col(self.cfg.hr_flag_col)
                ]
            ).alias(self.cfg.sirs_score_col)
        )
        
        return df_all_abnormal_flags


if __name__ == "__main__":
    df_all = dl.load_data()
    sirs_config = SIRSConfig()
    sirs_config.hr_flag_col = "Pule_High_Flag"
    sirs_calculator = SIRSCalculator(df_all, sirs_config)
    df_sirs = sirs_calculator.calculate_sirs_flags()