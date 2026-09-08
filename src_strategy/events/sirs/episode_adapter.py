"""Build normalized SIRS state segments for the shared episode filter."""

from datetime import timedelta

import polars as pl

from ...configs.aggregator import FEATURE_REGISTRY, FeatureColumn
from ...configs.sirscalculator import SIRSConfig, sirs_config
from .pipeline import build_sirs_pipeline


def _sirs_features(config: SIRSConfig) -> list[FeatureColumn]:
    return [
        config.temp_feature_col,
        config.hr_feature_col,
        config.resp_feature_col,
        config.wbc_feature_col,
    ]


def build_sirs_state_segments(
    df_sirs: pl.DataFrame,
    *,
    config: SIRSConfig = sirs_config,
    positive_threshold: int = 2,
) -> pl.DataFrame:
    """Reconstruct exact SIRS intervals from measurements and expirations.

    The encounter timeline starts and ends at its first and last backbone rows.
    A state beginning at the last row has no observable duration and is omitted.
    The returned state contract is ``1`` positive, ``0`` negative, and ``-1``
    when the SIRS score is null.
    """
    encounter_col = config.encounter_col
    event_dt_col = config.event_dt_col
    features = _sirs_features(config)

    feature_details: list[tuple[str, str, float]] = []
    for feature_col in features:
        definition = FEATURE_REGISTRY[feature_col]
        if definition.lookback_period is None:
            raise ValueError(
                f"SIRS feature {feature_col.value!r} requires a validity period"
            )
        value_col = feature_col.value
        source_ts_col = f"{definition.alias}_source_ts"
        feature_details.append(
            (value_col, source_ts_col, float(definition.lookback_period))
        )

    required = {
        encounter_col,
        event_dt_col,
        *[value_col for value_col, _, _ in feature_details],
        *[source_col for _, source_col, _ in feature_details],
    }
    missing = sorted(required.difference(df_sirs.columns))
    if missing:
        raise ValueError(f"SIRS episode input is missing required columns: {missing}")

    output_schema = {
        encounter_col: df_sirs.schema[encounter_col],
        "state": pl.Int8,
        "segment_start": df_sirs.schema[event_dt_col],
        "segment_end": df_sirs.schema[event_dt_col],
        config.sirs_score_col: pl.Int64,
    }
    if df_sirs.is_empty():
        return pl.DataFrame(schema=output_schema)

    if df_sirs.select(
        pl.any_horizontal(
            pl.col([encounter_col, event_dt_col]).is_null()
        ).any()
    ).item():
        raise ValueError("SIRS encounter and event timestamps cannot be null")

    duplicate_key_count = (
        df_sirs.group_by(encounter_col, event_dt_col)
        .len()
        .filter(pl.col("len") > 1)
        .height
    )
    if duplicate_key_count:
        raise ValueError(
            "SIRS episode input must have one row per encounter/timestamp; "
            f"found {duplicate_key_count} duplicate keys"
        )

    bounds = df_sirs.group_by(encounter_col).agg(
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

    measurement_tables: list[tuple[str, str, float, pl.DataFrame]] = []
    for value_col, source_ts_col, validity_minutes in feature_details:
        mismatched_pair_count = df_sirs.filter(
            pl.col(value_col).is_null() != pl.col(source_ts_col).is_null()
        ).height
        if mismatched_pair_count:
            raise ValueError(
                f"SIRS feature {value_col!r} has {mismatched_pair_count} rows "
                "with mismatched values and source timestamps"
            )

        measurement_ts_col = f"_{value_col}_measurement_time"
        measurements = (
            df_sirs.select(
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
                f"SIRS feature {value_col!r} has conflicting values at "
                f"{conflicting_measurement_count} encounter/timestamps"
            )
        measurements = measurements.unique(
            subset=[encounter_col, measurement_ts_col],
            keep="last",
        ).sort(encounter_col, measurement_ts_col)
        measurement_tables.append(
            (value_col, measurement_ts_col, validity_minutes, measurements)
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
        measurement_ts_col,
        validity_minutes,
        measurements,
    ) in measurement_tables:
        if measurements.is_empty():
            points = points.with_columns(
                pl.lit(None, dtype=df_sirs.schema[value_col]).alias(value_col)
            )
            continue

        points = points.join_asof(
            measurements,
            left_on="_change_time",
            right_on=measurement_ts_col,
            by=encounter_col,
            strategy="backward",
            check_sortedness=False,
        ).with_columns(
            pl.when(
                pl.col(measurement_ts_col).is_not_null()
                & (
                    pl.col("_change_time")
                    < pl.col(measurement_ts_col)
                    + pl.lit(timedelta(minutes=validity_minutes))
                )
            )
            .then(pl.col(value_col))
            .otherwise(pl.lit(None, dtype=df_sirs.schema[value_col]))
            .alias(value_col)
        )

    scored = build_sirs_pipeline(config).process(points)
    segments = (
        scored.with_columns(
            pl.when(pl.col(config.sirs_score_col).is_null())
            .then(pl.lit(-1))
            .when(pl.col(config.sirs_score_col) >= positive_threshold)
            .then(pl.lit(1))
            .otherwise(pl.lit(0))
            .cast(pl.Int8)
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
    return segments
