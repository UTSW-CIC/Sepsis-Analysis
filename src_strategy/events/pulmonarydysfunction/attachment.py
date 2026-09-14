"""Attach reconstructed pulmonary state to the temporal wide table."""

import polars as pl

from ...configs.pulmonarydysfunction import (
    PulmonaryDysfunctionConfig,
    pulmonary_dysfunction_config,
)


_ROW_ORDER = "__pulmonary_input_row_order"


def attach_pulmonary_state(
    df_aggregated: pl.DataFrame,
    df_state_timeline: pl.DataFrame,
    *,
    config: PulmonaryDysfunctionConfig = pulmonary_dysfunction_config,
) -> pl.DataFrame:
    """Add the latest pulmonary state and evidence to each aggregate row.

    The aggregate dataframe remains the authoritative row set. The function
    rejects duplicate keys and existing pulmonary output columns so that the
    temporal join cannot multiply rows or silently overwrite prior work.
    """
    encounter_col = config.encounter_col
    aggregate_time_col = config.event_dt_col
    timeline_time_col = config.state_time_col
    output_cols = [
        config.pulmonary_dysfunction_flag,
        config.transition_time_col,
        config.transition_type_col,
        config.exclusions.flag_col,
        config.exclusions.reason_col,
        config.exclusions.evidence_time_col,
    ]

    missing_aggregate = sorted(
        {encounter_col, aggregate_time_col}.difference(df_aggregated.columns)
    )
    if missing_aggregate:
        raise ValueError(
            "Pulmonary aggregate input is missing required columns: "
            f"{missing_aggregate}"
        )

    required_timeline = {encounter_col, timeline_time_col, *output_cols}
    missing_timeline = sorted(
        required_timeline.difference(df_state_timeline.columns)
    )
    if missing_timeline:
        raise ValueError(
            "Pulmonary state timeline is missing required columns: "
            f"{missing_timeline}"
        )

    existing_outputs = sorted(set(output_cols).intersection(df_aggregated.columns))
    if existing_outputs:
        raise ValueError(
            "Pulmonary aggregate input already contains columns that the "
            f"state attachment would overwrite: {existing_outputs}"
        )
    if _ROW_ORDER in df_aggregated.columns:
        raise ValueError(
            f"Pulmonary aggregate input contains reserved column {_ROW_ORDER!r}"
        )

    aggregate_keys = [encounter_col, aggregate_time_col]
    timeline_keys = [encounter_col, timeline_time_col]
    if df_aggregated.select(
        pl.any_horizontal(pl.col(aggregate_keys).is_null()).any()
    ).item():
        raise ValueError(
            "Pulmonary aggregate encounter identifiers and timestamps cannot "
            "be null"
        )
    if df_state_timeline.select(
        pl.any_horizontal(pl.col(timeline_keys).is_null()).any()
    ).item():
        raise ValueError(
            "Pulmonary state timeline encounter identifiers and timestamps "
            "cannot be null"
        )

    duplicate_aggregate_count = (
        df_aggregated.group_by(aggregate_keys)
        .len()
        .filter(pl.col("len") > 1)
        .height
    )
    if duplicate_aggregate_count:
        raise ValueError(
            "Pulmonary aggregate input must have one row per encounter and "
            f"timestamp; found {duplicate_aggregate_count} duplicate keys"
        )
    duplicate_timeline_count = (
        df_state_timeline.group_by(timeline_keys)
        .len()
        .filter(pl.col("len") > 1)
        .height
    )
    if duplicate_timeline_count:
        raise ValueError(
            "Pulmonary state timeline must have one row per encounter and "
            f"timestamp; found {duplicate_timeline_count} duplicate keys"
        )

    if df_aggregated.schema[encounter_col] != df_state_timeline.schema[encounter_col]:
        raise ValueError(
            "Pulmonary aggregate and state timeline encounter identifier "
            "types must match"
        )
    if df_aggregated.schema[aggregate_time_col] != df_state_timeline.schema[timeline_time_col]:
        raise ValueError(
            "Pulmonary aggregate and state timeline timestamp types must match"
        )

    original_cols = df_aggregated.columns
    result = (
        df_aggregated.with_row_index(_ROW_ORDER)
        .sort(encounter_col, aggregate_time_col)
        # Pulmonary state persists until the next explicit transition, so each
        # wide-table instant receives the latest state at or before that time.
        .join_asof(
            df_state_timeline.select(
                encounter_col,
                timeline_time_col,
                *output_cols,
            ).sort(encounter_col, timeline_time_col),
            left_on=aggregate_time_col,
            right_on=timeline_time_col,
            by=encounter_col,
            strategy="backward",
            check_sortedness=False,
        )
        .with_columns(
            pl.col(config.exclusions.flag_col).fill_null(0).cast(pl.Int8)
        )
        .sort(_ROW_ORDER)
        .select(*original_cols, *output_cols)
    )

    if result.height != df_aggregated.height:
        raise RuntimeError(
            "Pulmonary state attachment changed the aggregate row count"
        )
    if not result.select(original_cols).equals(df_aggregated):
        raise RuntimeError(
            "Pulmonary state attachment changed existing aggregate values"
        )
    return result
