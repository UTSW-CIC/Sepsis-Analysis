import polars as pl
import duckdb
from typing import List
from datetime import timedelta
from src.config import AggregatorConfig
import os
import re



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


def compare_column_between_two_dfs(df1: pl.DataFrame, df2: pl.DataFrame, factor_col_name: str, enc_id: str,
                                   val_col_name: str, df1_name: str, df2_name: str,
                                   expr_diff: pl.Expr,
                                   logger=None):
    df_comp = pl.concat([
        df1.select([pl.col(enc_id).alias(f'{df1_name}_{enc_id}'),
                           pl.col(factor_col_name).alias(f'{df1_name}_{factor_col_name}'),
                            pl.col(val_col_name).alias(f'{df1_name}_{val_col_name}')]),
        df2.select([pl.col(enc_id).alias(f'{df2_name}_{enc_id}'),
                           pl.col(factor_col_name).alias(f'{df2_name}_{factor_col_name}'),
                            pl.col(val_col_name).alias(f'{df2_name}_{val_col_name}')])
    ], how='horizontal')

    return df_comp.filter(
        expr_diff
    )[f'{df1_name}_{factor_col_name}'].value_counts()


def forward_fill_within_timeinterval(df: pl.DataFrame, group_col: str, time_col: str,
                                     val_col: str, max_interval: timedelta) -> pl.DataFrame:
    df_filled = df.with_columns(
        pl.when()
    ) 



def convert_bp_to_sbp_in_numerivalue_col(df: pl.DataFrame, 
        type_col: str = "Type",
        type_val: str = "Flowsheet",
        grouper_col: str = "Event_Grouper",
        grouper_val: str = "Blood Pressure",
        raw_val_col: str = "Value",
        val_col: str = "NumericValue") -> pl.DataFrame:
    # TODO: Remove the hardcoded names, and use config or arguments to the functions
    return df.with_columns(
        pl.when(
            (pl.col(type_col) == type_val)&
            (pl.col(grouper_col) == grouper_val)&
            (pl.col(raw_val_col).is_not_null())
        ).then(
            pl.col(raw_val_col).str.split('/').list.get(0).cast(pl.Int64, strict=False)
        ).otherwise(pl.col(val_col)).alias(val_col)
    )



def _safe_identifier(name: str) -> str:
    """
    Validates that a string is safe to use as a SQL identifier.
    Allows only letters, digits, and underscores, and must start
    with a letter or underscore.
    """
    if not re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', name):
        raise ValueError(
            f"Unsafe SQL identifier: {name!r}. "
            f"Only alphanumeric characters and underscores are allowed."
        )
    return name

def rolling_agg(
    reference: pl.DataFrame,
    events: pl.DataFrame,        # pre-filtered, must have: encounter_col, evt_dt, evt_val
    agg_col_name: str,
    agg_func: str = "max",
    lookback_period: float | timedelta = 24.0*60,
    encounter_col: str = "EncounterEpicCsn",
    ref_dt_col: str = "Event_DateTime",      # NEW
    evt_dt_col: str = "evt_dt",              # NEW
    evt_val_col: str = "evt_val",            # NEW
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

    # --- Sanitize identifiers ---
    encounter_col = _safe_identifier(encounter_col)
    agg_col_name = _safe_identifier(agg_col_name)
    ref_dt_col = _safe_identifier(ref_dt_col)
    evt_dt_col = _safe_identifier(evt_dt_col)
    evt_val_col = _safe_identifier(evt_val_col)

    agg_map = {
        "max":   f"MAX(events_tbl.{evt_val_col})",
        "min":   f"MIN(events_tbl.{evt_val_col})",
        "mean":  f"AVG(events_tbl.{evt_val_col})",
        "sum":   f"SUM(events_tbl.{evt_val_col})",
        "count": f"COUNT(events_tbl.{evt_val_col})",
        "last":  f"LAST(events_tbl.{evt_val_col} ORDER BY events_tbl.{evt_dt_col})",
        "first": f"FIRST(events_tbl.{evt_val_col} ORDER BY events_tbl.{evt_dt_col})",
    }

    agg_expr = agg_map.get(agg_func.lower())
    if agg_expr is None:
        supported = ", ".join(sorted(agg_map.keys()))
        raise ValueError(
            f"Unknown agg_func: '{agg_func}'. Supported functions: {supported}"
        )

    # if agg_func == "max":
    #     agg_expr = "MAX(events.evt_val)"
    # elif agg_func == "min":
    #     agg_expr = "MIN(events.evt_val)"
    # elif agg_func == "last":
    #     agg_expr = "LAST(events.evt_val ORDER BY events.evt_dt)"
    # else:
    #     raise ValueError(f"Unknown agg_func: '{agg_func}'. Choose from: max, min, last")

    # return duckdb.sql(f"""
    #     SELECT
    #         reference.{encounter_col},
    #         reference.Event_DateTime,
    #         {agg_expr} AS {agg_col_name}
    #     FROM reference
    #     LEFT JOIN events
    #         ON reference.{encounter_col} = events.{encounter_col}
    #         AND events.evt_dt < reference.Event_DateTime
    #         AND events.evt_dt >= reference.Event_DateTime - INTERVAL '{interval_str}'
    #     GROUP BY
    #         reference.{encounter_col},
    #         reference.Event_DateTime
    # """).pl()

    with duckdb.connect() as conn:
        conn.register("reference_tbl", reference)
        conn.register("events_tbl", events)
        
        result =  conn.sql(f"""
            SELECT
                reference_tbl.{encounter_col},
                reference_tbl.{ref_dt_col},
                {agg_expr} AS {agg_col_name}
            FROM reference_tbl
            LEFT JOIN events_tbl
                ON reference_tbl.{encounter_col} = events_tbl.{encounter_col}
                AND events_tbl.{evt_dt_col} <= reference_tbl.{ref_dt_col}
                AND events_tbl.{evt_dt_col} >= reference_tbl.{ref_dt_col} - INTERVAL '{interval_str}'
            GROUP BY
                reference_tbl.{encounter_col},
                reference_tbl.{ref_dt_col}
        """).pl()
    return result

def extract_arterial_blood_pressure_mean(df_all: pl.DataFrame,
                                         config: AggregatorConfig = None,
                                         **kwargs
                                         ) -> pl.DataFrame:
    """
    Robustly parse BP strings and compute MAP, handling dirty data gracefully.
    Invalid or unparseable values result in null MAP.
    """
    if config is None:
        encounter_col  = kwargs.get("encounter_col", "EncounterEpicCsn")
        event_dt_col = kwargs.get("event_dt_col", "Event_DateTime")
        event_grouper_col = kwargs.get("event_grouper_col", "Event_Grouper")
        bp_grouper_val = kwargs.get("bp_grouper_val", "Blood Pressure")
        sys_col_name = kwargs.get("sys_col", "sys")
        dia_col_name = kwargs.get("dia_col", "dia")
        map_col_name = kwargs.get("map_col", "map")
        val_col = kwargs.get("val_col", "Value")
    else:
        encounter_col = config.encounter_col
        event_dt_col = config.event_dt_col
        event_grouper_col = config.grouper_col
        bp_grouper_val = config.blood_pressure_config.bp_grouper_val
        sys_col_name = config.blood_pressure_config.sys_col
        dia_col_name = config.blood_pressure_config.dia_col
        map_col_name = config.blood_pressure_config.map_col
        val_col = config.blood_pressure_config.bp_val_col

    return df_all.filter(pl.col(event_grouper_col) == bp_grouper_val).with_columns(
        # Strip whitespace, then split
        pl.col(val_col).str.strip_chars().str.split("/").alias("_bp_parts")
    ).with_columns(
        # Only extract if we have at least 2 parts
        pl.when(pl.col("_bp_parts").list.len() >= 2)
          .then(pl.col("_bp_parts").list.get(0).str.strip_chars().cast(pl.Float64, strict=False))
          .otherwise(None)
          .alias(sys_col_name),

        pl.when(pl.col("_bp_parts").list.len() >= 2)
          .then(pl.col("_bp_parts").list.get(1).str.strip_chars().cast(pl.Float64, strict=False))
          .otherwise(None)
          .alias(dia_col_name),
    ).with_columns(
        # MAP is only valid if both SBP and DBP are non-null and physiologically plausible
        pl.when(
            pl.col(sys_col_name).is_not_null()
            & pl.col(dia_col_name).is_not_null()
            & (pl.col(sys_col_name) > 0)
            & (pl.col(dia_col_name) > 0)
            & (pl.col(sys_col_name) >= pl.col(dia_col_name))  # SBP should be ≥ DBP
        )
        .then(((pl.col(sys_col_name) + 2 * pl.col(dia_col_name)) / 3).round(1))
        .otherwise(None)
        .alias(map_col_name)
    ).drop("_bp_parts").select(
            pl.col(encounter_col),
            pl.col(event_dt_col),
            pl.col(map_col_name)
        )


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