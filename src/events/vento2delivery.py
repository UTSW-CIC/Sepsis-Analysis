from src.configs.pulmonarydysfunction import PulmonaryDysfunctionConfig
import polars as pl


class VentO2Delivery:
    def __init__(self, df_agg: pl.DataFrame, pulmonary_dysfunction_config: PulmonaryDysfunctionConfig):
        self.df_agg = df_agg
        self.pulmonary_dysfunction_config = pulmonary_dysfunction_config

    def calculate_vent_onoff_flags(self) -> pl.DataFrame:
        vent_onoff_config = self.pulmonary_dysfunction_config.vent_onoff_config
        # return self.df_agg.with_columns(
        #     pl.when(
        #         (pl.col(vent_onoff_config.grouper_col) == vent_onoff_config.vent_grouper_val)&
        #         (pl.col(vent_onoff_config.raw_val_col).is_in(vent_onoff_config.vent_on_status))
        #     ).then(pl.lit(1)).otherwise(pl.lit(None)).alias(vent_onoff_config.vent_on_off_flag)
        # )
        return pl.when(
                (pl.col(vent_onoff_config.grouper_col) == vent_onoff_config.vent_grouper_val)&
                (pl.col(vent_onoff_config.raw_val_col).is_in(vent_onoff_config.vent_on_status))
            ).then(pl.lit(1)).otherwise(pl.lit(None)).alias(vent_onoff_config.vent_on_off_flag)
        

    def calculate_vent_documentation_flags(self) -> pl.DataFrame:
        vent_doc_config = self.pulmonary_dysfunction_config.vent_documentation_config
        # return self.df_agg.with_columns(
        #     pl.when(pl.col(vent_doc_config.grouper_col) == vent_doc_config.vent_doc_on_grouper_val_and_status )
        #     .then(pl.lit(1)).otherwise(pl.lit(None)).alias(vent_doc_config.vent_document_on_flag)
        # )
        return pl.when(pl.col(vent_doc_config.grouper_col) == vent_doc_config.vent_doc_on_grouper_val_and_status )\
            .then(pl.lit(1)).otherwise(pl.lit(None)).alias(vent_doc_config.vent_document_on_flag)

    def calculate_pf_flags(self, df_vent: pl.DataFrame) -> pl.DataFrame:
        pf_config = self.pulmonary_dysfunction_config.pf_config

        df_pao2 = df_vent.filter(
        pl.col(pf_config.grouper_col) == pf_config.pao2_grouper_val
        ).select(
            pf_config.encounter_col, pf_config.event_dt_col, pf_config.type_col, pf_config.event_name_col, pf_config.raw_val_col, pf_config.val_col
        )

        df_fio2 = df_vent.filter(
        pl.col(pf_config.grouper_col) == pf_config.fio2_grouper_val
        ).select(
            pf_config.encounter_col, pf_config.event_dt_col, pf_config.type_col, pf_config.event_name_col, pf_config.raw_val_col, pf_config.val_col
        )

        df_pao2_fio2_joined = df_pao2.join(
            df_fio2,
            on=pf_config.encounter_col
        ).filter(
            (pl.col(pf_config.event_dt_col)-pl.col(f"{pf_config.event_dt_col}_right")).abs() < pl.duration(hours=pf_config.time_window_between_pao2_fio2_hrs)
        ).sort(by=[pf_config.encounter_col, pf_config.event_dt_col, f"{pf_config.event_dt_col}_right"])

        df_pao2_fio2_joined = df_pao2_fio2_joined.with_columns(
                    (pl.col(pf_config.val_col)/(pl.col(f"{pf_config.val_col}_right")/100.0)).alias(pf_config.pf_ratio_col)
                ).with_columns(
                    pl.when(pl.col(pf_config.pf_ratio_col)<pf_config.pf_lower_threshold).then(pl.lit(1)).otherwise(pl.lit(None)).alias(pf_config.pf_flag)
                )

        
        df_vent =  df_vent.join(
            df_pao2_fio2_joined.select(pf_config.encounter_col, pf_config.event_dt_col,
                                        pf_config.event_name_col, pf_config.pf_ratio_col, pf_config.pf_flag),
            on=[pf_config.encounter_col, pf_config.event_dt_col, pf_config.event_name_col],
            how='left'
        )

        if f'{pf_config.event_name_col}_right' in self.df_agg.columns:
            df_vent = df_vent.drop(f'{pf_config.event_name_col}_right')

        if f'{pf_config.event_dt_col}_right' in self.df_agg.columns:
            df_vent = df_vent.drop(f'{pf_config.event_dt_col}_right')

        return df_vent


    def calculate_o2_delivery_flags(self) -> pl.DataFrame:
        o2_config = self.pulmonary_dysfunction_config.o2_delivery_config
        # return self.df_agg.with_columns(
        #     pl.when(
        #         (pl.col(o2_config.grouper_col) == o2_config.mechanical_vent_grouper_val)&
        #         (pl.col(o2_config.raw_val_col).is_in(o2_config.mechanical_vent_on_status))
        #     ).then(pl.lit(1)).otherwise(pl.lit(None)).alias(o2_config.mechanical_vent_flag)
        # )
        return pl.when(
                (pl.col(o2_config.grouper_col) == o2_config.mechanical_vent_grouper_val)&
                (pl.col(o2_config.raw_val_col).is_in(o2_config.mechanical_vent_on_status))
            ).then(pl.lit(1)).otherwise(pl.lit(None)).alias(o2_config.mechanical_vent_flag)

    
    def calculate_termination_flags(self) -> pl.DataFrame:
        term_config = self.pulmonary_dysfunction_config.vent_termination_config
        # return self.df_agg.with_columns(
        #     pl.when(
        #         pl.col(term_config.grouper_col)==term_config.vent_documentation_grouper_val_and_status
        #     ).then(pl.lit(0)).otherwise(pl.lit(None))
        # )
        return pl.when(
            (pl.col(term_config.grouper_col)==term_config.vent_documentation_grouper_val_and_status)|
            (pl.col(term_config.grouper_col).is_in(term_config.o2_delivery_grouper_and_status)) |
            (
                (pl.col(term_config.grouper_col) == term_config.vent_onoff_grouper_val)&
                (pl.col(term_config.raw_val_col).is_null()|pl.col(term_config.raw_val_col).is_in(term_config.vent_onoff_status))
            ) | 
            (
                pl.col(term_config.pf_ratio_col) > term_config.pf_lower_threshold
            )
        ).then(pl.lit(0)).otherwise(pl.lit(None)).alias(term_config.termination_flag)
    
    def get_vent_dependent_patient(self):
        excluded_config = self.pulmonary_dysfunction_config.excluded_encounters_config
        excluded_encounters = self.df_agg.group_by(
            excluded_config.encounter_col
        ).agg(
            (pl.when(
                (pl.col(excluded_config.raw_val_col).is_in(excluded_config.vent_dep_raw_val))|
                (
                    (pl.col(excluded_config.grouper_col)==excluded_config.vent_dep_grouper_val)&
                    (pl.col(excluded_config.raw_val_col)==excluded_config.vent_dep_grouper_expr)
                )
            ).then(pl.lit(1)).otherwise(0).alias("Vent_dependent")).sum()
        ).filter(
            pl.col("Vent_dependent")>0
        )[excluded_config.encounter_col]
        return excluded_encounters

    def process(self):
        excluded_enc = self.get_vent_dependent_patient()
        df_novent_dep = self.df_agg.filter(~pl.col(self.pulmonary_dysfunction_config.encounter_col).is_in(excluded_enc))
        df_novent_dep = self.calculate_pf_flags(df_novent_dep)

        expr_ventonoff = self.calculate_vent_onoff_flags()
        expr_ventdoc = self.calculate_vent_documentation_flags()
        expr_o2 = self.calculate_o2_delivery_flags()
        expr_term = self.calculate_termination_flags()

        df = df_novent_dep.with_columns(
            [
                expr_ventonoff, expr_ventdoc, expr_o2, expr_term
            ]
        ).with_columns(
            pl.coalesce(self.pulmonary_dysfunction_config.set_flag_cols).alias(self.pulmonary_dysfunction_config.pulmonary_dysfunction_flag)
        ).with_columns(
            pl.when(pl.col(self.pulmonary_dysfunction_config.term_flag_col).is_not_null())
            .then(pl.lit(0))
            .otherwise(pl.col(self.pulmonary_dysfunction_config.pulmonary_dysfunction_flag))
            .alias(self.pulmonary_dysfunction_config.pulmonary_dysfunction_flag)
        )
        return df 
