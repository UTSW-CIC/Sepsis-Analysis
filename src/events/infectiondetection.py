import polars as pl
import duckdb
from src.dataloader import DataLoader
# from src.config import data_config
from src.utils.logger import get_logger
from src.configs.suspected_infection import SuspectedInfectionConfig

logger = get_logger(__name__)

class InfectionDetection:
    def __init__(self, df_all: pl.DataFrame, config: SuspectedInfectionConfig):
        self.df_all = df_all
        self.config = config

    def _detect_infection_with_antibiotic_culture(self, **kwargs) -> pl.DataFrame:
        logger.info("Detecting infection with antibiotic and culture criteria")
        antibiotic_bculture_config = self.config.antibiotic_blood_culture_config
        df_iv = self.df_all.filter(
            pl.col(self.config.type_col)== antibiotic_bculture_config.antibiotic_type_name
        ).select(self.config.encounter_col, self.config.event_dt_col, self.config.event_name_col)\
            .rename({self.config.event_dt_col: antibiotic_bculture_config.antibiotic_datetime_col,
                      self.config.event_name_col: antibiotic_bculture_config.antibiotic_evname_col}).sort(by=[self.config.encounter_col, antibiotic_bculture_config.antibiotic_datetime_col])

        df_culture = self.df_all.filter(
            pl.col(self.config.grouper_col)==antibiotic_bculture_config.blood_culture_grouper_val
        ).select(self.config.encounter_col, self.config.event_dt_col, self.config.event_name_col)\
            .rename({self.config.event_dt_col: antibiotic_bculture_config.blood_culture_datetime_col,
                     self.config.event_name_col: antibiotic_bculture_config.blood_culture_evname_col}).sort(by=[self.config.encounter_col, antibiotic_bculture_config.blood_culture_datetime_col])

        # IV centered
        df_forward = df_iv.join_asof(
            df_culture,
            left_on=antibiotic_bculture_config.antibiotic_datetime_col,
            right_on=antibiotic_bculture_config.blood_culture_datetime_col,
            by=self.config.encounter_col,
            strategy="forward",
            tolerance=antibiotic_bculture_config.forward_tolerance
        )

        df_backward = df_iv.join_asof(
            df_culture,
            left_on=antibiotic_bculture_config.antibiotic_datetime_col,
            right_on=antibiotic_bculture_config.blood_culture_datetime_col,
            by=self.config.encounter_col,
            strategy="backward",
            tolerance=antibiotic_bculture_config.backward_tolerance
        )

        # Culture centered
        # df_forward = df_culture.join_asof(
        #     df_iv,
        #     right_on=antibiotic_bculture_config.antibiotic_datetime_col,
        #     left_on=antibiotic_bculture_config.blood_culture_datetime_col,
        #     by=self.config.encounter_col,
        #     strategy="forward",
        #     tolerance=antibiotic_bculture_config.backward_tolerance
        # )

        # df_backward = df_culture.join_asof(
        #     df_iv,
        #     right_on=antibiotic_bculture_config.antibiotic_datetime_col,
        #     left_on=antibiotic_bculture_config.blood_culture_datetime_col,
        #     by=self.config.encounter_col,
        #     strategy="backward",
        #     tolerance=antibiotic_bculture_config.forward_tolerance
        # )

        # Combination that resulted into an issue. IV and culture are aggregated by first, which might
        # aggregate unmatched pairs

        # df_infection_detection = pl.concat([df_backward, df_forward], how="vertical").unique()

        # df_infect = df_infection_detection.group_by(self.config.encounter_col)\
        #     .agg(pl.col(antibiotic_bculture_config.antibiotic_datetime_col).min())\
        #     .join(df_infection_detection.group_by(self.config.encounter_col).agg(pl.col(antibiotic_bculture_config.blood_culture_datetime_col).min()), on=self.config.encounter_col).with_columns(
        #     pl.min_horizontal([antibiotic_bculture_config.antibiotic_datetime_col, antibiotic_bculture_config.blood_culture_datetime_col]).alias(antibiotic_bculture_config.first_time_ev_col)
        # ).with_columns(
        #     pl.lit(antibiotic_bculture_config.flag_val).alias(antibiotic_bculture_config.flag_col)
        # )

        df_infection_detection_1 = pl.concat([df_backward, df_forward], how="vertical")\
        .unique()\
        .filter(pl.col(antibiotic_bculture_config.blood_culture_datetime_col).is_not_null())

        df_infect_1 = (
            df_infection_detection_1
            .with_columns(
                pl.min_horizontal(
                    antibiotic_bculture_config.antibiotic_datetime_col,
                    antibiotic_bculture_config.blood_culture_datetime_col
                ).alias(antibiotic_bculture_config.first_time_ev_col)
            )
            .sort(antibiotic_bculture_config.first_time_ev_col)
            .group_by(self.config.encounter_col)
            .first()
            .with_columns(
                pl.lit(antibiotic_bculture_config.flag_val).alias(antibiotic_bculture_config.flag_col)
            )
        )

        return df_infect_1

    def _detect_infection_with_lactate_culture(self) -> pl.DataFrame:
        logger.info("Detecting infection with lactate and culture criteria")
        """
        Two blood culture orders within 6 hours of lactate order
        """
        lactate_culture_config = self.config.lactate_culture_config

        df_culture = self.df_all.filter(
            pl.col(self.config.grouper_col)==lactate_culture_config.blood_culture_grouper_val
        ).select(self.config.encounter_col, self.config.event_dt_col, self.config.event_name_col)\
            .rename({self.config.event_dt_col: lactate_culture_config.blood_culture_datetime_col,
                     self.config.event_name_col: lactate_culture_config.blood_culture_evname_col})

        df_lactate = self.df_all.filter(
            pl.col(self.config.grouper_col) == lactate_culture_config.lactate_grouper_val
        )

        df_lac_cult = duckdb.sql(
            f"""
            SELECT cul.{self.config.encounter_col},
                   cul.culture_dt AS {lactate_culture_config.blood_culture_datetime_col},
                   lac.Event_DateTime AS {lactate_culture_config.lactate_datetime_col} 
            FROM df_culture as cul
            LEFT JOIN df_lactate lac
            ON lac.{self.config.encounter_col}=cul.{self.config.encounter_col}
            AND lac.{self.config.event_dt_col} >= cul.{lactate_culture_config.blood_culture_datetime_col} - INTERVAL '{lactate_culture_config.tolerance}'
            AND lac.{self.config.event_dt_col} <= cul.{lactate_culture_config.blood_culture_datetime_col} + INTERVAL '{lactate_culture_config.tolerance}'
            """
        ).pl()

        df_lac_cult = df_lac_cult.drop_nulls(subset=[lactate_culture_config.lactate_datetime_col, lactate_culture_config.blood_culture_datetime_col])

        # 
        # df_infect =df_lac_cult.group_by(self.config.encounter_col).agg(pl.col(lactate_culture_config.blood_culture_datetime_col).min()).\
        #     join(df_lac_cult.group_by(self.config.encounter_col).agg(pl.col(lactate_culture_config.lactate_datetime_col).min()), on=self.config.encounter_col)\
        #         .with_columns(
        #     pl.min_horizontal([lactate_culture_config.blood_culture_datetime_col, lactate_culture_config.lactate_datetime_col]).alias(lactate_culture_config.first_time_ev_col)
        # ).with_columns(
        #     pl.lit(lactate_culture_config.flag_val).alias(lactate_culture_config.flag_col)
        # )

        # Find the earliest valid pair per encounter
        df_infect = (
            df_lac_cult
            .with_columns(
                pl.min_horizontal(
                    lactate_culture_config.blood_culture_datetime_col,
                    lactate_culture_config.lactate_datetime_col,
                ).alias(lactate_culture_config.first_time_ev_col)
            )
            .sort(lactate_culture_config.first_time_ev_col)
            .group_by(self.config.encounter_col)
            .first()
            .with_columns(
                pl.lit(lactate_culture_config.flag_val).alias(lactate_culture_config.flag_col)
            )
        )

        return df_infect

    def _detect_infection_with_code_sepsis_order(self) -> pl.DataFrame:
        logger.info("Detecting infection with code sepsis order criteria")
        code_sepsis_config = self.config.code_sepsis_config

        df_code_sepsis_page = self.df_all.filter(pl.col(self.config.grouper_col) == code_sepsis_config.diagnosis_grouper_val)\
            .select(
                pl.col(self.config.encounter_col),
                pl.col(self.config.event_dt_col).alias(code_sepsis_config.diagnosis_time_col)
            )\
        .with_columns(
            pl.lit(code_sepsis_config.flag_val).alias(code_sepsis_config.flag_col)
        )

        return df_code_sepsis_page
        # return detect_infection_with_code_sepsis_order(self.df_all)

    def _detect_infection_with_suspected_infection(self) -> pl.DataFrame:
        logger.info("Detecting infection with suspected infection criteria")
        suspected_infection_config = self.config.suspected_infection_flowsheet_config
        df_suspected_infection_grouper = self.df_all.filter(
            (pl.col(self.config.grouper_col) == suspected_infection_config.flowsheet_grouper_val)&
            (pl.col(self.config.raw_val_col) == suspected_infection_config.raw_val_col_value)
        ).select(
            pl.col(self.config.encounter_col),
            pl.col(self.config.event_dt_col).alias(self.config.suspected_infection_flowsheet_config.flowsheet_time_col)
        ).with_columns(
            pl.lit(suspected_infection_config.flag_val).alias(suspected_infection_config.flag_col)
        )
        return df_suspected_infection_grouper
        # return detect_infection_with_suspected_infection(self.df_all)
    
    def detect_infection_longframe(self):
        iv_dt_col = self.config.antibiotic_blood_culture_config.antibiotic_datetime_col
        culture_dt_col = self.config.antibiotic_blood_culture_config.blood_culture_datetime_col
        antibiotic_culture_longval = self.config.antibiotic_culture_longval # "IV+CULTURE"

        df_antibiotic_culture = self._detect_infection_with_antibiotic_culture()

        df_antibiotic_culture = df_antibiotic_culture.unpivot(
            on=[iv_dt_col, culture_dt_col],
            index = self.config.encounter_col,
            variable_name=self.config.variable_name_col,
            value_name=self.config.value_name_dt_col
        ).with_columns(pl.lit(antibiotic_culture_longval).alias(self.config.value_type_col))
        logger.info(f"Detected {df_antibiotic_culture.shape[0]} infections with antibiotic and culture criteria")

        lactate_dt_col = self.config.lactate_culture_config.lactate_datetime_col
        lactateculture_dt_col = self.config.lactate_culture_config.blood_culture_datetime_col
        lactate_culture_longval = self.config.lactate_culture_longval
        df_lactate_culture = self._detect_infection_with_lactate_culture()
        df_lactate_culture = df_lactate_culture.unpivot(
            on=[lactate_dt_col, lactateculture_dt_col],
            index = self.config.encounter_col,
            variable_name=self.config.variable_name_col,
            value_name=self.config.value_name_dt_col
        ).with_columns(pl.lit(lactate_culture_longval).alias(self.config.value_type_col))
        logger.info(f"Detected {df_lactate_culture.shape[0]} infections with lactate and culture criteria")

        codesepsis_dt_col = self.config.code_sepsis_config.diagnosis_time_col
        codesepsis_longval = "CODE_SEPSIS_ORDER"

        df_code_sepsis_order = self._detect_infection_with_code_sepsis_order()
        df_code_sepsis_order = df_code_sepsis_order.unpivot(
            on=[codesepsis_dt_col],
            index = self.config.encounter_col,
            variable_name=self.config.variable_name_col,
            value_name=self.config.value_name_dt_col
        ).with_columns(pl.lit(codesepsis_longval).alias(self.config.value_type_col))
        logger.info(f"Detected {df_code_sepsis_order.shape[0]} infections with code sepsis order criteria")


        flowsheet_dt_col = self.config.suspected_infection_flowsheet_config.flowsheet_time_col
        flowsheet_longval = self.config.flowsheet_longval

        df_suspected_infection = self._detect_infection_with_suspected_infection()

        df_suspected_infection = df_suspected_infection.unpivot(
            on=[flowsheet_dt_col],
            index = self.config.encounter_col,
            variable_name=self.config.variable_name_col,
            value_name=self.config.value_name_dt_col
        ).with_columns(pl.lit(flowsheet_longval).alias(self.config.value_type_col))

        logger.info(f"Detected {df_suspected_infection.shape[0]} infections with suspected infection criteria")

        logger.info("--------------------------------------------------------------------------------")
        logger.info("Combining infection detection results from all criteria")

        df_all_infection = pl.concat([df_antibiotic_culture, df_lactate_culture, df_code_sepsis_order, df_suspected_infection],
                                      how="vertical")
        # df_all_infection = df_antibiotic_culture.join(
        #     df_lactate_culture, on=self.config.encounter_col, how="outer", suffix=self.config.lactate_culture_suffix
        # ).join(
        #     df_code_sepsis_order, on=self.config.encounter_col, how="outer", suffix=self.config.diagnosis_codesepsis_suffix
        # ).join(
        #     df_suspected_infection, on=self.config.encounter_col, how="outer", suffix=self.config.flowsheet_infection_suffix
        # ).with_columns(
        #     pl.min_horizontal([self.config.antibiotic_blood_culture_config.first_time_ev_col, self.config.lactate_culture_config.first_time_ev_col, self.config.code_sepsis_config.diagnosis_time_col, self.config.suspected_infection_flowsheet_config.flowsheet_time_col]).alias(self.config.earliest_infection_time_col)
        # ).with_columns(
        #     pl.coalesce([self.config.encounter_col, f"{self.config.encounter_col}{self.config.lactate_culture_suffix}", f"{self.config.encounter_col}{self.config.diagnosis_codesepsis_suffix}", f"{self.config.encounter_col}{self.config.flowsheet_infection_suffix}"]).alias(self.config.encounter_col)
        # ).with_columns(
        #     pl.concat_str([self.config.antibiotic_blood_culture_config.flag_col, self.config.lactate_culture_config.flag_col, self.config.code_sepsis_config.flag_col, self.config.suspected_infection_flowsheet_config.flag_col],
        #                   separator="__", ignore_nulls=True).alias(self.config.infection_type_col)
        # ).with_columns(
        #     pl.when( pl.col(self.config.antibiotic_blood_culture_config.first_time_ev_col).is_not_null() &  (pl.col(self.config.antibiotic_blood_culture_config.first_time_ev_col) == pl.col(self.config.earliest_infection_time_col)) ).then(pl.col(self.config.antibiotic_blood_culture_config.flag_col))
        #     .when( pl.col(self.config.lactate_culture_config.first_time_ev_col).is_not_null() &  (pl.col(self.config.lactate_culture_config.first_time_ev_col) == pl.col(self.config.earliest_infection_time_col)) ).then(pl.col(self.config.lactate_culture_config.flag_col))
        #     .when( pl.col(self.config.code_sepsis_config.diagnosis_time_col).is_not_null() &  (pl.col(self.config.code_sepsis_config.diagnosis_time_col) == pl.col(self.config.earliest_infection_time_col)) ).then(pl.col(self.config.code_sepsis_config.flag_col))
        #     .when( pl.col(self.config.suspected_infection_flowsheet_config.flowsheet_time_col).is_not_null() &  (pl.col(self.config.suspected_infection_flowsheet_config.flowsheet_time_col) == pl.col(self.config.earliest_infection_time_col)) ).then(pl.col(self.config.suspected_infection_flowsheet_config.flag_col))
        #     .alias(self.config.earliest_infection_type_col)
        # )
        logger.info(f"Combined infection detection results has {df_all_infection.shape[0]} rows and columns: {df_all_infection.columns}")

        return df_all_infection

    def detect_infection(self):
        df_antibiotic_culture = self._detect_infection_with_antibiotic_culture()
        logger.info(f"Detected {df_antibiotic_culture.shape[0]} infections with antibiotic and culture criteria")
        df_lactate_culture = self._detect_infection_with_lactate_culture()
        logger.info(f"Detected {df_lactate_culture.shape[0]} infections with lactate and culture criteria")
        df_code_sepsis_order = self._detect_infection_with_code_sepsis_order()
        logger.info(f"Detected {df_code_sepsis_order.shape[0]} infections with code sepsis order criteria")
        df_suspected_infection = self._detect_infection_with_suspected_infection()
        logger.info(f"Detected {df_suspected_infection.shape[0]} infections with suspected infection criteria")

        logger.info("--------------------------------------------------------------------------------")
        logger.info("Combining infection detection results from all criteria")

        df_all_infection = df_antibiotic_culture.join(
            df_lactate_culture, on=self.config.encounter_col, how="outer", suffix=self.config.lactate_culture_suffix
        ).join(
            df_code_sepsis_order, on=self.config.encounter_col, how="outer", suffix=self.config.diagnosis_codesepsis_suffix
        ).join(
            df_suspected_infection, on=self.config.encounter_col, how="outer", suffix=self.config.flowsheet_infection_suffix
        ).with_columns(
            pl.min_horizontal([self.config.antibiotic_blood_culture_config.first_time_ev_col, self.config.lactate_culture_config.first_time_ev_col, self.config.code_sepsis_config.diagnosis_time_col, self.config.suspected_infection_flowsheet_config.flowsheet_time_col]).alias(self.config.earliest_infection_time_col)
        ).with_columns(
            pl.coalesce([self.config.encounter_col, f"{self.config.encounter_col}{self.config.lactate_culture_suffix}", f"{self.config.encounter_col}{self.config.diagnosis_codesepsis_suffix}", f"{self.config.encounter_col}{self.config.flowsheet_infection_suffix}"]).alias(self.config.encounter_col)
        ).with_columns(
            pl.concat_str([self.config.antibiotic_blood_culture_config.flag_col, self.config.lactate_culture_config.flag_col, self.config.code_sepsis_config.flag_col, self.config.suspected_infection_flowsheet_config.flag_col],
                          separator="__", ignore_nulls=True).alias(self.config.infection_type_col)
        ).with_columns(
            pl.when( pl.col(self.config.antibiotic_blood_culture_config.first_time_ev_col).is_not_null() &  (pl.col(self.config.antibiotic_blood_culture_config.first_time_ev_col) == pl.col(self.config.earliest_infection_time_col)) ).then(pl.col(self.config.antibiotic_blood_culture_config.flag_col))
            .when( pl.col(self.config.lactate_culture_config.first_time_ev_col).is_not_null() &  (pl.col(self.config.lactate_culture_config.first_time_ev_col) == pl.col(self.config.earliest_infection_time_col)) ).then(pl.col(self.config.lactate_culture_config.flag_col))
            .when( pl.col(self.config.code_sepsis_config.diagnosis_time_col).is_not_null() &  (pl.col(self.config.code_sepsis_config.diagnosis_time_col) == pl.col(self.config.earliest_infection_time_col)) ).then(pl.col(self.config.code_sepsis_config.flag_col))
            .when( pl.col(self.config.suspected_infection_flowsheet_config.flowsheet_time_col).is_not_null() &  (pl.col(self.config.suspected_infection_flowsheet_config.flowsheet_time_col) == pl.col(self.config.earliest_infection_time_col)) ).then(pl.col(self.config.suspected_infection_flowsheet_config.flag_col))
            .alias(self.config.earliest_infection_type_col)
        )
        logger.info(f"Combined infection detection results has {df_all_infection.shape[0]} rows and columns: {df_all_infection.columns}")

        return df_all_infection


if __name__ == "__main__":
    dl = DataLoader(data_config.data_path)
    df_all = dl.load_data()

    X = 0