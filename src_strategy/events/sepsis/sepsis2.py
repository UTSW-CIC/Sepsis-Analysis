"""Evidence-preserving Sepsis 2 temporal association and categorization."""

from datetime import timedelta

import polars as pl

from ...configs.severitysepsis import SeveritySepsisConfig, severitysepsisconfig


def _organ_failure_items(
    config: SeveritySepsisConfig,
) -> list[tuple[str, str]]:
    organ = config.organdysfunction_config
    return [
        (criterion.value, getattr(organ, criterion.value).flag_col)
        for criterion in organ.selected
    ]


def select_first_organ_episodes_by_type(
    df_organ_episodes: pl.DataFrame,
    *,
    config: SeveritySepsisConfig = severitysepsisconfig,
) -> pl.DataFrame:
    """Keep the earliest positive episode for each configured organ type."""
    encounter_col = config.encounter_col
    episode_id_col = config.organ_episode_id_col
    organ_items = _organ_failure_items(config)
    required = {
        encounter_col,
        episode_id_col,
        "organ_episode_state",
        "organ_episode_start",
        *[flag_col for _, flag_col in organ_items],
    }
    missing = sorted(required.difference(df_organ_episodes.columns))
    if missing:
        raise ValueError(f"Organ episodes are missing columns: {missing}")

    positive = df_organ_episodes.filter(pl.col("organ_episode_state") == 1)
    type_col = config.sepsis2_first_organ_types_col
    candidates = pl.concat(
        [
            positive.filter(pl.col(flag_col) == 1).with_columns(
                pl.lit(organ_type).alias(type_col)
            )
            for organ_type, flag_col in organ_items
        ],
        how="vertical",
    )
    first_per_type = (
        candidates.sort(
            encounter_col,
            type_col,
            "organ_episode_start",
            episode_id_col,
        )
        .unique(
            subset=[encounter_col, type_col],
            keep="first",
            maintain_order=True,
        )
        .group_by(encounter_col, episode_id_col, maintain_order=True)
        .agg(pl.col(type_col).sort())
    )

    # One combined organ episode can be the first episode for several organ
    # types. Keep one evidence row and record every selected type in a list.
    return positive.join(
        first_per_type,
        on=[encounter_col, episode_id_col],
        how="inner",
        validate="1:1",
    ).sort(encounter_col, "organ_episode_start", episode_id_col)


def build_sepsis2_associations(
    df_infection_anchors: pl.DataFrame,
    df_organ_episodes: pl.DataFrame,
    *,
    config: SeveritySepsisConfig = severitysepsisconfig,
) -> pl.DataFrame:
    """Associate positive organ episodes with independent infection windows."""
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

    required_episodes = {
        config.encounter_col,
        config.organ_episode_id_col,
        "organ_episode_state",
        "organ_episode_start",
        "organ_episode_end",
        "organ_episode_duration_minutes",
        "max_organ_dysfunction_total",
        *[flag_col for _, flag_col in _organ_failure_items(config)],
    }
    missing_episodes = sorted(
        required_episodes.difference(df_organ_episodes.columns)
    )
    if missing_episodes:
        raise ValueError(
            f"Organ episodes are missing columns: {missing_episodes}"
        )

    backward = pl.lit(
        timedelta(hours=config.infection_2_organdysfunction_backward_hrs)
    )
    forward = pl.lit(
        timedelta(hours=config.infection_2_organdysfunction_forward_hrs)
    )
    window_start_col = "infection_organ_window_start"
    window_end_col = "infection_organ_window_end"
    infect_dt_col = infection.value_name_dt_col
    first_organ_episodes = select_first_organ_episodes_by_type(
        df_organ_episodes,
        config=config,
    )
    association = (
        df_infection_anchors.join(
            first_organ_episodes,
            on=config.encounter_col,
            how="inner",
            validate="m:m",
        )
        .with_columns(
            (pl.col(infect_dt_col) - backward).alias(window_start_col),
            (pl.col(infect_dt_col) + forward).alias(window_end_col),
        )
        # Organ episodes are half-open intervals. Exact boundary contact has
        # no elapsed overlap and therefore does not establish Sepsis 2.
        .filter(
            (pl.col("organ_episode_start") < pl.col(window_end_col))
            & (pl.col("organ_episode_end") > pl.col(window_start_col))
        )
        .with_columns(
            pl.lit(1, dtype=pl.Int8).alias(config.sepsis2_flag_col),
            # Classification time is when both associated evidence components
            # have been established; the earlier evidence time is also kept.
            pl.max_horizontal(
                infect_dt_col,
                "organ_episode_start",
            ).alias(config.sepsis2_dt_col),
            pl.min_horizontal(
                infect_dt_col,
                "organ_episode_start",
            ).alias(config.sepsis2_earliest_evidence_dt_col),
        )
        .unique(
            subset=[
                config.encounter_col,
                config.infection_anchor_id_col,
                config.organ_episode_id_col,
            ]
        )
    )
    evidence_cols = [
        column
        for _, column in _organ_failure_items(config)
        if column in association.columns
    ]
    return association.select(
        config.encounter_col,
        config.infection_anchor_id_col,
        infection.variable_name_col,
        infect_dt_col,
        infection.value_type_col,
        window_start_col,
        window_end_col,
        config.organ_episode_id_col,
        "organ_episode_start",
        "organ_episode_end",
        "organ_episode_duration_minutes",
        "max_organ_dysfunction_total",
        config.sepsis2_first_organ_types_col,
        *evidence_cols,
        config.sepsis2_flag_col,
        config.sepsis2_earliest_evidence_dt_col,
        config.sepsis2_dt_col,
    ).sort(
        config.encounter_col,
        config.sepsis2_dt_col,
        config.infection_anchor_id_col,
        config.organ_episode_id_col,
    )


def build_sepsis2_encounter_summary(
    df_encounters: pl.DataFrame,
    df_sepsis2_associations: pl.DataFrame,
    *,
    config: SeveritySepsisConfig = severitysepsisconfig,
) -> pl.DataFrame:
    """Return one Sepsis 2 classification row for every encounter."""
    encounter_col = config.encounter_col
    if encounter_col not in df_encounters.columns:
        raise ValueError(
            f"Sepsis 2 encounter input is missing column {encounter_col!r}"
        )
    if df_encounters.select(pl.col(encounter_col).is_null().any()).item():
        raise ValueError("Sepsis 2 encounter identifiers cannot be null")
    duplicate_encounter_count = (
        df_encounters.group_by(encounter_col)
        .len()
        .filter(pl.col("len") > 1)
        .height
    )
    if duplicate_encounter_count:
        raise ValueError(
            "Sepsis 2 encounter input must have one row per encounter; "
            f"found {duplicate_encounter_count} duplicate encounter IDs"
        )

    required_association = {
        encounter_col,
        config.infection_anchor_id_col,
        config.organ_episode_id_col,
        config.sepsis2_dt_col,
        config.sepsis2_earliest_evidence_dt_col,
    }
    missing_association = sorted(
        required_association.difference(df_sepsis2_associations.columns)
    )
    if missing_association:
        raise ValueError(
            f"Sepsis 2 associations are missing columns: {missing_association}"
        )

    reduced = df_sepsis2_associations.group_by(encounter_col).agg(
        pl.col(config.sepsis2_dt_col).min(),
        pl.col(config.sepsis2_earliest_evidence_dt_col).min(),
        pl.len().cast(pl.Int64).alias(config.sepsis2_association_count_col),
        pl.col(config.infection_anchor_id_col)
        .n_unique()
        .cast(pl.Int64)
        .alias(config.sepsis2_anchor_count_col),
        pl.col(config.organ_episode_id_col)
        .n_unique()
        .cast(pl.Int64)
        .alias(config.sepsis2_organ_episode_count_col),
    )
    count_cols = [
        config.sepsis2_association_count_col,
        config.sepsis2_anchor_count_col,
        config.sepsis2_organ_episode_count_col,
    ]
    return (
        df_encounters.select(encounter_col)
        .join(reduced, on=encounter_col, how="left", validate="1:1")
        .with_columns(pl.col(count_cols).fill_null(0))
        .with_columns(
            (pl.col(config.sepsis2_association_count_col) > 0)
            .cast(pl.Int8)
            .alias(config.sepsis2_flag_col)
        )
        .select(
            encounter_col,
            config.sepsis2_flag_col,
            config.sepsis2_earliest_evidence_dt_col,
            config.sepsis2_dt_col,
            *count_cols,
        )
        .sort(encounter_col)
    )
