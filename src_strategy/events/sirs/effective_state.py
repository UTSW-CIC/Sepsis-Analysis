"""Map existing SIRS episode-filter results to effective SIRS episodes."""

import polars as pl

from ...configs.severitysepsis import SeveritySepsisConfig


def build_effective_sirs_episodes(
    episode_results: dict[str, pl.DataFrame],
    *,
    filter_enabled: bool,
    config: SeveritySepsisConfig,
) -> pl.DataFrame:
    """Return raw SIRS episodes with their classification-effective state.

    When filtering is enabled, retained source lineage comes from the existing
    episode filter. This function does not repeat bridging, merging, or duration
    filtering. When filtering is disabled, every raw positive episode remains
    effective.
    """
    if "raw" not in episode_results:
        raise ValueError("SIRS episode results are missing the raw stage")
    if filter_enabled and "filtered" not in episode_results:
        raise ValueError(
            "Enabled SIRS filtering requires the filtered episode stage"
        )

    raw = episode_results["raw"]
    encounter_col = config.encounter_col
    required_raw = {
        encounter_col,
        "episode_id",
        "state",
        "episode_start",
        "episode_end",
        "episode_duration_minutes",
    }
    missing_raw = sorted(required_raw.difference(raw.columns))
    if missing_raw:
        raise ValueError(f"Raw SIRS episodes are missing columns: {missing_raw}")

    output_schema = {
        encounter_col: raw.schema[encounter_col],
        config.sirs_episode_id_col: pl.Int64,
        "raw_sirs_state": pl.Int8,
        "sirs_episode_start": raw.schema["episode_start"],
        "sirs_episode_end": raw.schema["episode_end"],
        "sirs_episode_duration_minutes": pl.Float64,
        "sirs_episode_retained_flag": pl.Int8,
        config.effective_sirs_positive_flag_col: pl.Int8,
        config.sirs_filter_applied_col: pl.Boolean,
    }
    if raw.is_empty():
        return pl.DataFrame(schema=output_schema)

    required_values = [
        encounter_col,
        "episode_id",
        "state",
        "episode_start",
        "episode_end",
    ]
    if raw.select(
        pl.any_horizontal(pl.col(required_values).is_null()).any()
    ).item():
        raise ValueError("Raw SIRS episode keys, states, and boundaries cannot be null")
    invalid_state_count = raw.filter(~pl.col("state").is_in([-1, 0, 1])).height
    if invalid_state_count:
        raise ValueError(
            f"Raw SIRS episodes contain {invalid_state_count} invalid states"
        )

    if filter_enabled:
        filtered = episode_results["filtered"]
        required_filtered = {
            encounter_col,
            "state",
            "source_episode_ids",
        }
        missing_filtered = sorted(required_filtered.difference(filtered.columns))
        if missing_filtered:
            raise ValueError(
                f"Filtered SIRS episodes are missing columns: {missing_filtered}"
            )
        if filtered.filter(pl.col("state") != 1).height:
            raise ValueError(
                "Filtered SIRS output must contain only positive episodes"
            )
        retained_ids = (
            filtered.select(encounter_col, "source_episode_ids")
            .explode("source_episode_ids")
            .rename({"source_episode_ids": "episode_id"})
            .unique()
        )
    else:
        retained_ids = raw.filter(pl.col("state") == 1).select(
            encounter_col,
            "episode_id",
        )

    retained_ids = retained_ids.with_columns(
        pl.lit(True).alias("_retained_by_filter")
    )
    unmatched_retained_count = (
        retained_ids.select(encounter_col, "episode_id")
        .join(
            raw.select(encounter_col, "episode_id"),
            on=[encounter_col, "episode_id"],
            how="anti",
        )
        .height
    )
    if unmatched_retained_count:
        raise ValueError(
            f"Filtered SIRS lineage contains {unmatched_retained_count} raw "
            "episode IDs that do not exist"
        )

    marked = raw.join(
        retained_ids,
        on=[encounter_col, "episode_id"],
        how="left",
        validate="1:1",
    ).with_columns(pl.col("_retained_by_filter").fill_null(False))
    return (
        marked.with_columns(
            pl.when(pl.col("state") == 1)
            .then(pl.col("_retained_by_filter").cast(pl.Int8))
            .otherwise(pl.lit(0, dtype=pl.Int8))
            .alias("sirs_episode_retained_flag"),
            pl.when(pl.col("state") == -1)
            .then(pl.lit(None, dtype=pl.Int8))
            .when(
                (pl.col("state") == 1) & pl.col("_retained_by_filter")
            )
            .then(pl.lit(1, dtype=pl.Int8))
            .otherwise(pl.lit(0, dtype=pl.Int8))
            .alias(config.effective_sirs_positive_flag_col),
            pl.lit(filter_enabled).alias(config.sirs_filter_applied_col),
        )
        .select(
            encounter_col,
            pl.col("episode_id").alias(config.sirs_episode_id_col),
            pl.col("state").cast(pl.Int8).alias("raw_sirs_state"),
            pl.col("episode_start").alias("sirs_episode_start"),
            pl.col("episode_end").alias("sirs_episode_end"),
            pl.col("episode_duration_minutes").alias(
                "sirs_episode_duration_minutes"
            ),
            "sirs_episode_retained_flag",
            config.effective_sirs_positive_flag_col,
            config.sirs_filter_applied_col,
        )
        .sort(encounter_col, "sirs_episode_start")
    )
