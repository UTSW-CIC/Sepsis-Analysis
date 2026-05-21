import polars as pl
from src.configs.severitysepsis import SeveritySepsisConfig


class SeveritySepsisFlag:
    def __init__(self, df_infect: pl.DataFrame, df_sirs: pl.DataFrame,
                  df_organdysfunction: pl.DataFrame, df_septicshock:pl.DataFrame,
                  severitysepsisconfig: SeveritySepsisConfig):
        self.df_infect = df_infect
        self.df_sirs = df_sirs
        self.df_organdysfunction = df_organdysfunction
        self.df_septicshock = df_septicshock
        self.severitysepsisconfig = severitysepsisconfig
    
    def _sepsis_1(self):
        dd1 = self.df_infect.join(
            self.df_sirs.filter(
                pl.col(self.severitysepsisconfig.sirs_config.sirs_score_col) >= 2
            ),
            on=self.severitysepsisconfig.encounter_col,
            how="left"
        )
        dd1 = dd1.filter(
            (pl.col(self.severitysepsisconfig.event_dt_col) >= pl.col(self.severitysepsisconfig.suspected_infection_config.value_name_dt_col) - pl.duration(hours=24))&
            (pl.col(self.severitysepsisconfig.event_dt_col) <= pl.col(self.severitysepsisconfig.suspected_infection_config.value_name_dt_col) + pl.duration(hours=24))
        )
        dd1 = dd1.unique()
        dd1 = dd1.sort(
            by=[
                self.severitysepsisconfig.encounter_col,
                self.severitysepsisconfig.suspected_infection_config.value_name_dt_col,
                self.severitysepsisconfig.event_dt_col
            ]
        )
        dd1 = dd1.group_by(
            self.severitysepsisconfig.encounter_col
        ).first()

        dd1 = dd1.with_columns(
            pl.min_horizontal([
                self.severitysepsisconfig.event_dt_col, self.severitysepsisconfig.suspected_infection_config.value_name_dt_col
            ]).alias(self.severitysepsisconfig.earliest_sepsis1_instance)
        )

        return dd1

    # def _sepsis_1_old(self):
    #     """
    #     """
    #     # Configs
    #     infection_to_sirs_gte2 = 48
    #     sirs_score_threshold = 2
    #     sirs_score_threshold_dt_col = 'first_sirs_gte_2_dt'
    #     earliest_infection_time_col = "earliest_infection_time"
    #     earliest_infection_event_col = "earliest_infection_event"
    #     sirs_infect_time_diff_hrs_col = "sirs_infect_diff_hrs"  

    #     df_sirs_1 = self.df_sirs.filter(
    #         pl.col(self.severitysepsisconfig.sirs_config.sirs_score_col) >= sirs_score_threshold
    #     ).group_by(
    #         pl.col(self.severitysepsisconfig.encounter_col)
    #     ).agg(
    #         pl.col(self.severitysepsisconfig.event_dt_col).min().alias(sirs_score_threshold_dt_col)
    #     )

    #     infect_dt_cols = self.severitysepsisconfig.suspected_infection_config.dt_columns

    #     self.df_infect.join(
    #         df_sirs_1,
    #         on=self.severitysepsisconfig.encounter_col,
    #         how="left"
    #     ).with_columns(
    #         pl.when(
    #             pl.col(infect_dt_cols[0]).is_not_null()&
    #             ( 
    #                 (pl.col(sirs_score_threshold_dt_col) <= (pl.col(infect_dt_cols[0]+pl.duration(hours=infection_to_sirs_gte2))))&
    #                 (pl.col(sirs_score_threshold_dt_col) >= (pl.col(infect_dt_cols[0]-pl.duration(hours=infection_to_sirs_gte2))))
    #             )
    #         ).then(pl.lit())
    #     )




    #     # expr_conds = pl.any_horizontal([
    #     #     pl.col("first_sirs_gte_2") >= pl.col(col) for col in infect_dt_cols
    #     # ])

    #     # Main idea is that you want to capture within 24 hours of infection if SIRS score went up to 2
    #     expr_conds = pl.any_horizontal([
    #         (
    #             (pl.col(sirs_score_threshold_col) >= (pl.col(col)-pl.duration(hours=infection_to_sirs_gte2)))&
    #             (pl.col(sirs_score_threshold_col) <= (pl.col(col)+pl.duration(hours=infection_to_sirs_gte2)))
    #         )  for col in infect_dt_cols
    #     ])

    #     dd = self.df_infect.join(
    #         df_sirs_1,
    #         on=self.severitysepsisconfig.encounter_col,
    #         how="left"
    #     ).filter(
    #         expr_conds
    #     ).with_columns(
    #         pl.min_horizontal(infect_dt_cols).alias(earliest_infection_time_col)
    #     ).with_columns(
    #         (pl.col(sirs_score_threshold_col)-pl.col(earliest_infection_time_col)).dt.total_hours(fractional=True)
    #         .alias(sirs_infect_time_diff_hrs_col)
    #     )

    #     expr = None
    #     for c in infect_dt_cols:
    #         if expr is None:
    #             expr = pl.when(
    #                 pl.col(earliest_infection_time_col) == pl.col(c)
    #             ).then(pl.lit(c))
    #         else:
    #             expr = expr.when(
    #                 pl.col(earliest_infection_time_col) == pl.col(c)
    #             ).then(pl.lit(c))
    #     expr = expr.otherwise(None)
    #     dd = dd.with_columns(
    #         expr.alias(earliest_infection_event_col)
    #     )

    #     """ 
    #     Given how the distribution of the time difference between SIRS score >= 2 and the closest infection time. 48 hours are decided as the threshold to include more than 99% of the encounters 
    #     NOTE: That threshold was decided before running outlier removal
    #     """
    #     # import plotly.express as px

    #     # fig = px.histogram(dd.to_pandas(),
    #     #                     x='sirs_infect_diff_hrs',
    #     #                       nbins=128)
    #     # fig.show()


    #     return dd

    #     # return dd.filter(
    #     #     pl.col("sirs_infect_diff_hrs").abs() <= 48
    #     # )
    
    # Sepsis 2 depending on SIRS score which is not essential
    # def _sepsis_2(self, sespsis_1_df: pl.DataFrame):
    #     return sespsis_1_df.join(
    #         self.df_organdysfunction.filter(
    #             pl.col(self.severitysepsisconfig.organdysfunction_config.flag_col) >= 1
    #         ),
    #             on=self.severitysepsisconfig.encounter_col,
    #             how="left"
    #     ).filter(
    #         (pl.col("first_sirs_gte_2") >= pl.col(self.severitysepsisconfig.organdysfunction_config.event_dt_col) - pl.duration(hours=24))&
    #         (pl.col("first_sirs_gte_2") <= pl.col(self.severitysepsisconfig.organdysfunction_config.event_dt_col) + pl.duration(hours=24))
    #     ).with_columns(
    #         (pl.col('first_sirs_gte_2')-pl.col(self.severitysepsisconfig.event_dt_col)).dt.total_hours(fractional=True).abs().alias('sepsis1_to_organdysfc')
    #     ).sort(by=[self.severitysepsisconfig.encounter_col, "first_sirs_gte_2"]).group_by(
    #         self.severitysepsisconfig.encounter_col
    #     ).first()   

    def _sepsis_2(self):
        dd = self.df_infect.join(
            self.df_organdysfunction.filter(
                pl.col(self.severitysepsisconfig.organdysfunction_config.flag_col) >= 1
            ),
                on=self.severitysepsisconfig.encounter_col,
                how="left"
        )
        dd = dd.filter(
            (pl.col(self.severitysepsisconfig.event_dt_col) >= pl.col(self.severitysepsisconfig.suspected_infection_config.value_name_dt_col) - pl.duration(hours=48))&
            (pl.col(self.severitysepsisconfig.event_dt_col) <= pl.col(self.severitysepsisconfig.suspected_infection_config.value_name_dt_col) + pl.duration(hours=48))
        )
        dd = dd.unique()
        dd = dd.sort(
            by=[
                self.severitysepsisconfig.encounter_col,
                self.severitysepsisconfig.suspected_infection_config.value_name_dt_col,
                self.severitysepsisconfig.event_dt_col
            ]
        )
        dd = dd.group_by(
            self.severitysepsisconfig.encounter_col
        ).first()

        dd = dd.with_columns(
            pl.min_horizontal([
                self.severitysepsisconfig.event_dt_col, self.severitysepsisconfig.suspected_infection_config.value_name_dt_col
            ]).alias(self.severitysepsisconfig.earliest_sepsis2_instance)
        )

        return dd

    # def _sepsis_2_old(self):
    #     infect_dt_cols = self.severitysepsisconfig.suspected_infection_config.dt_columns

    #     expr_conds = pl.any_horizontal([
    #         pl.col(self.severitysepsisconfig.event_dt_col) >= pl.col(col) for col in infect_dt_cols
    #     ])

    #     dd = self.df_infect.join(
    #         self.df_organdysfunction.filter(pl.col(self.severitysepsisconfig.organdysfunction_config.flag_col) >= 1),
    #         on=self.severitysepsisconfig.encounter_col,
    #         how="left"
    #     ).filter(
    #         expr_conds
    #     ).with_columns(
    #         pl.min_horizontal(infect_dt_cols).alias('earliest_datetime')
    #     ).with_columns(
    #         (pl.col("Event_DateTime")-pl.col("earliest_datetime")).dt.total_hours(fractional=True).alias('organdys_infect_diff_hrs')
    #     )

    #     expr = None
    #     for c in infect_dt_cols:
    #         if expr is None:
    #             expr = pl.when(
    #                 pl.col('earliest_datetime') == pl.col(c)
    #             ).then(pl.lit(c))
    #         else:
    #             expr = expr.when(
    #                 pl.col('earliest_datetime') == pl.col(c)
    #             ).then(pl.lit(c))
    #     expr.otherwise('None')
    #     dd = dd.with_columns(
    #         expr.alias('earliest_infection_event')
    #     )

    #     return dd.filter(
    #         pl.col('organdys_infect_diff_hrs') <= 72
    #     )

    def _sepsis_3(self):
        septic_shock_suffix = self.severitysepsisconfig.septic_shock_suffix
        dd = self.df_infect.join(
            self.df_organdysfunction.filter(
                pl.col(self.severitysepsisconfig.organdysfunction_config.flag_col) >= 1
            ),
            on=self.severitysepsisconfig.encounter_col,
            # how="left"
        )
        dd = dd.filter(
            (pl.col(self.severitysepsisconfig.event_dt_col) >= pl.col(self.severitysepsisconfig.suspected_infection_config.value_name_dt_col) - pl.duration(hours=48))&
            (pl.col(self.severitysepsisconfig.event_dt_col) <= pl.col(self.severitysepsisconfig.suspected_infection_config.value_name_dt_col) + pl.duration(hours=48))
        )
        dd = dd.unique(
            subset=[
                self.severitysepsisconfig.encounter_col,
                self.severitysepsisconfig.organdysfunction_config.event_dt_col,
                self.severitysepsisconfig.suspected_infection_config.value_name_dt_col,
                self.severitysepsisconfig.suspected_infection_config.variable_name_col,
                self.severitysepsisconfig.suspected_infection_config.value_type_col
            ]
        )
        dd = dd.join(
            self.df_septicshock.filter(
                pl.col(self.severitysepsisconfig.septicshock_config.flag_col) >= 1,
            ),
            on=self.severitysepsisconfig.encounter_col,
            # how="left",
            suffix=septic_shock_suffix
        )
        dd = dd.filter(
            (pl.col(f'{self.severitysepsisconfig.organdysfunction_config.event_dt_col}{septic_shock_suffix}') >= (pl.col(self.severitysepsisconfig.organdysfunction_config.event_dt_col) - pl.duration(hours=6)))&
            (pl.col(f'{self.severitysepsisconfig.organdysfunction_config.event_dt_col}{septic_shock_suffix}') <= (pl.col(self.severitysepsisconfig.organdysfunction_config.event_dt_col) + pl.duration(hours=24)))
        )
        dd = dd.unique(
            subset=[
                self.severitysepsisconfig.encounter_col,
                self.severitysepsisconfig.organdysfunction_config.event_dt_col,
                self.severitysepsisconfig.suspected_infection_config.value_name_dt_col,
                self.severitysepsisconfig.septicshock_config.event_dt_col+septic_shock_suffix,
                self.severitysepsisconfig.septicshock_config.flag_col,
                self.severitysepsisconfig.suspected_infection_config.variable_name_col,
                self.severitysepsisconfig.suspected_infection_config.value_type_col
            ]
        )
        dd = dd.sort(
            by=[self.severitysepsisconfig.encounter_col,
                self.severitysepsisconfig.septicshock_config.event_dt_col+septic_shock_suffix,
                self.severitysepsisconfig.organdysfunction_config.event_dt_col,
                self.severitysepsisconfig.suspected_infection_config.value_name_dt_col
                ]
        )
        dd = dd.group_by(
            self.severitysepsisconfig.encounter_col
        ).first()

        dd = dd.with_columns(
            pl.min_horizontal([
            self.severitysepsisconfig.suspected_infection_config.value_name_dt_col,
            self.severitysepsisconfig.organdysfunction_config.event_dt_col,
            self.severitysepsisconfig.septicshock_config.event_dt_col+septic_shock_suffix
        ]).alias(self.severitysepsisconfig.earliest_sepsis3_instance))

        return dd


    # def _sepsis_3_old(self):
    #     infect_dt_cols = self.severitysepsisconfig.suspected_infection_config.dt_columns

    #     expr_conds = pl.any_horizontal([
    #         pl.col(self.severitysepsisconfig.event_dt_col) >= pl.col(col) for col in infect_dt_cols
    #     ])

    #     dd = self.df_infect.join(
    #         self.df_organdysfunction.filter(pl.col(self.severitysepsisconfig.organdysfunction_config.flag_col) >= 1),
    #         on=self.severitysepsisconfig.encounter_col,
    #         how="left"
    #     ).filter(
    #         expr_conds
    #     ).with_columns(
    #         pl.min_horizontal(infect_dt_cols).alias('earliest_datetime')
    #     ).with_columns(
    #         (pl.col("Event_DateTime")-pl.col("earliest_datetime")).dt.total_hours(fractional=True).alias('organdys_infect_diff_hrs')
    #     )

    #     expr = None
    #     for c in infect_dt_cols:
    #         if expr is None:
    #             expr = pl.when(
    #                 pl.col('earliest_datetime') == pl.col(c)
    #             ).then(pl.lit(c))
    #         else:
    #             expr = expr.when(
    #                 pl.col('earliest_datetime') == pl.col(c)
    #             ).then(pl.lit(c))
    #     expr.otherwise('None')
    #     dd = dd.with_columns(
    #         expr.alias('earliest_infection_event')
    #     )

    #     return dd.filter(
    #         pl.coL('organdys_infect_diff_hrs') <= 72
    #     )

    def compute(self):
        sepsis1_df = self._sepsis_1()
        sepsis2_df = self._sepsis_2() 
        sepsis3_df = self._sepsis_3()
        return sepsis1_df, sepsis2_df, sepsis3_df



    