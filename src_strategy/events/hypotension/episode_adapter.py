"""Build normalized blood-pressure hypotension segments.

This adapter reconstructs changes from rolling aggregated values and their
source timestamps. It deliberately does not read raw ``sys`` or ``map`` event
columns and does not apply episode-duration filtering itself.
"""

from datetime import timedelta

import polars as pl

from ...configs.aggregator import FEATURE_REGISTRY
from ...configs.septicshock import SepticShockConfig, septicshock_config


SBP_HYPOTENSION_FLAG = "sbp_hypotension_flag"
HYPOTENSION_FLAG = "hypotension_flag"
BASELINE_ROW_AVAILABLE = "baseline_encounter_row_available"


def _three_state_or(left_col: str, right_col: str, alias: str) -> pl.Expr:
    """Combine nullable 0/1 flags using clinical three-state OR semantics."""
    return (
        pl.when((pl.col(left_col) == 1) | (pl.col(right_col) == 1))
        .then(pl.lit(1, dtype=pl.Int8))
        .when((pl.col(left_col) == 0) & (pl.col(right_col) == 0))
        .then(pl.lit(0, dtype=pl.Int8))
        .otherwise(pl.lit(None, dtype=pl.Int8))
        .alias(alias)
    )


def build_bp_state_segments(
    df_aggregated: pl.DataFrame,
    df_encounters: pl.DataFrame,
    *,
    config: SepticShockConfig = septicshock_config,
) -> pl.DataFrame:
    """Reconstruct exact BP hypotension intervals from measurements and expiry.

    Inputs are the rolling aggregated SBP and directly measured MAP features,
    their source timestamps, and the encounter-level approved ``Baseline_SBP``.
    The encounter timeline is clipped to its first and last aggregated event.
    A state beginning at the last event has zero observable duration and is
    omitted.

    The returned normalized state is ``1`` for hypotension, ``0`` only when all
    applicable BP evidence is measured negative, and ``-1`` when no component
    is positive but evidence is insufficient to establish a negative state.
    """
    encounter_col = config.encounter_col
    event_dt_col = config.event_dt_col

    sbp_col = config.sbp90_criteria.sbp_col.value
    delta_sbp_col = config.sbpdelta40_criteria.sbp_col.value
    map_col = config.map65_criteria.map_col.value
    baseline_col = config.sbpdelta40_criteria.baseline_sbp_col.value
    sbp90_flag_col = config.sbp90_criteria.flag_col
    sbpdelta40_flag_col = config.sbpdelta40_criteria.flag_col
    map65_flag_col = config.map65_criteria.flag_col

    if delta_sbp_col != sbp_col:
        raise ValueError(
            "SBP <90 and SBP decline criteria must use the same aggregated feature"
        )
    feature_details: list[tuple[str, str, float]] = []
    for feature_col in (config.sbp90_criteria.sbp_col, config.map65_criteria.map_col):
        definition = FEATURE_REGISTRY[feature_col]
        if definition.lookback_period is None:
            raise ValueError(
                f"BP feature {feature_col.value!r} requires a validity period"
            )
        feature_details.append(
            (
                feature_col.value,
                f"{definition.alias}_source_ts",
                float(definition.lookback_period),
            )
        )

    sbp_source_col = feature_details[0][1]
    map_source_col = feature_details[1][1]
    required_aggregated = {
        encounter_col,
        event_dt_col,
        sbp_col,
        sbp_source_col,
        map_col,
        map_source_col,
    }
    missing_aggregated = sorted(
        required_aggregated.difference(df_aggregated.columns)
    )
    if missing_aggregated:
        raise ValueError(
            "BP episode input is missing required aggregated columns: "
            f"{missing_aggregated}"
        )

    required_encounter = {encounter_col, baseline_col}
    missing_encounter = sorted(required_encounter.difference(df_encounters.columns))
    if missing_encounter:
        raise ValueError(
            "BP encounter input is missing required columns: "
            f"{missing_encounter}"
        )

    output_schema = {
        encounter_col: df_aggregated.schema[encounter_col],
        "state": pl.Int8,
        "segment_start": df_aggregated.schema[event_dt_col],
        "segment_end": df_aggregated.schema[event_dt_col],
        sbp_col: df_aggregated.schema[sbp_col],
        sbp_source_col: df_aggregated.schema[sbp_source_col],
        baseline_col: df_encounters.schema[baseline_col],
        BASELINE_ROW_AVAILABLE: pl.Boolean,
        map_col: df_aggregated.schema[map_col],
        map_source_col: df_aggregated.schema[map_source_col],
        sbp90_flag_col: pl.Int8,
        sbpdelta40_flag_col: pl.Int8,
        SBP_HYPOTENSION_FLAG: pl.Int8,
        map65_flag_col: pl.Int8,
        HYPOTENSION_FLAG: pl.Int8,
    }
    if df_aggregated.is_empty():
        return pl.DataFrame(schema=output_schema)

    if df_aggregated.select(
        pl.any_horizontal(pl.col([encounter_col, event_dt_col]).is_null()).any()
    ).item():
        raise ValueError("BP encounter and event timestamps cannot be null")
    if df_encounters.select(pl.col(encounter_col).is_null().any()).item():
        raise ValueError("BP encounter identifiers cannot be null")

    duplicate_key_count = (
        df_aggregated.group_by(encounter_col, event_dt_col)
        .len()
        .filter(pl.col("len") > 1)
        .height
    )
    if duplicate_key_count:
        raise ValueError(
            "BP episode input must have one row per encounter/timestamp; "
            f"found {duplicate_key_count} duplicate keys"
        )

    duplicate_encounter_count = (
        df_encounters.group_by(encounter_col)
        .len()
        .filter(pl.col("len") > 1)
        .height
    )
    if duplicate_encounter_count:
        raise ValueError(
            "BP encounter input must have one row per encounter; "
            f"found {duplicate_encounter_count} duplicate encounter IDs"
        )

    bounds = df_aggregated.group_by(encounter_col).agg(
        pl.col(event_dt_col).min().alias("_encounter_start"),
        pl.col(event_dt_col).max().alias("_encounter_end"),
    )
    change_point_frames = [
        bounds.select(
            encounter_col,
            pl.col("_encounter_start").alias("_change_time"),
        ),
        bounds.select(
            encounter_col,
            pl.col("_encounter_end").alias("_change_time"),
        ),
    ]

    measurement_tables: list[tuple[str, str, str, float, pl.DataFrame]] = []
    for value_col, source_ts_col, validity_minutes in feature_details:
        mismatched_pair_count = df_aggregated.filter(
            pl.col(value_col).is_null() != pl.col(source_ts_col).is_null()
        ).height
        if mismatched_pair_count:
            raise ValueError(
                f"BP feature {value_col!r} has {mismatched_pair_count} rows "
                "with mismatched values and source timestamps"
            )

        future_source_count = df_aggregated.filter(
            pl.col(source_ts_col).is_not_null()
            & (pl.col(source_ts_col) > pl.col(event_dt_col))
        ).height
        if future_source_count:
            raise ValueError(
                f"BP feature {value_col!r} has {future_source_count} source "
                "timestamps after their backbone timestamp"
            )

        measurement_ts_col = f"_{value_col}_measurement_time"
        measurements = (
            df_aggregated.select(
                encounter_col,
                pl.col(source_ts_col).alias(measurement_ts_col),
                value_col,
            )
            .filter(pl.col(measurement_ts_col).is_not_null())
            .unique()
        )
        conflicting_measurement_count = (
            measurements.group_by(encounter_col, measurement_ts_col)
            .agg(pl.col(value_col).n_unique().alias("_value_count"))
            .filter(pl.col("_value_count") > 1)
            .height
        )
        if conflicting_measurement_count:
            raise ValueError(
                f"BP feature {value_col!r} has conflicting values at "
                f"{conflicting_measurement_count} encounter/timestamps"
            )
        measurements = measurements.unique(
            subset=[encounter_col, measurement_ts_col],
            keep="last",
        ).sort(encounter_col, measurement_ts_col)
        measurement_tables.append(
            (
                value_col,
                source_ts_col,
                measurement_ts_col,
                validity_minutes,
                measurements,
            )
        )

        if not measurements.is_empty():
            change_point_frames.extend(
                [
                    measurements.select(
                        encounter_col,
                        pl.col(measurement_ts_col).alias("_change_time"),
                    ),
                    measurements.select(
                        encounter_col,
                        (
                            pl.col(measurement_ts_col)
                            + pl.lit(timedelta(minutes=validity_minutes))
                        ).alias("_change_time"),
                    ),
                ]
            )

    points = (
        pl.concat(change_point_frames, how="vertical")
        .unique()
        .join(bounds, on=encounter_col, how="left")
        .filter(
            (pl.col("_change_time") >= pl.col("_encounter_start"))
            & (pl.col("_change_time") <= pl.col("_encounter_end"))
        )
        .drop("_encounter_start", "_encounter_end")
        .sort(encounter_col, "_change_time")
    )

    for (
        value_col,
        source_ts_col,
        measurement_ts_col,
        validity_minutes,
        measurements,
    ) in measurement_tables:
        if measurements.is_empty():
            points = points.with_columns(
                pl.lit(None, dtype=df_aggregated.schema[value_col]).alias(value_col),
                pl.lit(None, dtype=df_aggregated.schema[source_ts_col]).alias(
                    source_ts_col
                ),
            )
            continue

        valid_measurement = (
            pl.col(measurement_ts_col).is_not_null()
            & (
                pl.col("_change_time")
                < pl.col(measurement_ts_col)
                + pl.lit(timedelta(minutes=validity_minutes))
            )
        )
        points = points.join_asof(
            measurements,
            left_on="_change_time",
            right_on=measurement_ts_col,
            by=encounter_col,
            strategy="backward",
            check_sortedness=False,
        ).with_columns(
            pl.when(valid_measurement)
            .then(pl.col(value_col))
            .otherwise(pl.lit(None, dtype=df_aggregated.schema[value_col]))
            .alias(value_col),
            pl.when(valid_measurement)
            .then(pl.col(measurement_ts_col))
            .otherwise(pl.lit(None, dtype=df_aggregated.schema[source_ts_col]))
            .alias(source_ts_col),
        )

    points = points.join(
        df_encounters.select(encounter_col, baseline_col).with_columns(
            pl.lit(True).alias(BASELINE_ROW_AVAILABLE)
        ),
        on=encounter_col,
        how="left",
        validate="m:1",
    ).with_columns(pl.col(BASELINE_ROW_AVAILABLE).fill_null(False))

    scored = points.with_columns(
        pl.when(pl.col(sbp_col).is_null())
        .then(pl.lit(None, dtype=pl.Int8))
        .otherwise(
            (pl.col(sbp_col) < config.sbp90_criteria.sbp_threshold).cast(pl.Int8)
        )
        .alias(sbp90_flag_col),
        pl.when(pl.col(sbp_col).is_null() | pl.col(baseline_col).is_null())
        .then(pl.lit(None, dtype=pl.Int8))
        .otherwise(
            (
                (pl.col(baseline_col) - pl.col(sbp_col))
                > config.sbpdelta40_criteria.sbp_delta_threshold
            ).cast(pl.Int8)
        )
        .alias(sbpdelta40_flag_col),
        pl.when(pl.col(map_col).is_null())
        .then(pl.lit(None, dtype=pl.Int8))
        .otherwise(
            (pl.col(map_col) < config.map65_criteria.map_threshold).cast(pl.Int8)
        )
        .alias(map65_flag_col),
    ).with_columns(
        _three_state_or(
            sbp90_flag_col,
            sbpdelta40_flag_col,
            SBP_HYPOTENSION_FLAG,
        )
    ).with_columns(
        _three_state_or(SBP_HYPOTENSION_FLAG, map65_flag_col, HYPOTENSION_FLAG)
    )

    return (
        scored.with_columns(
            pl.when(pl.col(HYPOTENSION_FLAG).is_null())
            .then(pl.lit(-1, dtype=pl.Int8))
            .otherwise(pl.col(HYPOTENSION_FLAG))
            .alias("state"),
            pl.col("_change_time").alias("segment_start"),
            pl.col("_change_time")
            .shift(-1)
            .over(encounter_col)
            .alias("segment_end"),
        )
        .filter(
            pl.col("segment_end").is_not_null()
            & (pl.col("segment_end") > pl.col("segment_start"))
        )
        .select(output_schema.keys())
        .sort(encounter_col, "segment_start")
    )
