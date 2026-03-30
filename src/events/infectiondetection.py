import polars as pl
import duckdb
from src.dataloader import DataLoader
from src.config import data_config
from src.utils.logger import get_logger


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
    def __init__(self, df_all: pl.DataFrame):
        self.df_all = df_all

    def _detect_infection_with_antibiotic_culture(self, **kwargs) -> pl.DataFrame:
        logger.info("Detecting infection with antibiotic and culture criteria")
        return detect_infection_with_antibiotic_culture(self.df_all, **kwargs)

    def _detect_infection_with_lactate_culture(self) -> pl.DataFrame:
        logger.info("Detecting infection with lactate and culture criteria")
        return detect_infection_with_lactate_culture(self.df_all)

    def _detect_infection_with_code_sepsis_order(self) -> pl.DataFrame:
        logger.info("Detecting infection with code sepsis order criteria")
        return detect_infection_with_code_sepsis_order(self.df_all)

    def _detect_infection_with_suspected_infection(self) -> pl.DataFrame:
        logger.info("Detecting infection with suspected infection criteria")
        return detect_infection_with_suspected_infection(self.df_all)
    
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
            df_lactate_culture, on="EncounterEpicCsn", how="outer", suffix="_lactcult"
        ).join(
            df_code_sepsis_order, on="EncounterEpicCsn", how="outer", suffix="_codesepsis"
        ).join(
            df_suspected_infection, on="EncounterEpicCsn", how="outer", suffix="_suspectedinfection"
        ).with_columns(
            pl.min_horizontal(["first_ev_time_iv_culture", "first_ev_time_lactcult", "first_ev_time_codesepsis", "first_ev_time_flowsheet"]).alias("infection_time")
        ).with_columns(
            pl.coalesce(["EncounterEpicCsn", "EncounterEpicCsn_lactcult", "EncounterEpicCsn_codesepsis", "EncounterEpicCsn_suspectedinfection"]).alias("EncounterEpicCsn")
        ).with_columns(
            pl.concat_str(["ev_type_iv_culture", "ev_type_lactcult", "ev_type_codesepsis", "ev_type_flowsheet"],
                          separator="__", ignore_nulls=True).alias("infection_ev_type")
        ).with_columns(
            pl.when( pl.col("first_ev_time_iv_culture").is_not_null() &  (pl.col("first_ev_time_iv_culture") == pl.col("infection_time")) ).then(pl.col("ev_type_iv_culture"))
            .when( pl.col("first_ev_time_lactcult").is_not_null() &  (pl.col("first_ev_time_lactcult") == pl.col("infection_time")) ).then(pl.col("ev_type_lactcult"))
            .when( pl.col("first_ev_time_codesepsis").is_not_null() &  (pl.col("first_ev_time_codesepsis") == pl.col("infection_time")) ).then(pl.col("ev_type_codesepsis"))
            .when( pl.col("first_ev_time_flowsheet").is_not_null() &  (pl.col("first_ev_time_flowsheet") == pl.col("infection_time")) ).then(pl.col("ev_type_flowsheet"))
            .alias("first_ev_type")
        )
        logger.info(f"Combined infection detection results has {df_all_infection.shape[0]} rows and columns: {df_all_infection.columns}")

        return df_all_infection


if __name__ == "__main__":
    dl = DataLoader(data_config.data_path)
    df_all = dl.load_data()

    X = 0