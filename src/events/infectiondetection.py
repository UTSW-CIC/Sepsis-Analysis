import polars as pl
import duckdb
from src.dataloader import DataLoader
# from src.config import data_config
from src.utils.logger import get_logger
from src.configs.suspected_infection import SuspectedInfectionConfig



def detect_infection_with_antibiotic_culture(df_all: pl.DataFrame,
                    id_col: str = "EncounterEpicCsn",
                    event_dt_col: str = "Event_DateTime",
                    event_name_col: str = "Event_Name",
                    type_name:str = "IV Antibiotics",
                    event_grouper:str = "Blood Culture Order",
                    forward_tolerance:str = "24h", backward_tolerance:str = "72h",
                     ) -> pl.DataFrame:
    """
    IV antibiotics administered and blood culture ordered
    Blood culture 72 hours before or 24 hours after IV antibiotics administered
    """
    df_iv = df_all.filter(
        pl.col("Type")==type_name
    ).select(id_col, event_dt_col, event_name_col).rename({"Event_DateTime": "iv_dt", "Event_Name": "iv_name"})

    df_culture = df_all.filter(
        pl.col("Event_Grouper")==event_grouper
    ).select(id_col, event_dt_col, event_name_col).rename({"Event_DateTime": "culture_dt", "Event_Name": "culture_name"})

    df_forward = df_iv.join_asof(
        df_culture,
        left_on="iv_dt",
        right_on="culture_dt",
        by=id_col,
        strategy="forward",
        tolerance=forward_tolerance
    )

    df_backward = df_iv.join_asof(
        df_culture,
        left_on="iv_dt",
        right_on="culture_dt",
        by=id_col,
        strategy="backward",
        tolerance=backward_tolerance
    )

    df_infection_detection = pl.concat([df_backward, df_forward], how="vertical").unique()

    df_infect = df_infection_detection.group_by(id_col).agg(pl.col("iv_dt").min()).join(df_infection_detection.group_by("EncounterEpicCsn").agg(pl.col("culture_dt").min()), on="EncounterEpicCsn").with_columns(
        pl.min_horizontal(["iv_dt", "culture_dt"]).alias("first_ev_time_iv_culture")
    ).with_columns(
        pl.lit("antibiotic_lactate").alias("ev_type_iv_culture")
    )
    return df_infect

def detect_infection_with_lactate_culture(df_all: pl.DataFrame) -> pl.DataFrame:
    """
    Two blood culture orders within 6 hours of lactate order
    """
    df_culture = df_all.filter(
        pl.col("Event_Grouper")=="Blood Culture Order"
    ).select("EncounterEpicCsn", "Event_DateTime", "Event_Name").rename({"Event_DateTime": "culture_dt", "Event_Name": "culture_name"})

    df_lactate = df_all.filter(
        pl.col("Event_Grouper") == "Lactate"
    )

    df_lac_cult = duckdb.sql(
        """
        SELECT cul.EncounterEpicCsn, cul.culture_dt AS cul_dt, lac.Event_DateTime AS lac_dt
        FROM df_culture as cul
        LEFT JOIN df_lactate lac
        ON lac.EncounterEpicCsn=cul.EncounterEpicCsn
        AND lac.Event_DateTime >= cul.culture_dt - INTERVAL '6 hours'
        AND lac.Event_DateTime <= cul.culture_dt + INTERVAL '6 hours'
        """
    ).pl()

    df_lac_cult = df_lac_cult.drop_nulls(subset=["lac_dt", "cul_dt"])

    df_infect =df_lac_cult.group_by("EncounterEpicCsn").agg(pl.col("cul_dt").min()).\
        join(df_lac_cult.group_by("EncounterEpicCsn").agg(pl.col("lac_dt").min()), on="EncounterEpicCsn")\
            .with_columns(
        pl.min_horizontal(["cul_dt", "lac_dt"]).alias("first_ev_time_lactcult")
    ).with_columns(
        pl.lit("culture_lactate").alias("ev_type_lactcult")
    )

    return df_infect

def detect_infection_with_code_sepsis_order(df_all: pl.DataFrame) -> pl.DataFrame:

    """
    Code sepsis order exists
    """

    df_code_sepsis_page = df_all.filter(pl.col("Event_Grouper") == "Code Sepsis Page")\
        .select(
            pl.col("EncounterEpicCsn"),
            pl.col("Event_DateTime").alias("first_ev_time_codesepsis")
        )\
    .with_columns(
        pl.lit("code_sep_page").alias("ev_type_codesepsis")
    )

    return df_code_sepsis_page


def detect_infection_with_suspected_infection(df_all: pl.DataFrame) -> pl.DataFrame:

    """
    Suspected infection flowsheet with answer yes exists
    """
    df_suspected_infection_grouper = df_all.filter(
        (pl.col("Event_Grouper") == "Suspected Infection")&
        (pl.col("Value") == "Yes")
    ).select(
        pl.col("EncounterEpicCsn"),
        pl.col("Event_DateTime").alias("first_ev_time_flowsheet")
    ).with_columns(
        pl.lit("suspected_infection_flowsheet").alias("ev_type_flowsheet")
    )
    return df_suspected_infection_grouper


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
                      self.config.event_name_col: antibiotic_bculture_config.antibiotic_evname_col})

        df_culture = self.df_all.filter(
            pl.col(self.config.grouper_col)==antibiotic_bculture_config.blood_culture_grouper_val
        ).select(self.config.encounter_col, self.config.event_dt_col, self.config.event_name_col)\
            .rename({self.config.event_dt_col: antibiotic_bculture_config.blood_culture_datetime_col,
                     self.config.event_name_col: antibiotic_bculture_config.blood_culture_evname_col})

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

        df_infection_detection = pl.concat([df_backward, df_forward], how="vertical").unique()

        df_infect = df_infection_detection.group_by(self.config.encounter_col)\
            .agg(pl.col(antibiotic_bculture_config.antibiotic_datetime_col).min())\
            .join(df_infection_detection.group_by(self.config.encounter_col).agg(pl.col(antibiotic_bculture_config.blood_culture_datetime_col).min()), on=self.config.encounter_col).with_columns(
            pl.min_horizontal([antibiotic_bculture_config.antibiotic_datetime_col, antibiotic_bculture_config.blood_culture_datetime_col]).alias(antibiotic_bculture_config.first_time_ev_col)
        ).with_columns(
            pl.lit(antibiotic_bculture_config.flag_val).alias(antibiotic_bculture_config.flag_col)
        )
        return df_infect
        # return detect_infection_with_antibiotic_culture(self.df_all, **kwargs)

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

        df_infect =df_lac_cult.group_by(self.config.encounter_col).agg(pl.col(lactate_culture_config.blood_culture_datetime_col).min()).\
            join(df_lac_cult.group_by(self.config.encounter_col).agg(pl.col(lactate_culture_config.lactate_datetime_col).min()), on=self.config.encounter_col)\
                .with_columns(
            pl.min_horizontal([lactate_culture_config.blood_culture_datetime_col, lactate_culture_config.lactate_datetime_col]).alias(lactate_culture_config.first_time_ev_col)
        ).with_columns(
            pl.lit(lactate_culture_config.flag_val).alias(lactate_culture_config.flag_col)
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