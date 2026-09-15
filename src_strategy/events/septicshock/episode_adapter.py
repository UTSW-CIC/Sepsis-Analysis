"""Build exact septic-shock intervals and point evidence."""

from datetime import timedelta

import polars as pl

from ...configs.aggregator import FEATURE_REGISTRY, FeatureColumn
from ...configs.septicshock import (
    SepticShockConfig,
    SepticShockCriterionName,
    septicshock_config,
)
from ..episode_filter import build_state_episodes
from ..hypotension.effective_state import (
    EFFECTIVE_HYPOTENSION_FLAG,
    EPISODE_END,
    EPISODE_START,
    attach_effective_hypotension,
)
from .pipeline import build_septic_shock_pipeline


def _selected_features(config: SepticShockConfig) -> list[FeatureColumn]:
    feature_map = {
        SepticShockCriterionName.SBP_90: config.sbp90_criteria.sbp_col,
        SepticShockCriterionName.SBP_DELTA_40: (
            config.sbpdelta40_criteria.sbp_col
        ),
        SepticShockCriterionName.MAP_65: config.map65_criteria.map_col,
        SepticShockCriterionName.LACTATE_4: config.lactate4_criteria.lactate_col,
    }
    return list(
        dict.fromkeys(
            feature_map[criterion]
            for criterion in config.selected
            if criterion in feature_map
        )
    )


def _component_flag_cols(
    config: SepticShockConfig,
    *,
    use_filtered_hypotension: bool,
) -> list[str]:
    flag_map = {
        SepticShockCriterionName.SBP_90: config.sbp90_criteria.flag_col,
        SepticShockCriterionName.SBP_DELTA_40: (
            config.sbpdelta40_criteria.flag_col
        ),
        SepticShockCriterionName.MAP_65: config.map65_criteria.flag_col,
        SepticShockCriterionName.LACTATE_4: config.lactate4_criteria.flag_col,
        SepticShockCriterionName.VASOPRESSOR: (
            config.vasopressor_criteria.flag_col
        ),
    }
    columns = [flag_map[criterion] for criterion in config.selected]
    if use_filtered_hypotension and any(
        criterion
        in {
            SepticShockCriterionName.SBP_90,
            SepticShockCriterionName.SBP_DELTA_40,
            SepticShockCriterionName.MAP_65,
        }
        for criterion in config.selected
    ):
        columns.append(config.effective_hypotension_flag_col)
    return columns


def build_septic_shock_interval_segments(
    df_shock_input: pl.DataFrame,
    df_effective_hypotension_episodes: pl.DataFrame | None = None,
    *,
    use_filtered_hypotension: bool,
    config: SepticShockConfig = septicshock_config,
) -> pl.DataFrame:
    """Re-evaluate duration-bearing shock evidence at exact change points.

    Vasopressor administrations are deliberately set to zero here. They are
    represented separately as point evidence and never stretched into an
    interval ending at the next observed EHR timestamp.
    """
    encounter_col = config.encounter_col
    event_dt_col = config.event_dt_col
    features = _selected_features(config)
    feature_details: list[tuple[str, str, float]] = []
    for feature in features:
        definition = FEATURE_REGISTRY[feature]
        if definition.lookback_period is None:
            raise ValueError(
                f"Shock feature {feature.value!r} requires a validity period"
            )
        feature_details.append(
            (
                feature.value,
                f"{feature.value}_source_ts",
                float(definition.lookback_period),
            )
        )

    baseline_cols = []
    if SepticShockCriterionName.SBP_DELTA_40 in config.selected:
        baseline_cols.append(
            config.sbpdelta40_criteria.baseline_sbp_col.value
        )
    required = {
        encounter_col,
        event_dt_col,
        *baseline_cols,
        *[value_col for value_col, _, _ in feature_details],
        *[source_col for _, source_col, _ in feature_details],
    }
    missing = sorted(required.difference(df_shock_input.columns))
    if missing:
        raise ValueError(
            f"Shock interval input is missing required columns: {missing}"
        )

    component_cols = _component_flag_cols(
        config,
        use_filtered_hypotension=use_filtered_hypotension,
    )
    output_schema = {
        encounter_col: df_shock_input.schema[encounter_col],
        "state": pl.Int8,
        "segment_start": df_shock_input.schema[event_dt_col],
        "segment_end": df_shock_input.schema[event_dt_col],
        config.flag_col: pl.Int8,
        **{column: pl.Int8 for column in component_cols},
    }
    if df_shock_input.is_empty():
        return pl.DataFrame(schema=output_schema)
    if df_shock_input.select(
        pl.any_horizontal(
            pl.col([encounter_col, event_dt_col]).is_null()
        ).any()
    ).item():
        raise ValueError("Shock interval encounter and event timestamps cannot be null")
    duplicate_key_count = (
        df_shock_input.group_by(encounter_col, event_dt_col)
        .len()
        .filter(pl.col("len") > 1)
        .height
    )
    if duplicate_key_count:
        raise ValueError(
            "Shock interval input must have one row per encounter/timestamp; "
            f"found {duplicate_key_count} duplicate keys"
        )

    bounds = df_shock_input.group_by(encounter_col).agg(
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
    measurement_tables: list[
        tuple[str, str, str, float, pl.DataFrame]
    ] = []
    for value_col, source_ts_col, validity_minutes in feature_details:
        mismatched_pair_count = df_shock_input.filter(
            pl.col(value_col).is_null() != pl.col(source_ts_col).is_null()
        ).height
        if mismatched_pair_count:
            raise ValueError(
                f"Shock feature {value_col!r} has {mismatched_pair_count} "
                "rows with mismatched values and source timestamps"
            )
        measurement_ts_col = f"_{value_col}_measurement_time"
        measurements = (
            df_shock_input.select(
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
                f"Shock feature {value_col!r} has conflicting values at "
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
                            + pl.lit(
                                timedelta(minutes=validity_minutes)
                            )
                        ).alias("_change_time"),
                    ),
                ]
            )

    if use_filtered_hypotension:
        if df_effective_hypotension_episodes is None:
            raise ValueError(
                "Filtered shock intervals require effective hypotension episodes"
            )
        required_effective = {encounter_col, EPISODE_START, EPISODE_END}
        missing_effective = sorted(
            required_effective.difference(
                df_effective_hypotension_episodes.columns
            )
        )
        if missing_effective:
            raise ValueError(
                "Effective hypotension episodes are missing columns: "
                f"{missing_effective}"
            )
        change_point_frames.extend(
            [
                df_effective_hypotension_episodes.select(
                    encounter_col,
                    pl.col(EPISODE_START).alias("_change_time"),
                ),
                df_effective_hypotension_episodes.select(
                    encounter_col,
                    pl.col(EPISODE_END).alias("_change_time"),
                ),
            ]
        )

    points = (
        pl.concat(change_point_frames, how="vertical")
        .unique()
        .join(bounds, on=encounter_col, how="inner", validate="m:1")
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
                pl.lit(None, dtype=df_shock_input.schema[value_col]).alias(
                    value_col
                )
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
            .otherwise(pl.lit(None, dtype=df_shock_input.schema[value_col]))
            .alias(value_col),
            pl.col(measurement_ts_col).alias(source_ts_col),
        )

    if baseline_cols:
        conflicting_baselines = (
            df_shock_input.group_by(encounter_col)
            .agg(
                *[
                    pl.col(column)
                    .drop_nulls()
                    .n_unique()
                    .alias(column)
                    for column in baseline_cols
                ]
            )
            .filter(pl.any_horizontal(pl.col(baseline_cols) > 1))
            .height
        )
        if conflicting_baselines:
            raise ValueError(
                "Shock interval input contains conflicting encounter baselines"
            )
        baseline_values = df_shock_input.group_by(encounter_col).agg(
            *[
                pl.col(column).drop_nulls().first().alias(column)
                for column in baseline_cols
            ]
        )
        points = points.join(
            baseline_values,
            on=encounter_col,
            how="left",
            validate="m:1",
        )

    points = points.rename({"_change_time": event_dt_col})
    if use_filtered_hypotension:
        points = attach_effective_hypotension(
            points,
            df_effective_hypotension_episodes,
            encounter_col=encounter_col,
            event_dt_col=event_dt_col,
        )
    points = points.with_columns(
        pl.lit(0, dtype=pl.Int8).alias(
            config.vasopressor_criteria.administered_flag_col
        )
    )
    scored = build_septic_shock_pipeline(
        config,
        use_filtered_hypotension=use_filtered_hypotension,
    ).process(points)
    return (
        scored.with_columns(
            pl.col(config.flag_col).cast(pl.Int8).alias("state"),
            pl.col(event_dt_col).alias("segment_start"),
            pl.col(event_dt_col)
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


def build_septic_shock_interval_episodes(
    df_segments: pl.DataFrame,
    *,
    use_filtered_hypotension: bool,
    config: SepticShockConfig = septicshock_config,
) -> pl.DataFrame:
    """Collapse shock state segments and retain component evidence flags."""
    encounter_col = config.encounter_col
    component_cols = [
        column
        for column in _component_flag_cols(
            config,
            use_filtered_hypotension=use_filtered_hypotension,
        )
        if column in df_segments.columns
    ]
    raw = build_state_episodes(df_segments, encounter_col=encounter_col)
    evidence = (
        raw.select(
            encounter_col,
            "episode_id",
            "episode_start",
            "episode_end",
        )
        .join(df_segments, on=encounter_col, how="inner", validate="m:m")
        .filter(
            (pl.col("segment_start") >= pl.col("episode_start"))
            & (pl.col("segment_end") <= pl.col("episode_end"))
        )
        .group_by(encounter_col, "episode_id")
        .agg(*[pl.col(column).max().alias(column) for column in component_cols])
    )
    return (
        raw.join(
            evidence,
            on=[encounter_col, "episode_id"],
            how="left",
            validate="1:1",
        )
        .rename(
            {
                "episode_id": "shock_episode_id",
                "state": "shock_episode_state",
                "episode_start": "shock_episode_start",
                "episode_end": "shock_episode_end",
                "episode_duration_minutes": (
                    "shock_episode_duration_minutes"
                ),
            }
        )
        .sort(encounter_col, "shock_episode_start")
    )


def build_septic_shock_point_evidence(
    df_vasopressor_evidence: pl.DataFrame,
    *,
    config: SepticShockConfig = septicshock_config,
) -> pl.DataFrame:
    """Return one qualifying vasopressor point per encounter/timestamp."""
    criterion = config.vasopressor_criteria
    required = {
        config.encounter_col,
        config.event_dt_col,
        config.grouper_col,
        criterion.qualifying_dose_flag_col,
    }
    missing = sorted(required.difference(df_vasopressor_evidence.columns))
    if missing:
        raise ValueError(
            f"Shock point evidence is missing required columns: {missing}"
        )
    points = (
        df_vasopressor_evidence.filter(
            pl.col(criterion.qualifying_dose_flag_col) == 1
        )
        .group_by(config.encounter_col, config.event_dt_col)
        .agg(
            pl.len().cast(pl.Int64).alias("qualifying_vasopressor_dose_count"),
            pl.col(config.grouper_col)
            .unique()
            .sort()
            .alias("qualifying_vasopressor_groupers"),
        )
        .sort(config.encounter_col, config.event_dt_col)
        .with_columns(
            pl.int_range(1, pl.len() + 1)
            .over(config.encounter_col)
            .cast(pl.Int64)
            .alias("shock_point_id"),
            pl.lit("vasopressor_administration").alias("shock_point_type"),
        )
        .rename({config.event_dt_col: "shock_point_time"})
        .select(
            config.encounter_col,
            "shock_point_id",
            "shock_point_time",
            "shock_point_type",
            "qualifying_vasopressor_dose_count",
            "qualifying_vasopressor_groupers",
        )
    )
    return points
