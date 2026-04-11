import polars as pl
import duckdb
from typing import List
from datetime import timedelta
from src.config import AggregatorConfig
import os


def join_baselines_2_agg(df_agg: pl.DataFrame, df_all: pl.DataFrame,
                         encounter_col: str, baseline_cols: List[str], logger=None) -> pl.DataFrame:
    if logger:
        logger.info(f"Joining baseline values to aggregated dataframe. Baseline columns: {baseline_cols}")
    df_baselines = df_all.group_by(encounter_col)\
        .agg([pl.col(c).last() for c in baseline_cols])
    df_agg_baselines = duckdb.sql(f"""
        SELECT df_agg.*, df_baselines.*
        FROM df_agg
        LEFT JOIN df_baselines
        ON df_agg.{encounter_col} = df_baselines.{encounter_col}
    """).pl()
    return df_agg_baselines

def rolling_agg(
    reference: pl.DataFrame,
    events: pl.DataFrame,        # pre-filtered, must have: encounter_col, evt_dt, evt_val
    agg_col_name: str,
    agg_func: str = "max",
    lookback_period: float | timedelta = 24.0*60,
    encounter_col: str = "EncounterEpicCsn",
) -> pl.DataFrame:
    """
    For each row in reference, look back `lookback_period` hours into events
    and compute the aggregate of evt_val.

    Parameters
    ----------
    reference : unique (encounter, Event_DateTime) pairs — the left table
    events : pre-filtered events with columns [encounter_col, evt_dt, evt_val]
    agg_col_name : name of the output column
    agg_func : "max", "min", or "last"
    lookback_period : hours to look back (float), or a timedelta
    encounter_col : name of the encounter ID column

    Returns
    -------
    reference with one new column added
    """
    if isinstance(lookback_period, (int, float)):
        lookback_period = timedelta(minutes=lookback_period)

    interval_str = f"{int(lookback_period.total_seconds())} seconds"

    if agg_func == "max":
        agg_expr = "MAX(events.evt_val)"
    elif agg_func == "min":
        agg_expr = "MIN(events.evt_val)"
    elif agg_func == "last":
        agg_expr = "LAST(events.evt_val ORDER BY events.evt_dt)"
    else:
        raise ValueError(f"Unknown agg_func: '{agg_func}'. Choose from: max, min, last")

    return duckdb.sql(f"""
        SELECT
            reference.{encounter_col},
            reference.Event_DateTime,
            {agg_expr} AS {agg_col_name}
        FROM reference
        LEFT JOIN events
            ON reference.{encounter_col} = events.{encounter_col}
            AND events.evt_dt < reference.Event_DateTime
            AND events.evt_dt >= reference.Event_DateTime - INTERVAL '{interval_str}'
        GROUP BY
            reference.{encounter_col},
            reference.Event_DateTime
    """).pl()

def extract_systolic_bp(df_all: pl.DataFrame,
                        config: AggregatorConfig = None,
                        **kwargs
                        ) -> pl.DataFrame:
    """
    Extract systolic blood pressure from Blood Pressure events in df_all.
    Assumes Value is in the format "120/80" and extracts the first number.
    """
    if config is None:
        encounter_col  = kwargs.get("encounter_col", "EncounterEpicCsn")
        event_dt_col = kwargs.get("event_dt_col", "Event_DateTime")
        event_grouper_col = kwargs.get("event_grouper_col", "Event_Grouper")
        bp_grouper_val = kwargs.get("bp_grouper_val", "Blood Pressure")
        sys_col_name = kwargs.get("sys_col_name", "sys")
        val_col = kwargs.get("val_col", "Value")
    else:
        encounter_col = config.encounter_col
        event_dt_col = config.event_dt_col
        event_grouper_col = config.grouper_col
        bp_grouper_val = config.blood_pressure_config.bp_grouper_val
        sys_col_name = config.blood_pressure_config.sys_col
        val_col = config.blood_pressure_config.bp_val_col

    df_sys = df_all.filter(pl.col(event_grouper_col) == bp_grouper_val).with_columns(
            pl.col(val_col).str.split('/').list.first().cast(pl.Int64).alias(sys_col_name)
        ).select(
            pl.col(encounter_col),
            pl.col(event_dt_col),
            pl.col(sys_col_name)
        )
    return df_sys


def save_df(df: pl.DataFrame, output_path: str, file_name: str, logger=None, message: str = ""):
    if logger:
        logger.info(f"Saving dataframe to {output_path}/{file_name}") if message == "" else logger.info(message+f" Saving dataframe to {output_path}/{file_name}")
    output_file = f"{output_path}/{file_name}"
    df.write_parquet(output_file)


def load_df( input_path: str, file_name: str, logger=None):
    if logger:
        logger.info(f"Loading dataframe from {input_path}/{file_name}") 
    input_file = f"{input_path}/{file_name}"
    return pl.read_parquet(input_file)

def load_output_folder(output_path: str, logger=None) -> dict[str, pl.DataFrame]:
    if logger:
        logger.info(f"Loading dataframes from {output_path}") 
    df_dict = {}
    for file in os.listdir(output_path):
        if file.endswith(".parquet"):
            fname = file.split(".")[0]
            df_dict[fname] = pl.read_parquet(os.path.join(output_path, file))
    return df_dict