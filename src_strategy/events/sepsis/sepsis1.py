"""Evidence-preserving Sepsis 1 temporal association and categorization."""

from datetime import timedelta

import polars as pl

from ...configs.severitysepsis import SeveritySepsisConfig, severitysepsisconfig


def build_infection_anchors(
    df_infection: pl.DataFrame,
    *,
    config: SeveritySepsisConfig = severitysepsisconfig,
) -> pl.DataFrame:
    """Return every distinct suspected-infection evidence row as an anchor."""
    infection = config.suspected_infection_config
    anchor_cols = [
        config.encounter_col,
        infection.value_name_dt_col,
        infection.variable_name_col,
        infection.value_type_col,
    ]
    missing = sorted(set(anchor_cols).difference(df_infection.columns))
    if missing:
        raise ValueError(
            f"Suspected-infection anchor input is missing columns: {missing}"
        )
    if df_infection.select(
        pl.any_horizontal(pl.col(anchor_cols).is_null()).any()
    ).item():
        raise ValueError("Suspected-infection anchor fields cannot be null")

    # Approved sensitivity-first policy: every distinct evidence row is an
    # independent anchor. For paired criteria this can create overlapping
    # windows wider than one canonical episode anchored at its earliest event;
    # canonical episode grouping remains the recommended future comparison.
    return (
        df_infection.select(anchor_cols)
        .unique(subset=anchor_cols)
        .sort(
            config.encounter_col,
            infection.value_name_dt_col,
            infection.variable_name_col,
            infection.value_type_col,
        )
        .with_columns(
            pl.int_range(1, pl.len() + 1)
            .over(config.encounter_col)
            .cast(pl.Int64)
            .alias(config.infection_anchor_id_col)
        )
        .select(
            config.encounter_col,
            config.infection_anchor_id_col,
            infection.variable_name_col,
            infection.value_name_dt_col,
            infection.value_type_col,
        )
    )


def build_sepsis1_associations(
    df_infection_anchors: pl.DataFrame,
    df_effective_sirs_episodes: pl.DataFrame,
    *,
    use_filtered_sirs: bool,
    config: SeveritySepsisConfig = severitysepsisconfig,
) -> pl.DataFrame:
    """Associate effective SIRS episodes with independent infection windows."""
    infection = config.suspected_infection_config
    required_anchors = {
        config.encounter_col,
        config.infection_anchor_id_col,
        infection.variable_name_col,
        infection.value_name_dt_col,
        infection.value_type_col,
    }
    missing_anchors = sorted(
        required_anchors.difference(df_infection_anchors.columns)
    )
    if missing_anchors:
        raise ValueError(f"Infection anchors are missing columns: {missing_anchors}")

    required_sirs = {
        config.encounter_col,
        config.sirs_episode_id_col,
        "sirs_episode_start",
        "sirs_episode_end",
        "sirs_episode_duration_minutes",
        config.effective_sirs_positive_flag_col,
        config.sirs_filter_applied_col,
    }
    missing_sirs = sorted(
        required_sirs.difference(df_effective_sirs_episodes.columns)
    )
    if missing_sirs:
        raise ValueError(
            f"Effective SIRS episodes are missing columns: {missing_sirs}"
        )
    if not df_effective_sirs_episodes.is_empty():
        applied_values = df_effective_sirs_episodes[
            config.sirs_filter_applied_col
        ].unique().to_list()
        if applied_values != [use_filtered_sirs]:
            raise ValueError(
                "Effective SIRS episodes do not match the requested filter state"
            )

    backward = pl.lit(
        timedelta(hours=config.infection_2_sirs_backward_hrs)
    )
    forward = pl.lit(
        timedelta(hours=config.infection_2_sirs_forward_hrs)
    )
    window_start_col = "infection_window_start"
    window_end_col = "infection_window_end"
    infect_dt_col = infection.value_name_dt_col
    association = (
        df_infection_anchors.join(
            df_effective_sirs_episodes.filter(
                pl.col(config.effective_sirs_positive_flag_col) == 1
            ),
            on=config.encounter_col,
            how="inner",
            validate="m:m",
        )
        .with_columns(
            (pl.col(infect_dt_col) - backward).alias(window_start_col),
            (pl.col(infect_dt_col) + forward).alias(window_end_col),
        )
        # SIRS episodes are half-open intervals. Exact contact with either
        # window boundary has zero overlap and therefore does not qualify.
        .filter(
            (pl.col("sirs_episode_start") < pl.col(window_end_col))
            & (pl.col("sirs_episode_end") > pl.col(window_start_col))
        )
        .with_columns(
            pl.lit(1, dtype=pl.Int8).alias(config.sepsis1_flag_col),
            # Approved onset: the later timestamp is when both associated
            # infection and qualifying SIRS evidence have been established.
            pl.max_horizontal(
                infect_dt_col,
                "sirs_episode_start",
            ).alias(config.sepsis1_dt_col),
            pl.min_horizontal(
                infect_dt_col,
                "sirs_episode_start",
            ).alias(config.sepsis1_earliest_evidence_dt_col),
        )
        .unique(
            subset=[
                config.encounter_col,
                config.infection_anchor_id_col,
                config.sirs_episode_id_col,
            ]
        )
    )
    return association.select(
        config.encounter_col,
        config.infection_anchor_id_col,
        infection.variable_name_col,
        infect_dt_col,
        infection.value_type_col,
        window_start_col,
        window_end_col,
        config.sirs_episode_id_col,
        "sirs_episode_start",
        "sirs_episode_end",
        "sirs_episode_duration_minutes",
        config.sirs_filter_applied_col,
        config.effective_sirs_positive_flag_col,
        config.sepsis1_flag_col,
        config.sepsis1_earliest_evidence_dt_col,
        config.sepsis1_dt_col,
    ).sort(
        config.encounter_col,
        config.sepsis1_dt_col,
        config.infection_anchor_id_col,
        config.sirs_episode_id_col,
    )


def build_sepsis1_encounter_summary(
    df_encounters: pl.DataFrame,
    df_sepsis1_associations: pl.DataFrame,
    *,
    config: SeveritySepsisConfig = severitysepsisconfig,
) -> pl.DataFrame:
    """Return one Sepsis 1 classification row for every encounter."""
    encounter_col = config.encounter_col
    if encounter_col not in df_encounters.columns:
        raise ValueError(
            f"Sepsis 1 encounter input is missing column {encounter_col!r}"
        )
    if df_encounters.select(pl.col(encounter_col).is_null().any()).item():
        raise ValueError("Sepsis 1 encounter identifiers cannot be null")
    duplicate_encounter_count = (
        df_encounters.group_by(encounter_col)
        .len()
        .filter(pl.col("len") > 1)
        .height
    )
    if duplicate_encounter_count:
        raise ValueError(
            "Sepsis 1 encounter input must have one row per encounter; "
            f"found {duplicate_encounter_count} duplicate encounter IDs"
        )

    required_association = {
        encounter_col,
        config.infection_anchor_id_col,
        config.sirs_episode_id_col,
        config.sepsis1_dt_col,
        config.sepsis1_earliest_evidence_dt_col,
    }
    missing_association = sorted(
        required_association.difference(df_sepsis1_associations.columns)
    )
    if missing_association:
        raise ValueError(
            f"Sepsis 1 associations are missing columns: {missing_association}"
        )

    reduced = df_sepsis1_associations.group_by(encounter_col).agg(
        pl.col(config.sepsis1_dt_col).min(),
        pl.col(config.sepsis1_earliest_evidence_dt_col).min(),
        pl.len().cast(pl.Int64).alias(config.sepsis1_association_count_col),
        pl.col(config.infection_anchor_id_col)
        .n_unique()
        .cast(pl.Int64)
        .alias(config.sepsis1_anchor_count_col),
        pl.col(config.sirs_episode_id_col)
        .n_unique()
        .cast(pl.Int64)
        .alias(config.sepsis1_sirs_episode_count_col),
    )
    count_cols = [
        config.sepsis1_association_count_col,
        config.sepsis1_anchor_count_col,
        config.sepsis1_sirs_episode_count_col,
    ]
    return (
        df_encounters.select(encounter_col)
        .join(reduced, on=encounter_col, how="left", validate="1:1")
        .with_columns(pl.col(count_cols).fill_null(0))
        .with_columns(
            (pl.col(config.sepsis1_association_count_col) > 0)
            .cast(pl.Int8)
            .alias(config.sepsis1_flag_col)
        )
        .select(
            encounter_col,
            config.sepsis1_flag_col,
            config.sepsis1_earliest_evidence_dt_col,
            config.sepsis1_dt_col,
            *count_cols,
        )
        .sort(encounter_col)
    )
