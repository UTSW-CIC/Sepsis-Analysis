"""Evidence-preserving Sepsis 3 temporal association and categorization."""

from datetime import timedelta

import polars as pl

from ...configs.severitysepsis import SeveritySepsisConfig, severitysepsisconfig


def build_sepsis3_associations(
    df_infection_anchors: pl.DataFrame,
    df_sepsis2_associations: pl.DataFrame,
    df_effective_hypotension_episodes: pl.DataFrame,
    df_lactate_gt2_evidence: pl.DataFrame,
    df_vasopressor_points: pl.DataFrame,
    *,
    config: SeveritySepsisConfig = severitysepsisconfig,
) -> pl.DataFrame:
    """Build the two independent, infection-anchored Sepsis 3 pathways.

    Pathway A requires occurrences of Sepsis 2, filtered hypotension, and a
    lactate result above 2 inside the same inclusive infection +/-48-hour
    window. Their positive intervals do not need to overlap.

    Pathway B requires a qualifying vasopressor administration inside that
    inclusive window. It does not require Sepsis 2.
    """
    infection = config.suspected_infection_config
    infect_dt_col = infection.value_name_dt_col
    infection_met_col = infection.criterion_met_datetime_col
    encounter_col = config.encounter_col
    pathway_col = config.sepsis3_pathway_col
    criterion_met_col = config.sepsis3_criterion_met_dt_col
    shock_flag_col = config.septicshock_config.flag_col
    vasopressor = config.septicshock_config.vasopressor_criteria
    lactate = config.septicshock_config.lactate2_criteria

    required_anchors = {
        encounter_col,
        config.infection_anchor_id_col,
        infection.infection_episode_id_col,
        infection.variable_name_col,
        infect_dt_col,
        infection_met_col,
        infection.value_type_col,
    }
    missing_anchors = sorted(
        required_anchors.difference(df_infection_anchors.columns)
    )
    if missing_anchors:
        raise ValueError(
            f"Infection anchors are missing columns: {missing_anchors}"
        )

    required_sepsis2 = {
        encounter_col,
        config.infection_anchor_id_col,
        config.organ_episode_id_col,
        infect_dt_col,
        infection_met_col,
        config.sepsis2_dt_col,
    }
    missing_sepsis2 = sorted(
        required_sepsis2.difference(df_sepsis2_associations.columns)
    )
    if missing_sepsis2:
        raise ValueError(
            f"Sepsis 2 associations are missing columns: {missing_sepsis2}"
        )

    required_hypotension = {
        encounter_col,
        "raw_hypotension_episode_id",
        "hypotension_episode_start",
        "hypotension_episode_end",
        "effective_hypotension_flag",
    }
    missing_hypotension = sorted(
        required_hypotension.difference(
            df_effective_hypotension_episodes.columns
        )
    )
    if missing_hypotension:
        raise ValueError(
            "Effective hypotension episodes are missing columns: "
            f"{missing_hypotension}"
        )

    required_lactate = {
        encounter_col,
        lactate.evidence_id_col,
        lactate.evidence_datetime_col,
        lactate.evidence_value_col,
    }
    missing_lactate = sorted(
        required_lactate.difference(df_lactate_gt2_evidence.columns)
    )
    if missing_lactate:
        raise ValueError(
            f"Lactate >2 evidence is missing columns: {missing_lactate}"
        )

    required_points = {
        encounter_col,
        config.shock_point_id_col,
        "shock_point_time",
        vasopressor.anchor_datetime_col,
        vasopressor.administration_datetime_col,
        "qualifying_vasopressor_dose_count",
        "qualifying_vasopressor_groupers",
    }
    missing_points = sorted(
        required_points.difference(df_vasopressor_points.columns)
    )
    if missing_points:
        raise ValueError(
            f"Vasopressor evidence is missing columns: {missing_points}"
        )

    backward = pl.lit(
        timedelta(hours=config.infection_2_shock_dysfunction_backward_hrs)
    )
    forward = pl.lit(
        timedelta(hours=config.infection_2_shock_dysfunction_forward_hrs)
    )
    window_start_col = "infection_shock_window_start"
    window_end_col = "infection_shock_window_end"
    infection_with_window = df_infection_anchors.with_columns(
        (pl.col(infect_dt_col) - backward).alias(window_start_col),
        (pl.col(infect_dt_col) + forward).alias(window_end_col),
    )

    sepsis2 = df_sepsis2_associations.join(
        infection_with_window.select(
            encounter_col,
            config.infection_anchor_id_col,
            window_start_col,
            window_end_col,
        ),
        on=[encounter_col, config.infection_anchor_id_col],
        how="inner",
        validate="m:1",
    ).filter(
        pl.col(config.sepsis2_dt_col).is_between(
            pl.col(window_start_col),
            pl.col(window_end_col),
            closed="both",
        )
    )

    pathway_a = (
        sepsis2.join(
            df_effective_hypotension_episodes.filter(
                pl.col("effective_hypotension_flag") == 1
            ).select(
                encounter_col,
                "raw_hypotension_episode_id",
                "hypotension_episode_start",
                "hypotension_episode_end",
            ),
            on=encounter_col,
            how="inner",
            validate="m:m",
        )
        .filter(
            pl.col("hypotension_episode_start").is_between(
                pl.col(window_start_col),
                pl.col(window_end_col),
                closed="both",
            )
        )
        .join(
            df_lactate_gt2_evidence,
            on=encounter_col,
            how="inner",
            validate="m:m",
        )
        .filter(
            pl.col(lactate.evidence_datetime_col).is_between(
                pl.col(window_start_col),
                pl.col(window_end_col),
                closed="both",
            )
        )
        .with_columns(
            pl.lit("hypotension_lactate_sepsis2").alias(pathway_col),
            pl.lit(1, dtype=pl.Int8).alias(lactate.flag_col),
            pl.lit(0, dtype=pl.Int8).alias(vasopressor.flag_col),
        )
        .with_columns(
            pl.concat_str(
                pl.lit("pathway_a"),
                pl.col(config.organ_episode_id_col),
                pl.col("raw_hypotension_episode_id"),
                pl.col(lactate.evidence_id_col),
                separator=":",
            ).alias("shock_evidence_key"),
            pl.min_horizontal(
                infect_dt_col,
                config.sepsis2_dt_col,
                "hypotension_episode_start",
                lactate.evidence_datetime_col,
            ).alias(config.sepsis3_dt_col),
            pl.max_horizontal(
                infection_met_col,
                config.sepsis2_dt_col,
                "hypotension_episode_start",
                lactate.evidence_datetime_col,
            ).alias(criterion_met_col),
        )
    )

    pathway_b = (
        infection_with_window.join(
            df_vasopressor_points,
            on=encounter_col,
            how="inner",
            validate="m:m",
        )
        .filter(
            pl.col(vasopressor.administration_datetime_col).is_between(
                pl.col(window_start_col),
                pl.col(window_end_col),
                closed="both",
            )
        )
        .with_columns(
            pl.lit("infection_vasopressor").alias(pathway_col),
            pl.lit(1, dtype=pl.Int8).alias(vasopressor.flag_col),
            pl.concat_str(
                pl.lit("pathway_b"),
                pl.col(config.shock_point_id_col),
                separator=":",
            ).alias("shock_evidence_key"),
            pl.min_horizontal(
                infect_dt_col,
                vasopressor.anchor_datetime_col,
            ).alias(config.sepsis3_dt_col),
            pl.max_horizontal(
                infection_met_col,
                vasopressor.administration_datetime_col,
            ).alias(criterion_met_col),
        )
    )

    association = (
        pl.concat([pathway_a, pathway_b], how="diagonal_relaxed")
        .with_columns(
            pl.col(config.sepsis3_dt_col).alias(
                config.sepsis3_earliest_evidence_dt_col
            ),
            pl.lit(1, dtype=pl.Int8).alias(shock_flag_col),
            pl.lit(1, dtype=pl.Int8).alias(config.sepsis3_flag_col),
        )
        .unique(
            subset=[
                encounter_col,
                config.infection_anchor_id_col,
                pathway_col,
                "shock_evidence_key",
            ]
        )
    )
    return association.sort(
        encounter_col,
        config.sepsis3_dt_col,
        config.infection_anchor_id_col,
        pathway_col,
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
        "shock_evidence_key",
        config.sepsis3_dt_col,
        config.sepsis3_criterion_met_dt_col,
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
        pl.col(config.sepsis3_criterion_met_dt_col).min(),
        pl.col(config.sepsis3_earliest_evidence_dt_col).min(),
        pl.len().cast(pl.Int64).alias(config.sepsis3_association_count_col),
        pl.col(config.infection_anchor_id_col)
        .n_unique()
        .cast(pl.Int64)
        .alias(config.sepsis3_anchor_count_col),
        pl.col(config.organ_episode_id_col)
        .drop_nulls()
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
            config.sepsis3_criterion_met_dt_col,
            *count_cols,
        )
        .sort(encounter_col)
    )
