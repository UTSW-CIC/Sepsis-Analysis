"""Evidence-preserving Sepsis 3 temporal association and categorization."""

from datetime import timedelta

import polars as pl

from ...configs.severitysepsis import SeveritySepsisConfig, severitysepsisconfig


def build_sepsis3_associations(
    df_sepsis2_associations: pl.DataFrame,
    df_shock_episodes: pl.DataFrame,
    df_shock_points: pl.DataFrame,
    *,
    config: SeveritySepsisConfig = severitysepsisconfig,
) -> pl.DataFrame:
    """Match Sepsis 2 evidence to overlapping shock intervals or points."""
    infection = config.suspected_infection_config
    infect_dt_col = infection.value_name_dt_col
    required_sepsis2 = {
        config.encounter_col,
        config.infection_anchor_id_col,
        config.organ_episode_id_col,
        infect_dt_col,
        "organ_episode_start",
        "organ_episode_end",
        config.sepsis2_dt_col,
    }
    missing_sepsis2 = sorted(
        required_sepsis2.difference(df_sepsis2_associations.columns)
    )
    if missing_sepsis2:
        raise ValueError(
            f"Sepsis 2 associations are missing columns: {missing_sepsis2}"
        )

    required_episodes = {
        config.encounter_col,
        config.shock_episode_id_col,
        "shock_episode_state",
        "shock_episode_start",
        "shock_episode_end",
        "shock_episode_duration_minutes",
    }
    missing_episodes = sorted(
        required_episodes.difference(df_shock_episodes.columns)
    )
    if missing_episodes:
        raise ValueError(
            f"Shock episodes are missing columns: {missing_episodes}"
        )
    required_points = {
        config.encounter_col,
        config.shock_point_id_col,
        "shock_point_time",
        "shock_point_type",
        "qualifying_vasopressor_dose_count",
        "qualifying_vasopressor_groupers",
    }
    missing_points = sorted(required_points.difference(df_shock_points.columns))
    if missing_points:
        raise ValueError(f"Shock points are missing columns: {missing_points}")

    backward = pl.lit(
        timedelta(hours=config.infection_2_shock_dysfunction_backward_hrs)
    )
    forward = pl.lit(
        timedelta(hours=config.infection_2_shock_dysfunction_forward_hrs)
    )
    window_start_col = "infection_shock_window_start"
    window_end_col = "infection_shock_window_end"
    sepsis2 = df_sepsis2_associations.with_columns(
        (pl.col(infect_dt_col) - backward).alias(window_start_col),
        (pl.col(infect_dt_col) + forward).alias(window_end_col),
    )

    interval_matches = (
        sepsis2.join(
            df_shock_episodes.filter(pl.col("shock_episode_state") == 1),
            on=config.encounter_col,
            how="inner",
            validate="m:m",
        )
        # Approved rule: interval shock evidence must have positive-duration
        # overlap with both the organ episode and infection window.
        .filter(
            (pl.col("shock_episode_start") < pl.col("organ_episode_end"))
            & (pl.col("shock_episode_end") > pl.col("organ_episode_start"))
            & (pl.col("shock_episode_start") < pl.col(window_end_col))
            & (pl.col("shock_episode_end") > pl.col(window_start_col))
        )
        .with_columns(
            pl.lit("interval").alias("shock_evidence_type"),
            pl.col(config.shock_episode_id_col)
            .cast(pl.String)
            .alias("shock_evidence_id"),
            pl.col("shock_episode_start").alias("shock_evidence_start"),
            pl.col("shock_episode_end").alias("shock_evidence_end"),
            pl.lit(1, dtype=pl.Int8).alias(
                config.septicshock_config.flag_col
            ),
        )
    )

    point_matches = (
        sepsis2.join(
            df_shock_points,
            on=config.encounter_col,
            how="inner",
            validate="m:m",
        )
        # Point evidence is inside a half-open interval when it is at or after
        # the start and strictly before the end. It is never carried forward.
        .filter(
            (pl.col("shock_point_time") >= pl.col("organ_episode_start"))
            & (pl.col("shock_point_time") < pl.col("organ_episode_end"))
            & (pl.col("shock_point_time") >= pl.col(window_start_col))
            & (pl.col("shock_point_time") < pl.col(window_end_col))
        )
        .with_columns(
            pl.col("shock_point_type").alias("shock_evidence_type"),
            pl.col(config.shock_point_id_col)
            .cast(pl.String)
            .alias("shock_evidence_id"),
            pl.col("shock_point_time").alias("shock_evidence_start"),
            pl.lit(None, dtype=df_shock_points.schema["shock_point_time"])
            .alias("shock_evidence_end"),
            pl.lit(1, dtype=pl.Int8).alias(
                config.septicshock_config.vasopressor_criteria.flag_col
            ),
            pl.lit(1, dtype=pl.Int8).alias(
                config.septicshock_config.flag_col
            ),
        )
    )

    association = pl.concat(
        [interval_matches, point_matches],
        how="diagonal_relaxed",
    ).with_columns(
        pl.concat_str(
            "shock_evidence_type",
            "shock_evidence_id",
            separator=":",
        ).alias("shock_evidence_key"),
        # Approved timestamp semantics: classification occurs when infection,
        # organ dysfunction, and shock evidence have all been established.
        pl.max_horizontal(
            infect_dt_col,
            "organ_episode_start",
            "shock_evidence_start",
        ).alias(config.sepsis3_dt_col),
        pl.min_horizontal(
            infect_dt_col,
            "organ_episode_start",
            "shock_evidence_start",
        ).alias(config.sepsis3_earliest_evidence_dt_col),
        pl.lit(1, dtype=pl.Int8).alias(config.sepsis3_flag_col),
    ).unique(
        subset=[
            config.encounter_col,
            config.infection_anchor_id_col,
            config.organ_episode_id_col,
            "shock_evidence_key",
        ]
    )

    sepsis2_cols = df_sepsis2_associations.columns
    shock_cols = [
        column
        for column in association.columns
        if column not in sepsis2_cols
        and column
        not in {
            config.encounter_col,
            window_start_col,
            window_end_col,
        }
    ]
    return association.select(
        *sepsis2_cols,
        window_start_col,
        window_end_col,
        *shock_cols,
    ).sort(
        config.encounter_col,
        config.sepsis3_dt_col,
        config.infection_anchor_id_col,
        config.organ_episode_id_col,
        "shock_evidence_key",
    )


def build_sepsis3_encounter_summary(
    df_encounters: pl.DataFrame,
    df_sepsis3_associations: pl.DataFrame,
    *,
    config: SeveritySepsisConfig = severitysepsisconfig,
) -> pl.DataFrame:
    """Return one Sepsis 3 classification row for every encounter."""
    encounter_col = config.encounter_col
    if encounter_col not in df_encounters.columns:
        raise ValueError(
            f"Sepsis 3 encounter input is missing column {encounter_col!r}"
        )
    if df_encounters.select(pl.col(encounter_col).is_null().any()).item():
        raise ValueError("Sepsis 3 encounter identifiers cannot be null")
    duplicate_encounter_count = (
        df_encounters.group_by(encounter_col)
        .len()
        .filter(pl.col("len") > 1)
        .height
    )
    if duplicate_encounter_count:
        raise ValueError(
            "Sepsis 3 encounter input must have one row per encounter; "
            f"found {duplicate_encounter_count} duplicate encounter IDs"
        )

    required_association = {
        encounter_col,
        config.infection_anchor_id_col,
        config.organ_episode_id_col,
        "shock_evidence_key",
        config.sepsis3_dt_col,
        config.sepsis3_earliest_evidence_dt_col,
    }
    missing_association = sorted(
        required_association.difference(df_sepsis3_associations.columns)
    )
    if missing_association:
        raise ValueError(
            f"Sepsis 3 associations are missing columns: {missing_association}"
        )

    reduced = df_sepsis3_associations.group_by(encounter_col).agg(
        pl.col(config.sepsis3_dt_col).min(),
        pl.col(config.sepsis3_earliest_evidence_dt_col).min(),
        pl.len().cast(pl.Int64).alias(config.sepsis3_association_count_col),
        pl.col(config.infection_anchor_id_col)
        .n_unique()
        .cast(pl.Int64)
        .alias(config.sepsis3_anchor_count_col),
        pl.col(config.organ_episode_id_col)
        .n_unique()
        .cast(pl.Int64)
        .alias(config.sepsis3_organ_episode_count_col),
        pl.col("shock_evidence_key")
        .n_unique()
        .cast(pl.Int64)
        .alias(config.sepsis3_shock_evidence_count_col),
    )
    count_cols = [
        config.sepsis3_association_count_col,
        config.sepsis3_anchor_count_col,
        config.sepsis3_organ_episode_count_col,
        config.sepsis3_shock_evidence_count_col,
    ]
    return (
        df_encounters.select(encounter_col)
        .join(reduced, on=encounter_col, how="left", validate="1:1")
        .with_columns(pl.col(count_cols).fill_null(0))
        .with_columns(
            (pl.col(config.sepsis3_association_count_col) > 0)
            .cast(pl.Int8)
            .alias(config.sepsis3_flag_col)
        )
        .select(
            encounter_col,
            config.sepsis3_flag_col,
            config.sepsis3_earliest_evidence_dt_col,
            config.sepsis3_dt_col,
            *count_cols,
        )
        .sort(encounter_col)
    )
