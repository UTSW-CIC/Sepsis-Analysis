"""Shared temporal episode construction for clinical state timelines.

The helpers in this module operate on explicit, half-open state segments.  They
do not decide how a clinical state is calculated or how an encounter ends.
Those decisions belong to the SIRS and hypotension adapters that create the
input segments.
"""

from math import isfinite

import polars as pl


UNKNOWN_STATE = -1
NEGATIVE_STATE = 0
POSITIVE_STATE = 1
VALID_STATES = (UNKNOWN_STATE, NEGATIVE_STATE, POSITIVE_STATE)


def _require_columns(df: pl.DataFrame, required: set[str]) -> None:
    missing = sorted(required.difference(df.columns))
    if missing:
        raise ValueError(f"State segments are missing required columns: {missing}")


def build_state_episodes(
    segments: pl.DataFrame,
    *,
    encounter_col: str = "EncounterEpicCsn",
    state_col: str = "state",
    segment_start_col: str = "segment_start",
    segment_end_col: str = "segment_end",
) -> pl.DataFrame:
    """Collapse contiguous equal-state segments into encounter episodes.

    Input rows must describe a complete, non-overlapping timeline using
    half-open intervals ``[segment_start, segment_end)``.  State values are:
    ``1`` positive, ``0`` measured negative, and ``-1`` unknown.  A gap must be
    represented explicitly as an unknown segment; the function never fills or
    bridges time silently.

    The returned ``episode_id`` restarts at one for each encounter.  Unknown
    episodes are retained for later, clinically configured handling.
    """
    _require_columns(
        segments,
        {
            encounter_col,
            state_col,
            segment_start_col,
            segment_end_col,
        },
    )

    output_schema = {
        encounter_col: segments.schema[encounter_col],
        "episode_id": pl.Int64,
        state_col: pl.Int8,
        "episode_start": segments.schema[segment_start_col],
        "episode_end": segments.schema[segment_end_col],
        "episode_duration_minutes": pl.Float64,
        "source_segment_count": pl.UInt32,
    }
    if segments.is_empty():
        return pl.DataFrame(schema=output_schema)

    required_cols = [
        encounter_col,
        state_col,
        segment_start_col,
        segment_end_col,
    ]
    if segments.select(
        pl.any_horizontal(pl.col(required_cols).is_null()).any()
    ).item():
        raise ValueError("State segment keys, boundaries, and states cannot be null")

    try:
        ordered = (
            segments.select(required_cols)
            .with_columns(pl.col(state_col).cast(pl.Int8, strict=True))
            .sort(encounter_col, segment_start_col, segment_end_col)
        )
    except Exception as exc:
        raise ValueError("State values must be integers in {-1, 0, 1}") from exc

    invalid_state_count = ordered.filter(
        ~pl.col(state_col).is_in(VALID_STATES)
    ).height
    if invalid_state_count:
        raise ValueError(
            f"State segments contain {invalid_state_count} values outside {{-1, 0, 1}}"
        )

    invalid_duration_count = ordered.filter(
        pl.col(segment_end_col) <= pl.col(segment_start_col)
    ).height
    if invalid_duration_count:
        raise ValueError(
            f"State segments contain {invalid_duration_count} non-positive intervals"
        )

    ordered = ordered.with_columns(
        pl.col(segment_end_col)
        .shift(1)
        .over(encounter_col)
        .alias("_previous_end")
    )
    discontinuity_count = ordered.filter(
        pl.col("_previous_end").is_not_null()
        & (pl.col(segment_start_col) != pl.col("_previous_end"))
    ).height
    if discontinuity_count:
        raise ValueError(
            "State segments must be contiguous within each encounter; "
            f"found {discontinuity_count} gaps or overlaps"
        )

    segmented = (
        ordered.with_columns(
            pl.col(state_col)
            .ne(pl.col(state_col).shift(1).over(encounter_col))
            .fill_null(True)
            .alias("_new_episode")
        )
        .with_columns(
            pl.col("_new_episode")
            .cast(pl.Int64)
            .cum_sum()
            .over(encounter_col)
            .alias("episode_id")
        )
    )

    return (
        segmented.group_by(encounter_col, "episode_id", maintain_order=True)
        .agg(
            pl.col(state_col).first(),
            pl.col(segment_start_col).first().alias("episode_start"),
            pl.col(segment_end_col).last().alias("episode_end"),
            pl.len().alias("source_segment_count"),
        )
        .with_columns(
            (
                pl.col("episode_end") - pl.col("episode_start")
            )
            .dt.total_minutes(fractional=True)
            .alias("episode_duration_minutes")
        )
        .select(output_schema.keys())
        .sort(encounter_col, "episode_id")
    )


def bridge_equal_states_across_unknown(
    episodes: pl.DataFrame,
    *,
    encounter_col: str = "EncounterEpicCsn",
    episode_id_col: str = "episode_id",
    state_col: str = "state",
    episode_start_col: str = "episode_start",
    episode_end_col: str = "episode_end",
    source_segment_count_col: str = "source_segment_count",
) -> pl.DataFrame:
    """Bridge internal unknown episodes surrounded by the same known state.

    ``positive -> unknown -> positive`` and
    ``negative -> unknown -> negative`` become one episode. Connected chains,
    such as ``positive -> unknown -> positive -> unknown -> positive``, are
    collapsed together. Leading, trailing, and differently bounded unknown
    episodes remain explicit and are not assigned to a known state.

    The output receives new encounter-local episode IDs. ``source_episode_ids``
    and ``bridged_unknown_gap_count`` preserve the transformation provenance.
    """
    required_cols = {
        encounter_col,
        episode_id_col,
        state_col,
        episode_start_col,
        episode_end_col,
        source_segment_count_col,
    }
    _require_columns(episodes, required_cols)

    output_schema = {
        encounter_col: episodes.schema[encounter_col],
        episode_id_col: pl.Int64,
        state_col: pl.Int8,
        episode_start_col: episodes.schema[episode_start_col],
        episode_end_col: episodes.schema[episode_end_col],
        "episode_duration_minutes": pl.Float64,
        source_segment_count_col: episodes.schema[source_segment_count_col],
        "source_episode_ids": pl.List(episodes.schema[episode_id_col]),
        "source_episode_count": pl.UInt32,
        "bridged_unknown_gap_count": pl.UInt32,
    }
    if episodes.is_empty():
        return pl.DataFrame(schema=output_schema)

    selected_cols = [
        encounter_col,
        episode_id_col,
        state_col,
        episode_start_col,
        episode_end_col,
        source_segment_count_col,
    ]
    if episodes.select(
        pl.any_horizontal(pl.col(selected_cols).is_null()).any()
    ).item():
        raise ValueError("Episode keys, boundaries, states, and counts cannot be null")

    try:
        ordered = (
            episodes.select(selected_cols)
            .with_columns(pl.col(state_col).cast(pl.Int8, strict=True))
            .sort(encounter_col, episode_start_col, episode_end_col)
        )
    except Exception as exc:
        raise ValueError("Episode states must be integers in {-1, 0, 1}") from exc

    invalid_state_count = ordered.filter(
        ~pl.col(state_col).is_in(VALID_STATES)
    ).height
    if invalid_state_count:
        raise ValueError(
            f"Episodes contain {invalid_state_count} values outside {{-1, 0, 1}}"
        )

    duplicate_id_count = (
        ordered.group_by(encounter_col, episode_id_col)
        .len()
        .filter(pl.col("len") > 1)
        .height
    )
    if duplicate_id_count:
        raise ValueError(
            f"Episodes contain {duplicate_id_count} duplicate encounter/episode IDs"
        )

    ordered = ordered.with_columns(
        pl.col(state_col).shift(1).over(encounter_col).alias("_previous_state"),
        pl.col(state_col).shift(-1).over(encounter_col).alias("_next_state"),
        pl.col(episode_end_col)
        .shift(1)
        .over(encounter_col)
        .alias("_previous_end"),
        pl.col(episode_start_col)
        .shift(-1)
        .over(encounter_col)
        .alias("_next_start"),
    )

    discontinuity_count = ordered.filter(
        pl.col("_previous_end").is_not_null()
        & (pl.col(episode_start_col) != pl.col("_previous_end"))
    ).height
    if discontinuity_count:
        raise ValueError(
            "Input episodes must be contiguous within each encounter; "
            f"found {discontinuity_count} gaps or overlaps"
        )

    adjacent_equal_count = ordered.filter(
        pl.col("_previous_state").is_not_null()
        & (pl.col(state_col) == pl.col("_previous_state"))
    ).height
    if adjacent_equal_count:
        raise ValueError(
            "Input must contain collapsed state episodes; "
            f"found {adjacent_equal_count} adjacent equal-state pairs"
        )

    marked = ordered.with_columns(
        (
            (pl.col(state_col) == UNKNOWN_STATE)
            & pl.col("_previous_state").is_in(
                [NEGATIVE_STATE, POSITIVE_STATE]
            )
            & (pl.col("_previous_state") == pl.col("_next_state"))
            & (pl.col("_previous_end") == pl.col(episode_start_col))
            & (pl.col(episode_end_col) == pl.col("_next_start"))
        )
        .fill_null(False)
        .alias("_bridge_unknown")
    )
    marked = marked.with_columns(
        (
            pl.col("_bridge_unknown")
            | pl.col("_bridge_unknown")
            .shift(1)
            .over(encounter_col)
            .fill_null(False)
        ).alias("_connect_to_previous")
    ).with_columns(
        (~pl.col("_connect_to_previous"))
        .cast(pl.Int64)
        .cum_sum()
        .over(encounter_col)
        .alias("_bridge_group")
    )

    bridged = (
        marked.group_by(encounter_col, "_bridge_group", maintain_order=True)
        .agg(
            pl.col(state_col)
            .filter(pl.col(state_col) != UNKNOWN_STATE)
            .first()
            .fill_null(UNKNOWN_STATE)
            .alias(state_col),
            pl.col(episode_start_col).first(),
            pl.col(episode_end_col).last(),
            pl.col(source_segment_count_col).sum(),
            pl.col(episode_id_col).alias("source_episode_ids"),
            pl.len().alias("source_episode_count"),
            pl.col("_bridge_unknown")
            .sum()
            .alias("bridged_unknown_gap_count"),
        )
        .with_columns(
            pl.int_range(1, pl.len() + 1)
            .over(encounter_col)
            .alias(episode_id_col),
            (
                pl.col(episode_end_col) - pl.col(episode_start_col)
            )
            .dt.total_minutes(fractional=True)
            .alias("episode_duration_minutes"),
        )
        .with_columns(
            pl.col(episode_id_col).cast(pl.Int64),
            pl.col(state_col).cast(pl.Int8),
            pl.col("source_episode_count").cast(pl.UInt32),
            pl.col("bridged_unknown_gap_count").cast(pl.UInt32),
        )
        .select(output_schema.keys())
        .sort(encounter_col, episode_id_col)
    )
    return bridged


def merge_positive_across_short_negative_gaps(
    episodes: pl.DataFrame,
    *,
    threshold_minutes: float,
    encounter_col: str = "EncounterEpicCsn",
    episode_id_col: str = "episode_id",
    state_col: str = "state",
    episode_start_col: str = "episode_start",
    episode_end_col: str = "episode_end",
    source_segment_count_col: str = "source_segment_count",
    source_episode_ids_col: str = "source_episode_ids",
    source_episode_count_col: str = "source_episode_count",
    bridged_unknown_gap_count_col: str = "bridged_unknown_gap_count",
) -> pl.DataFrame:
    """Merge positive episodes across short measured-negative gaps.

    Input must be the three-state episode timeline produced by
    :func:`bridge_equal_states_across_unknown`. A measured-negative episode is
    absorbed only when it is directly bounded by positive episodes and its
    duration is strictly less than ``threshold_minutes``. Explicit unknown
    episodes therefore block a merge.

    All episodes that are not absorbed remain in the output. Connected chains
    of eligible gaps collapse into one positive episode, and the source lineage
    from the unknown-bridging step is retained.
    """
    try:
        threshold_minutes = float(threshold_minutes)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "threshold_minutes must be a finite non-negative number"
        ) from exc
    if not isfinite(threshold_minutes) or threshold_minutes < 0:
        raise ValueError("threshold_minutes must be a finite non-negative number")

    required_cols = {
        encounter_col,
        episode_id_col,
        state_col,
        episode_start_col,
        episode_end_col,
        source_segment_count_col,
        source_episode_ids_col,
        source_episode_count_col,
        bridged_unknown_gap_count_col,
    }
    _require_columns(episodes, required_cols)

    output_schema = {
        encounter_col: episodes.schema[encounter_col],
        episode_id_col: pl.Int64,
        state_col: pl.Int8,
        episode_start_col: episodes.schema[episode_start_col],
        episode_end_col: episodes.schema[episode_end_col],
        "episode_duration_minutes": pl.Float64,
        source_segment_count_col: episodes.schema[source_segment_count_col],
        source_episode_ids_col: episodes.schema[source_episode_ids_col],
        source_episode_count_col: pl.UInt32,
        bridged_unknown_gap_count_col: pl.UInt32,
        "bridged_negative_gap_count": pl.UInt32,
    }
    if episodes.is_empty():
        return pl.DataFrame(schema=output_schema)

    selected_cols = [
        encounter_col,
        episode_id_col,
        state_col,
        episode_start_col,
        episode_end_col,
        source_segment_count_col,
        source_episode_ids_col,
        source_episode_count_col,
        bridged_unknown_gap_count_col,
    ]
    if episodes.select(
        pl.any_horizontal(pl.col(selected_cols).is_null()).any()
    ).item():
        raise ValueError("Episode keys, boundaries, states, and lineage cannot be null")

    try:
        ordered = (
            episodes.select(selected_cols)
            .with_columns(pl.col(state_col).cast(pl.Int8, strict=True))
            .sort(encounter_col, episode_start_col, episode_end_col)
        )
    except Exception as exc:
        raise ValueError("Episode states must be integers in {-1, 0, 1}") from exc

    invalid_state_count = ordered.filter(
        ~pl.col(state_col).is_in(VALID_STATES)
    ).height
    if invalid_state_count:
        raise ValueError(
            f"Episodes contain {invalid_state_count} values outside {{-1, 0, 1}}"
        )

    duplicate_id_count = (
        ordered.group_by(encounter_col, episode_id_col)
        .len()
        .filter(pl.col("len") > 1)
        .height
    )
    if duplicate_id_count:
        raise ValueError(
            f"Episodes contain {duplicate_id_count} duplicate encounter/episode IDs"
        )

    invalid_duration_count = ordered.filter(
        pl.col(episode_end_col) <= pl.col(episode_start_col)
    ).height
    if invalid_duration_count:
        raise ValueError(
            f"Episodes contain {invalid_duration_count} non-positive intervals"
        )

    try:
        inconsistent_lineage_count = ordered.filter(
            pl.col(source_episode_ids_col).list.len()
            != pl.col(source_episode_count_col)
        ).height
    except Exception as exc:
        raise ValueError(
            "source_episode_ids must contain a list for each episode"
        ) from exc
    if inconsistent_lineage_count:
        raise ValueError(
            "source_episode_count must match the number of source_episode_ids; "
            f"found {inconsistent_lineage_count} inconsistent episodes"
        )

    ordered = ordered.with_columns(
        pl.col(state_col).shift(1).over(encounter_col).alias("_previous_state"),
        pl.col(state_col).shift(-1).over(encounter_col).alias("_next_state"),
        pl.col(episode_end_col)
        .shift(1)
        .over(encounter_col)
        .alias("_previous_end"),
        (
            pl.col(episode_end_col) - pl.col(episode_start_col)
        )
        .dt.total_minutes(fractional=True)
        .alias("_episode_duration_minutes"),
    )

    discontinuity_count = ordered.filter(
        pl.col("_previous_end").is_not_null()
        & (pl.col(episode_start_col) != pl.col("_previous_end"))
    ).height
    if discontinuity_count:
        raise ValueError(
            "Input episodes must be contiguous within each encounter; "
            f"found {discontinuity_count} gaps or overlaps"
        )

    adjacent_equal_count = ordered.filter(
        pl.col("_previous_state").is_not_null()
        & (pl.col(state_col) == pl.col("_previous_state"))
    ).height
    if adjacent_equal_count:
        raise ValueError(
            "Input must contain collapsed state episodes; "
            f"found {adjacent_equal_count} adjacent equal-state pairs"
        )

    marked = ordered.with_columns(
        (
            (pl.col(state_col) == NEGATIVE_STATE)
            & (pl.col("_previous_state") == POSITIVE_STATE)
            & (pl.col("_next_state") == POSITIVE_STATE)
            & (pl.col("_episode_duration_minutes") < threshold_minutes)
        )
        .fill_null(False)
        .alias("_merge_negative")
    )
    marked = marked.with_columns(
        (
            pl.col("_merge_negative")
            | pl.col("_merge_negative")
            .shift(1)
            .over(encounter_col)
            .fill_null(False)
        ).alias("_connect_to_previous")
    ).with_columns(
        (~pl.col("_connect_to_previous"))
        .cast(pl.Int64)
        .cum_sum()
        .over(encounter_col)
        .alias("_merge_group")
    )

    return (
        marked.group_by(encounter_col, "_merge_group", maintain_order=True)
        .agg(
            pl.col(state_col).first(),
            pl.col(episode_start_col).first(),
            pl.col(episode_end_col).last(),
            pl.col(source_segment_count_col).sum(),
            pl.col(source_episode_ids_col).explode(),
            pl.col(source_episode_count_col).sum(),
            pl.col(bridged_unknown_gap_count_col).sum(),
            pl.col("_merge_negative").any().alias("_has_merged_negative"),
            pl.col("_merge_negative").sum().alias("bridged_negative_gap_count"),
        )
        .with_columns(
            pl.when(pl.col("_has_merged_negative"))
            .then(pl.lit(POSITIVE_STATE))
            .otherwise(pl.col(state_col))
            .cast(pl.Int8)
            .alias(state_col),
            pl.int_range(1, pl.len() + 1)
            .over(encounter_col)
            .alias(episode_id_col),
            (
                pl.col(episode_end_col) - pl.col(episode_start_col)
            )
            .dt.total_minutes(fractional=True)
            .alias("episode_duration_minutes"),
            pl.col(source_episode_count_col).cast(pl.UInt32),
            pl.col(bridged_unknown_gap_count_col).cast(pl.UInt32),
            pl.col("bridged_negative_gap_count").cast(pl.UInt32),
        )
        .select(output_schema.keys())
        .sort(encounter_col, episode_id_col)
    )
