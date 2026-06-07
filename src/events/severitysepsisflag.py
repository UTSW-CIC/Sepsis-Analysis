import polars as pl
from src.configs.severitysepsis import SeveritySepsisConfig
from src.utils.utils import combine_dfs_using_backbone


class SeveritySepsisFlag:
    def __init__(self, df_infect: pl.DataFrame, df_sirs: pl.DataFrame,
                  df_organdysfunction: pl.DataFrame, df_pulmonarydysfunction: pl.DataFrame, df_septicshock:pl.DataFrame,
                  severitysepsisconfig: SeveritySepsisConfig):
        self.df_infect = df_infect
        self.df_sirs = df_sirs
        self.df_organdysfunction = df_organdysfunction
        self.df_septicshock = df_septicshock
        self.df_pulmonarydysfunction = df_pulmonarydysfunction
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
            (pl.col(self.severitysepsisconfig.event_dt_col) >= pl.col(self.severitysepsisconfig.suspected_infection_config.value_name_dt_col) - pl.duration(hours=self.severitysepsisconfig.infection_2_sirs_backward_hrs))&
            (pl.col(self.severitysepsisconfig.event_dt_col) <= pl.col(self.severitysepsisconfig.suspected_infection_config.value_name_dt_col) + pl.duration(hours=self.severitysepsisconfig.infection_2_sirs_forward_hrs))
        )
        return dd1

    def _sepsis_2(self):
        dd = self.df_infect.join(
            self.df_organdysfunction.filter(
                pl.col(self.severitysepsisconfig.organdysfunction_config.flag_col) >= 1
            ),
                on=self.severitysepsisconfig.encounter_col,
                how="left"
        )

        dd_p = self.df_infect.join(
            self.df_pulmonarydysfunction.filter(
                pl.col(self.severitysepsisconfig.pulmonarydysfunction_config.pulmonary_dysfunction_flag) >= 1
            ),
                on=self.severitysepsisconfig.encounter_col,
                how="left"
        )

        dd = dd.filter(
            (
            (pl.col(self.severitysepsisconfig.event_dt_col) >= pl.col(self.severitysepsisconfig.suspected_infection_config.value_name_dt_col) - pl.duration(hours=self.severitysepsisconfig.infection_2_organdysfunction_backward_hrs))&
            (pl.col(self.severitysepsisconfig.event_dt_col) <= pl.col(self.severitysepsisconfig.suspected_infection_config.value_name_dt_col) + pl.duration(hours=self.severitysepsisconfig.infection_2_organdysfunction_forward_hrs))
            )
        )

        dd_p = dd_p.filter(
            (
            (pl.col(self.severitysepsisconfig.event_dt_col) >= pl.col(self.severitysepsisconfig.suspected_infection_config.value_name_dt_col) - pl.duration(hours=self.severitysepsisconfig.infection_2_organdysfunction_backward_hrs))&
            (pl.col(self.severitysepsisconfig.event_dt_col) <= pl.col(self.severitysepsisconfig.suspected_infection_config.value_name_dt_col) + pl.duration(hours=self.severitysepsisconfig.infection_2_organdysfunction_forward_hrs))
            )
        )

        dd_f = combine_dfs_using_backbone(dd, dd_p,
                                          [self.severitysepsisconfig.encounter_col, self.severitysepsisconfig.suspected_infection_config.value_name_dt_col],
                                           how='left', suffix_1='_organdys', suffix_2='_pulmonarydys')

        return dd_f


    def _sepsis_3_with_infection_and_od(self, sepsis2_df: pl.DataFrame):
        # Configs
        shock_flag = self.severitysepsisconfig.septicshock_config.flag_col
        event_dt = self.severitysepsisconfig.event_dt_col
        infect_dt = self.severitysepsisconfig.suspected_infection_config.value_name_dt_col

        shock_forward_hrs = self.severitysepsisconfig.infection_2_shock_dysfunction_forward_hrs
        shock_backward_hrs = self.severitysepsisconfig.infection_2_shock_dysfunction_backward_hrs

        sepsis2_backbone = sepsis2_df.select(
            self.severitysepsisconfig.encounter_col, self.severitysepsisconfig.suspected_infection_config.value_name_dt_col 
        ).unique()

        # Getting the time when a shock flag is set
        septic_shock_df = self.df_septicshock.filter(pl.col(shock_flag)==1).join(
            sepsis2_backbone,
            on=self.severitysepsisconfig.encounter_col,
            how='left'
        ).filter(
            (pl.col(event_dt) >= (pl.col(infect_dt)-pl.duration(hours=shock_backward_hrs)))&
            (pl.col(event_dt) <= (pl.col(infect_dt)+pl.duration(hours=shock_forward_hrs)))
        )
        return septic_shock_df



    def _clean_sepsis1_columns(self, sepsis1_df: pl.DataFrame):
        return (
            sepsis1_df.select(
                self.severitysepsisconfig.encounter_col,
                self.severitysepsisconfig.suspected_infection_config.value_name_dt_col,
                self.severitysepsisconfig.event_dt_col,
                self.severitysepsisconfig.sirs_config.sirs_score_col,
            ).with_columns(
                pl.min_horizontal([
                self.severitysepsisconfig.suspected_infection_config.value_name_dt_col,
                self.severitysepsisconfig.event_dt_col,
                ]).alias(self.severitysepsisconfig.earliest_sepsis1_instance)
            ).sort(by=[
                self.severitysepsisconfig.encounter_col,
                self.severitysepsisconfig.earliest_sepsis1_instance
            ])
        )

    def _clean_sepsis2_columns(self, sepsis2_df: pl.DataFrame):
        return (
            sepsis2_df.select(
                self.severitysepsisconfig.encounter_col,
                self.severitysepsisconfig.suspected_infection_config.value_name_dt_col,
                self.severitysepsisconfig.event_dt_col,
                f'{self.severitysepsisconfig.event_dt_col}_pulmonarydys',
                self.severitysepsisconfig.organdysfunction_config.flag_col,
                self.severitysepsisconfig.pulmonarydysfunction_config.pulmonary_dysfunction_flag,
            ).with_columns(
                pl.min_horizontal([
                self.severitysepsisconfig.suspected_infection_config.value_name_dt_col,
                self.severitysepsisconfig.event_dt_col,
                f'{self.severitysepsisconfig.event_dt_col}_pulmonarydys',
                ]).alias(self.severitysepsisconfig.earliest_sepsis2_instance)
            ).sort(by=[
                self.severitysepsisconfig.encounter_col,
                self.severitysepsisconfig.earliest_sepsis2_instance
            ])
            
        )

    def _clean_sepsis3_columns(self, sepsis3_df: pl.DataFrame):
        return (
            sepsis3_df.select(
                self.severitysepsisconfig.encounter_col,
                self.severitysepsisconfig.suspected_infection_config.value_name_dt_col,
                self.severitysepsisconfig.event_dt_col,
                self.severitysepsisconfig.septicshock_config.flag_col,
            ).with_columns(
                pl.min_horizontal([
                self.severitysepsisconfig.suspected_infection_config.value_name_dt_col,
                self.severitysepsisconfig.event_dt_col,
                ]).alias(self.severitysepsisconfig.earliest_sepsis3_instance)
            ).sort(by=[
                self.severitysepsisconfig.encounter_col,
                self.severitysepsisconfig.earliest_sepsis3_instance
            ])
            
        )


    def compute(self):
        raw_sepsis1_df = self._sepsis_1()
        raw_sepsis2_df = self._sepsis_2() 

        sepsis1_df = self._clean_sepsis1_columns(raw_sepsis1_df)
        sepsis2_df = self._clean_sepsis2_columns(raw_sepsis2_df)
        raw_sepsis3_df = self._sepsis_3_with_infection_and_od(sepsis2_df)
        sepsis3_df = self._clean_sepsis3_columns(raw_sepsis3_df)
        # x = 0


        # # self.detect_sepsis2_sepsis3_from_sepsis_1(sepsis1_df)
        # sepsis1_from_sepsis2_df = self._sepsis_1_from_sepsis_2(sepsis2_df)
        # x = 0

        # # sepsis3_df = self._sepsis_3()
        # # sepsis3_df = self._sepsis_3_new()
        return sepsis1_df, sepsis2_df, sepsis3_df



    
    def detect_sepsis2_sepsis3_from_sepsis_1(self, clean_sepsis1_df: pl.DataFrame):
        enc_id = self.severitysepsisconfig.encounter_col        
        event_dt = self.severitysepsisconfig.event_dt_col
        sepsis1_instance = self.severitysepsisconfig.earliest_sepsis1_instance
        og_flag = self.severitysepsisconfig.organdysfunction_config.flag_col
        pul_flag = self.severitysepsisconfig.pulmonarydysfunction_config.pulmonary_dysfunction_flag
        shock_flag = self.severitysepsisconfig.septicshock_config.flag_col
        sirs_score = self.severitysepsisconfig.sirs_config.sirs_score_col

        window = self.severitysepsisconfig.sepsis_state_period_from_infection_hrs

        # Preprocess 
        df_od = self.df_organdysfunction.filter(pl.col(og_flag)>0).group_by(
            enc_id, event_dt
        ).agg(
            pl.col(og_flag).max().alias("max_og_flag")
        )

        df_pul = self.df_pulmonarydysfunction.filter(pl.col(pul_flag)>0).group_by(
            enc_id, event_dt
        ).agg(
            pl.col(pul_flag).max().alias("max_pul_flag")
        )
        
        df_shock = self.df_septicshock.filter(pl.col(shock_flag)>0).group_by(
            enc_id, event_dt
        ).agg(
            pl.col(shock_flag).max().alias("max_shoch_flag")
        )


        backbone_s1 = clean_sepsis1_df.group_by(
            enc_id, sepsis1_instance
        ).agg(
            pl.col(sirs_score).max().alias("max_sirs_score")
        )

        df_od_joined = (
            backbone_s1
            .join(
               df_od , on=[enc_id], how='left'
            ).filter(
                (pl.col(event_dt) >= pl.col(sepsis1_instance))&
                (pl.col(event_dt) <= pl.col(sepsis1_instance)+pl.duration(hours=window))
            )
        )

        df_pul_joined = (
            backbone_s1
            .join(
                df_pul, on=[enc_id], how='left'
            ).filter(
                (pl.col(event_dt) >= pl.col(sepsis1_instance))&
                (pl.col(event_dt) <= pl.col(sepsis1_instance)+pl.duration(hours=window))
            )
        )

        df_shock_joined = (
            backbone_s1
            .join(
                df_shock, on=[enc_id], how='left'
            ).filter(
                (pl.col(event_dt) >= pl.col(sepsis1_instance))&
                (pl.col(event_dt) <= pl.col(sepsis1_instance)+pl.duration(hours=window))
            )
        )

        x = 0


    def _clean_sepsis3_columns(self, sepsis3_df: pl.DataFrame):
        return (
            sepsis3_df.select(
                self.severitysepsisconfig.encounter_col,
                self.severitysepsisconfig.suspected_infection_config.value_name_dt_col,
                self.severitysepsisconfig.event_dt_col,
                self.severitysepsisconfig.septicshock_config.flag_col,
            ).with_columns(
                pl.min_horizontal([
                self.severitysepsisconfig.suspected_infection_config.value_name_dt_col,
                self.severitysepsisconfig.event_dt_col,
                ]).alias(self.severitysepsisconfig.earliest_sepsis3_instance)
            ).sort(by=[
                self.severitysepsisconfig.encounter_col,
                self.severitysepsisconfig.earliest_sepsis3_instance
            ])
            
        )

    def _sepsis_3_obselete(self):
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