"""Map existing BP episode-filter results back to the clinical timeline."""

import polars as pl


RAW_EPISODE_ID = "raw_hypotension_episode_id"
RAW_STATE = "raw_hypotension_state"
EPISODE_START = "hypotension_episode_start"
EPISODE_END = "hypotension_episode_end"
EPISODE_RETAINED = "hypotension_episode_retained_flag"
EFFECTIVE_HYPOTENSION_FLAG = "effective_hypotension_flag"
_ROW_ORDER = "__effective_hypotension_row_order"


def build_effective_hypotension_episodes(
    episode_results: dict[str, pl.DataFrame],
    *,
    encounter_col: str = "EncounterEpicCsn",
) -> pl.DataFrame:
    """Mark raw positive BP episodes retained by the existing filter.

    The filter's merged interval may contain absorbed negative or unknown gaps.
    This adapter uses its source-episode lineage so only original positive
    episodes become effective hypotension. It does not rerun episode filtering.
    """
    missing_stages = sorted({"raw", "filtered"}.difference(episode_results))
    if missing_stages:
        raise ValueError(
            f"BP episode results are missing required stages: {missing_stages}"
        )

    raw = episode_results["raw"]
    filtered = episode_results["filtered"]
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
        raise ValueError(f"Raw BP episodes are missing columns: {missing_raw}")
    required_filtered = {encounter_col, "state", "source_episode_ids"}
    missing_filtered = sorted(required_filtered.difference(filtered.columns))
    if missing_filtered:
        raise ValueError(
            f"Filtered BP episodes are missing columns: {missing_filtered}"
        )

    output_schema = {
        encounter_col: raw.schema[encounter_col],
        RAW_EPISODE_ID: pl.Int64,
        RAW_STATE: pl.Int8,
        EPISODE_START: raw.schema["episode_start"],
        EPISODE_END: raw.schema["episode_end"],
        "episode_duration_minutes": pl.Float64,
        EPISODE_RETAINED: pl.Int8,
        EFFECTIVE_HYPOTENSION_FLAG: pl.Int8,
    }
    if raw.is_empty():
        return pl.DataFrame(schema=output_schema)

    if raw.select(
        pl.any_horizontal(
            pl.col(
                [
                    encounter_col,
                    "episode_id",
                    "state",
                    "episode_start",
                    "episode_end",
                ]
            ).is_null()
        ).any()
    ).item():
        raise ValueError("Raw BP episode keys, states, and boundaries cannot be null")
    invalid_state_count = raw.filter(~pl.col("state").is_in([-1, 0, 1])).height
    if invalid_state_count:
        raise ValueError(
            f"Raw BP episodes contain {invalid_state_count} invalid states"
        )
    if filtered.filter(pl.col("state") != 1).height:
        raise ValueError("Filtered BP output must contain only positive episodes")

    retained_ids = (
        filtered.select(encounter_col, "source_episode_ids")
        .explode("source_episode_ids")
        .rename({"source_episode_ids": "episode_id"})
        .unique()
        .with_columns(pl.lit(True).alias("_retained_by_filter"))
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
            f"Filtered BP lineage contains {unmatched_retained_count} raw "
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
            .alias(EPISODE_RETAINED),
            pl.when(pl.col("state") == -1)
            .then(pl.lit(None, dtype=pl.Int8))
            .when(
                (pl.col("state") == 1) & pl.col("_retained_by_filter")
            )
            .then(pl.lit(1, dtype=pl.Int8))
            .otherwise(pl.lit(0, dtype=pl.Int8))
            .alias(EFFECTIVE_HYPOTENSION_FLAG),
        )
        .select(
            encounter_col,
            pl.col("episode_id").alias(RAW_EPISODE_ID),
            pl.col("state").cast(pl.Int8).alias(RAW_STATE),
            pl.col("episode_start").alias(EPISODE_START),
            pl.col("episode_end").alias(EPISODE_END),
            "episode_duration_minutes",
            EPISODE_RETAINED,
            EFFECTIVE_HYPOTENSION_FLAG,
        )
        .sort(encounter_col, EPISODE_START)
    )


def attach_effective_hypotension(
    df_timeline: pl.DataFrame,
    df_effective_episodes: pl.DataFrame,
    *,
    encounter_col: str = "EncounterEpicCsn",
    event_dt_col: str = "Event_DateTime",
) -> pl.DataFrame:
    """Attach the active filtered-hypotension episode to each timeline row."""
    timeline_keys = [encounter_col, event_dt_col]
    episode_required = {
        encounter_col,
        RAW_EPISODE_ID,
        RAW_STATE,
        EPISODE_START,
        EPISODE_END,
        EPISODE_RETAINED,
        EFFECTIVE_HYPOTENSION_FLAG,
    }
    missing_timeline = sorted(set(timeline_keys).difference(df_timeline.columns))
    if missing_timeline:
        raise ValueError(
            f"Hypotension timeline is missing required columns: {missing_timeline}"
        )
    missing_episodes = sorted(
        episode_required.difference(df_effective_episodes.columns)
    )
    if missing_episodes:
        raise ValueError(
            f"Effective hypotension episodes are missing columns: {missing_episodes}"
        )

    output_cols = [
        RAW_EPISODE_ID,
        RAW_STATE,
        EPISODE_START,
        EPISODE_END,
        EPISODE_RETAINED,
        EFFECTIVE_HYPOTENSION_FLAG,
    ]
    existing_outputs = sorted(set(output_cols).intersection(df_timeline.columns))
    if existing_outputs:
        raise ValueError(
            "Hypotension timeline already contains effective-state outputs: "
            f"{existing_outputs}"
        )
    if _ROW_ORDER in df_timeline.columns:
        raise ValueError(
            f"Hypotension timeline contains reserved column {_ROW_ORDER!r}"
        )
    if df_timeline.select(
        pl.any_horizontal(pl.col(timeline_keys).is_null()).any()
    ).item():
        raise ValueError("Hypotension timeline keys cannot be null")
    duplicate_timeline_count = (
        df_timeline.group_by(timeline_keys)
        .len()
        .filter(pl.col("len") > 1)
        .height
    )
    if duplicate_timeline_count:
        raise ValueError(
            "Hypotension timeline must have one row per encounter and timestamp; "
            f"found {duplicate_timeline_count} duplicate keys"
        )

    original_cols = df_timeline.columns
    joined = (
        df_timeline.with_row_index(_ROW_ORDER)
        .sort(encounter_col, event_dt_col)
        .join_asof(
            df_effective_episodes.select(
                encounter_col,
                *output_cols,
            ).sort(encounter_col, EPISODE_START),
            left_on=event_dt_col,
            right_on=EPISODE_START,
            by=encounter_col,
            strategy="backward",
            check_sortedness=False,
        )
    )
    active_episode = (
        pl.col(RAW_EPISODE_ID).is_not_null()
        & (pl.col(event_dt_col) < pl.col(EPISODE_END))
    )
    result = (
        joined.with_columns(
            *[
                pl.when(active_episode)
                .then(pl.col(column))
                .otherwise(pl.lit(None, dtype=df_effective_episodes.schema[column]))
                .alias(column)
                for column in [
                    RAW_EPISODE_ID,
                    RAW_STATE,
                    EPISODE_START,
                    EPISODE_END,
                ]
            ],
            pl.when(active_episode)
            .then(pl.col(EPISODE_RETAINED))
            .otherwise(pl.lit(0, dtype=pl.Int8))
            .alias(EPISODE_RETAINED),
            # Approved classification behavior: when filtering is enabled, a
            # final-event measurement has no observable interval and therefore
            # does not establish effective hypotension.
            pl.when(active_episode)
            .then(pl.col(EFFECTIVE_HYPOTENSION_FLAG))
            .otherwise(pl.lit(0, dtype=pl.Int8))
            .alias(EFFECTIVE_HYPOTENSION_FLAG),
        )
        .sort(_ROW_ORDER)
        .select(*original_cols, *output_cols)
    )
    if result.height != df_timeline.height:
        raise RuntimeError("Hypotension attachment changed the timeline row count")
    if not result.select(original_cols).equals(df_timeline):
        raise RuntimeError("Hypotension attachment changed existing timeline values")
    return result
