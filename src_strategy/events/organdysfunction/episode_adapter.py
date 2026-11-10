"""Build exact organ-dysfunction intervals from six-organ evidence."""

from datetime import timedelta

import polars as pl

from ...configs.aggregator import (
    FEATURE_REGISTRY,
    FeatureColumn,
    source_provenance_cols,
)
from ...configs.organdysfunction import (
    OrganDysfunctionConfig,
    OrganDysfunctionCriterionName,
    organdysfunction_config,
)
from ...configs.pulmonarydysfunction import (
    PulmonaryDysfunctionConfig,
    pulmonary_dysfunction_config,
)
from ..episode_filter import build_state_episodes
from .pipeline import build_organ_dysfunction_pipeline


def _selected_features(config: OrganDysfunctionConfig) -> list[FeatureColumn]:
    feature_map = {
        OrganDysfunctionCriterionName.CARDIOVASCULAR: [
            config.cardiovascular.lactate_col
        ],
        OrganDysfunctionCriterionName.RENAL: [
            config.renal.creatinine_col,
            config.renal.egfr_col,
        ],
        OrganDysfunctionCriterionName.HEPATIC: [
            config.hepatic.bilirubin_col
        ],
        OrganDysfunctionCriterionName.COAGULATION: [
            config.coagulation.platelets_col,
            config.coagulation.inr_col,
            config.coagulation.aptt_col,
        ],
        OrganDysfunctionCriterionName.NEUROLOGICAL: [
            config.neurological.gcs_col
        ],
        OrganDysfunctionCriterionName.PULMONARY: [],
    }
    return [
        feature
        for criterion in config.selected
        for feature in feature_map[criterion]
    ]


def _selected_baselines(config: OrganDysfunctionConfig) -> list[str]:
    baseline_map = {
        OrganDysfunctionCriterionName.RENAL: [
            config.renal.baseline_creatinine_col.value,
            config.renal.baseline_egfr_col.value,
        ],
        OrganDysfunctionCriterionName.HEPATIC: [
            config.hepatic.baseline_bilirubin_col.value
        ],
        OrganDysfunctionCriterionName.COAGULATION: [
            config.coagulation.baseline_platelets_col.value
        ],
    }
    return list(
        dict.fromkeys(
            baseline
            for criterion in config.selected
            for baseline in baseline_map.get(criterion, [])
        )
    )


def _selected_failure_cols(config: OrganDysfunctionConfig) -> list[str]:
    failure_map = {
        OrganDysfunctionCriterionName.CARDIOVASCULAR: (
            config.cardiovascular.flag_col
        ),
        OrganDysfunctionCriterionName.PULMONARY: config.pulmonary.flag_col,
        OrganDysfunctionCriterionName.RENAL: config.renal.flag_col,
        OrganDysfunctionCriterionName.HEPATIC: config.hepatic.flag_col,
        OrganDysfunctionCriterionName.COAGULATION: config.coagulation.flag_col,
        OrganDysfunctionCriterionName.NEUROLOGICAL: (
            config.neurological.flag_col
        ),
    }
    return [failure_map[criterion] for criterion in config.selected]


def _feature_failure_col(
    feature: FeatureColumn,
    config: OrganDysfunctionConfig,
) -> str:
    feature_map = {
        config.cardiovascular.lactate_col: config.cardiovascular.flag_col,
        config.renal.creatinine_col: config.renal.flag_col,
        config.renal.egfr_col: config.renal.flag_col,
        config.hepatic.bilirubin_col: config.hepatic.flag_col,
        config.coagulation.platelets_col: config.coagulation.flag_col,
        config.coagulation.inr_col: config.coagulation.flag_col,
        config.coagulation.aptt_col: config.coagulation.flag_col,
        config.neurological.gcs_col: config.neurological.flag_col,
    }
    return feature_map[feature]


def _feature_evidence_col(
    feature: FeatureColumn,
    config: OrganDysfunctionConfig,
) -> str:
    return f"{feature.value}{config.source_evidence_suffix}"


def build_organ_dysfunction_state_segments(
    df_organ_input: pl.DataFrame,
    df_pulmonary_timeline: pl.DataFrame | None = None,
    *,
    config: OrganDysfunctionConfig = organdysfunction_config,
    pulmonary_config: PulmonaryDysfunctionConfig = (
        pulmonary_dysfunction_config
    ),
) -> pl.DataFrame:
    """Re-evaluate organ state at measurements, expirations, and lung changes."""
    encounter_col = config.encounter_col
    event_dt_col = config.event_dt_col
    features = _selected_features(config)
    baselines = _selected_baselines(config)
    failure_cols = _selected_failure_cols(config)
    feature_details: list[tuple[FeatureColumn, str, list[str], float]] = []
    for feature in features:
        definition = FEATURE_REGISTRY[feature]
        if definition.lookback_period is None:
            raise ValueError(
                f"Organ feature {feature.value!r} requires a validity period"
            )
        feature_details.append(
            (
                feature,
                feature.value,
                source_provenance_cols(feature.value),
                float(definition.lookback_period),
            )
        )

    required = {
        encounter_col,
        event_dt_col,
        *baselines,
        *[value_col for _, value_col, _, _ in feature_details],
        *[
            source_col
            for _, _, provenance_cols, _ in feature_details
            for source_col in provenance_cols
        ],
    }
    missing = sorted(required.difference(df_organ_input.columns))
    if missing:
        raise ValueError(
            f"Organ episode input is missing required columns: {missing}"
        )

    pulmonary_selected = (
        OrganDysfunctionCriterionName.PULMONARY in config.selected
    )
    feature_output_cols = [
        column
        for _, value_col, provenance_cols, _ in feature_details
        for column in [value_col, *provenance_cols]
    ]
    output_schema = {
        encounter_col: df_organ_input.schema[encounter_col],
        "state": pl.Int8,
        "segment_start": df_organ_input.schema[event_dt_col],
        "segment_end": df_organ_input.schema[event_dt_col],
        config.flag_col: pl.Int64,
        **{column: pl.Int8 for column in failure_cols},
        **{column: df_organ_input.schema[column] for column in baselines},
        **{
            column: df_organ_input.schema[column]
            for column in feature_output_cols
        },
    }
    if pulmonary_selected:
        if df_pulmonary_timeline is None:
            raise ValueError(
                "Pulmonary organ episodes require the pulmonary state timeline"
            )
        pulmonary_evidence_cols = [
            pulmonary_config.transition_time_col,
            pulmonary_config.transition_type_col,
            pulmonary_config.transition_event_ids_col,
        ]
        output_schema.update(
            {
                column: df_pulmonary_timeline.schema[column]
                for column in pulmonary_evidence_cols
            }
        )
    if df_organ_input.is_empty():
        return pl.DataFrame(schema=output_schema)
    if df_organ_input.select(
        pl.any_horizontal(
            pl.col([encounter_col, event_dt_col]).is_null()
        ).any()
    ).item():
        raise ValueError("Organ episode encounter and event timestamps cannot be null")
    duplicate_key_count = (
        df_organ_input.group_by(encounter_col, event_dt_col)
        .len()
        .filter(pl.col("len") > 1)
        .height
    )
    if duplicate_key_count:
        raise ValueError(
            "Organ episode input must have one row per encounter/timestamp; "
            f"found {duplicate_key_count} duplicate keys"
        )

    bounds = df_organ_input.group_by(encounter_col).agg(
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
        tuple[str, list[str], str, float, pl.DataFrame]
    ] = []
    for _, value_col, provenance_cols, validity_minutes in feature_details:
        source_ts_col = provenance_cols[0]
        mismatched_pair_count = df_organ_input.filter(
            pl.col(value_col).is_null() != pl.col(source_ts_col).is_null()
        ).height
        if mismatched_pair_count:
            raise ValueError(
                f"Organ feature {value_col!r} has {mismatched_pair_count} "
                "rows with mismatched values and source timestamps"
            )

        measurement_ts_col = f"_{value_col}_measurement_time"
        measurements = (
            df_organ_input.select(
                encounter_col,
                pl.col(source_ts_col).alias(measurement_ts_col),
                value_col,
                *provenance_cols[1:],
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
                f"Organ feature {value_col!r} has conflicting values at "
                f"{conflicting_measurement_count} encounter/timestamps"
            )
        measurements = measurements.unique(
            subset=[encounter_col, measurement_ts_col],
            keep="last",
        ).sort(encounter_col, measurement_ts_col)
        measurement_tables.append(
            (
                value_col,
                provenance_cols,
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

    if pulmonary_selected:
        required_pulmonary = {
            encounter_col,
            pulmonary_config.state_time_col,
            pulmonary_config.pulmonary_dysfunction_flag,
            pulmonary_config.transition_time_col,
            pulmonary_config.transition_type_col,
            pulmonary_config.transition_event_ids_col,
        }
        missing_pulmonary = sorted(
            required_pulmonary.difference(df_pulmonary_timeline.columns)
        )
        if missing_pulmonary:
            raise ValueError(
                "Pulmonary timeline is missing required columns: "
                f"{missing_pulmonary}"
            )
        if df_pulmonary_timeline.select(
            pl.any_horizontal(
                pl.col(
                    [encounter_col, pulmonary_config.state_time_col]
                ).is_null()
            ).any()
        ).item():
            raise ValueError(
                "Pulmonary timeline encounter and state timestamps cannot be null"
            )
        duplicate_pulmonary_count = (
            df_pulmonary_timeline.group_by(
                encounter_col,
                pulmonary_config.state_time_col,
            )
            .len()
            .filter(pl.col("len") > 1)
            .height
        )
        if duplicate_pulmonary_count:
            raise ValueError(
                "Pulmonary timeline must have one row per encounter/timestamp; "
                f"found {duplicate_pulmonary_count} duplicate keys"
            )
        change_point_frames.append(
            df_pulmonary_timeline.select(
                encounter_col,
                pl.col(pulmonary_config.state_time_col).alias("_change_time"),
            )
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
        provenance_cols,
        measurement_ts_col,
        validity_minutes,
        measurements,
    ) in measurement_tables:
        source_ts_col = provenance_cols[0]
        if measurements.is_empty():
            points = points.with_columns(
                pl.lit(None, dtype=df_organ_input.schema[value_col]).alias(
                    value_col
                ),
                *[
                    pl.lit(
                        None,
                        dtype=df_organ_input.schema[column],
                    ).alias(column)
                    for column in provenance_cols
                ],
            )
            continue
        points = points.join_asof(
            measurements,
            left_on="_change_time",
            right_on=measurement_ts_col,
            by=encounter_col,
            strategy="backward",
            check_sortedness=False,
        )
        evidence_is_valid = (
            pl.col(measurement_ts_col).is_not_null()
            & (
                pl.col("_change_time")
                < pl.col(measurement_ts_col)
                + pl.lit(timedelta(minutes=validity_minutes))
            )
        )
        points = points.with_columns(
            pl.when(evidence_is_valid)
            .then(pl.col(value_col))
            .otherwise(pl.lit(None, dtype=df_organ_input.schema[value_col]))
            .alias(value_col),
            pl.when(evidence_is_valid)
            .then(pl.col(measurement_ts_col))
            .otherwise(
                pl.lit(None, dtype=df_organ_input.schema[source_ts_col])
            )
            .alias(source_ts_col),
            *[
                pl.when(evidence_is_valid)
                .then(pl.col(column))
                .otherwise(
                    pl.lit(None, dtype=df_organ_input.schema[column])
                )
                .alias(column)
                for column in provenance_cols[1:]
            ],
        )

    if baselines:
        conflicting_baselines = (
            df_organ_input.group_by(encounter_col)
            .agg(
                *[
                    pl.col(column)
                    .drop_nulls()
                    .n_unique()
                    .alias(column)
                    for column in baselines
                ]
            )
            .filter(pl.any_horizontal(pl.col(baselines) > 1))
            .height
        )
        if conflicting_baselines:
            raise ValueError(
                "Organ episode input contains conflicting encounter baselines"
            )
        baseline_values = df_organ_input.group_by(encounter_col).agg(
            *[
                pl.col(column).drop_nulls().first().alias(column)
                for column in baselines
            ]
        )
        points = points.join(
            baseline_values,
            on=encounter_col,
            how="left",
            validate="m:1",
        )

    if pulmonary_selected:
        pulmonary_state_col = pulmonary_config.pulmonary_dysfunction_flag
        points = points.join_asof(
            df_pulmonary_timeline.select(
                encounter_col,
                pulmonary_config.state_time_col,
                pulmonary_state_col,
                pulmonary_config.transition_time_col,
                pulmonary_config.transition_type_col,
                pulmonary_config.transition_event_ids_col,
            ).sort(encounter_col, pulmonary_config.state_time_col),
            left_on="_change_time",
            right_on=pulmonary_config.state_time_col,
            by=encounter_col,
            strategy="backward",
            check_sortedness=False,
        )

    scored = build_organ_dysfunction_pipeline(config).process(points)
    return (
        scored.with_columns(
            (pl.col(config.flag_col) >= 1)
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


def build_organ_dysfunction_episodes(
    df_segments: pl.DataFrame,
    *,
    config: OrganDysfunctionConfig = organdysfunction_config,
    pulmonary_config: PulmonaryDysfunctionConfig = (
        pulmonary_dysfunction_config
    ),
) -> pl.DataFrame:
    """Collapse exact organ state segments and retain contributing organs."""
    encounter_col = config.encounter_col
    failure_cols = [
        column
        for column in _selected_failure_cols(config)
        if column in df_segments.columns
    ]
    features = _selected_features(config)
    baselines = [
        column
        for column in _selected_baselines(config)
        if column in df_segments.columns
    ]
    feature_evidence_exprs = []
    for feature in features:
        value_col = feature.value
        provenance_cols = source_provenance_cols(value_col)
        source_ts_col, source_type, source_event_id, source_event_name = (
            provenance_cols
        )
        required_feature_cols = {
            value_col,
            *provenance_cols,
            _feature_failure_col(feature, config),
        }
        missing_feature_cols = sorted(
            required_feature_cols.difference(df_segments.columns)
        )
        if missing_feature_cols:
            raise ValueError(
                "Organ segments are missing source-evidence columns: "
                f"{missing_feature_cols}"
            )
        feature_evidence_exprs.append(
            pl.struct(
                pl.col(value_col).alias("value"),
                pl.col(source_ts_col).alias("result_dt"),
                pl.col(source_type).alias("type"),
                pl.col(source_event_id).alias("event_id"),
                pl.col(source_event_name).alias("event_name"),
            )
            .filter(
                (pl.col(_feature_failure_col(feature, config)) == 1)
                & pl.col(source_ts_col).is_not_null()
            )
            .unique(maintain_order=True)
            .alias(_feature_evidence_col(feature, config))
        )

    pulmonary_evidence_exprs = []
    if OrganDysfunctionCriterionName.PULMONARY in config.selected:
        transition_time_col = pulmonary_config.transition_time_col
        transition_type_col = pulmonary_config.transition_type_col
        transition_event_ids_col = pulmonary_config.transition_event_ids_col
        pulmonary_columns = {
            config.pulmonary.flag_col,
            transition_time_col,
            transition_type_col,
            transition_event_ids_col,
        }
        missing_pulmonary = sorted(
            pulmonary_columns.difference(df_segments.columns)
        )
        if missing_pulmonary:
            raise ValueError(
                "Organ segments are missing pulmonary evidence columns: "
                f"{missing_pulmonary}"
            )
        pulmonary_evidence_exprs.append(
            pl.struct(
                pl.col(transition_time_col).alias("transition_dt"),
                pl.col(transition_type_col).alias("transition_type"),
                pl.col(transition_event_ids_col).alias("event_ids"),
            )
            .filter(
                (pl.col(config.pulmonary.flag_col) == 1)
                & pl.col(transition_time_col).is_not_null()
            )
            .unique(maintain_order=True)
            .alias(f"pulmonary{config.source_evidence_suffix}")
        )
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
        .agg(
            pl.col(config.flag_col)
            .max()
            .alias("max_organ_dysfunction_total"),
            *[pl.col(column).max().alias(column) for column in failure_cols],
            *[
                pl.col(column).drop_nulls().first().alias(column)
                for column in baselines
            ],
            *feature_evidence_exprs,
            *pulmonary_evidence_exprs,
        )
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
                "episode_id": "organ_episode_id",
                "state": "organ_episode_state",
                "episode_start": "organ_episode_start",
                "episode_end": "organ_episode_end",
                "episode_duration_minutes": (
                    "organ_episode_duration_minutes"
                ),
            }
        )
        .sort(encounter_col, "organ_episode_start")
    )
