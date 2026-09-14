"""Reconstruct pulmonary state from explicit start and termination evidence."""

import polars as pl

from ...configs.pulmonarydysfunction import (
    PulmonaryDysfunctionConfig,
    pulmonary_dysfunction_config,
)
from .exclusions import build_pulmonary_exclusion_evidence
from .pipeline import (
    build_pulmonary_pf_start_pipeline,
    build_pulmonary_pf_termination_pipeline,
    build_pulmonary_raw_start_pipeline,
    build_pulmonary_raw_termination_pipeline,
)


_CHANGE_TIME = "_pulmonary_change_time"
_TRANSITION_TYPE = "_pulmonary_transition_type"
_TRANSITION_STATE = "_pulmonary_transition_state"


def _timeline_schema(
    df_events: pl.DataFrame,
    config: PulmonaryDysfunctionConfig,
) -> dict[str, pl.DataType]:
    event_time_type = df_events.schema[config.event_dt_col]
    return {
        config.encounter_col: df_events.schema[config.encounter_col],
        config.state_time_col: event_time_type,
        config.pulmonary_dysfunction_flag: pl.Int8,
        config.transition_time_col: event_time_type,
        config.transition_type_col: pl.List(pl.String),
        config.exclusions.flag_col: pl.Int8,
        config.exclusions.reason_col: pl.List(pl.String),
        config.exclusions.evidence_time_col: pl.List(event_time_type),
    }


def _raw_transition_rows(
    df_events: pl.DataFrame,
    config: PulmonaryDysfunctionConfig,
) -> pl.DataFrame:
    relevant_groupers = [
        config.vent_documentation.start_grouper,
        config.vent_documentation.termination_grouper,
        config.vent_onoff.grouper,
        config.o2_delivery.mechanical_grouper,
        *config.o2_delivery.termination_groupers,
    ]
    relevant = df_events.filter(
        pl.col(config.grouper_col).is_in(relevant_groupers)
    )
    started = build_pulmonary_raw_start_pipeline(config).process(relevant)
    scored = build_pulmonary_raw_termination_pipeline(config).process(started)

    vent_documentation = config.vent_documentation
    vent_onoff = config.vent_onoff
    o2 = config.o2_delivery
    return (
        scored.filter(
            (pl.col(config.start_flag_col) == 1)
            | (pl.col(config.termination_flag_col) == 1)
        )
        .with_columns(
            pl.when(pl.col(vent_documentation.termination_flag_col) == 1)
            .then(pl.lit("vent_documentation_termination"))
            .when(pl.col(vent_onoff.termination_flag_col) == 1)
            .then(pl.lit("vent_onoff_termination"))
            .when(pl.col(o2.termination_flag_col) == 1)
            .then(pl.lit("o2_delivery_termination"))
            .when(pl.col(vent_documentation.start_flag_col) == 1)
            .then(pl.lit("vent_documentation_start"))
            .when(pl.col(vent_onoff.start_flag_col) == 1)
            .then(pl.lit("vent_onoff_start"))
            .when(pl.col(o2.start_flag_col) == 1)
            .then(pl.lit("mechanical_o2_start"))
            .otherwise(pl.lit(None, dtype=pl.String))
            .alias(_TRANSITION_TYPE)
        )
        .select(
            config.encounter_col,
            pl.col(config.event_dt_col).alias(_CHANGE_TIME),
            config.start_flag_col,
            config.termination_flag_col,
            _TRANSITION_TYPE,
        )
    )


def _pf_transition_rows(
    df_pf_events: pl.DataFrame,
    config: PulmonaryDysfunctionConfig,
) -> pl.DataFrame:
    started = build_pulmonary_pf_start_pipeline(config).process(df_pf_events)
    scored = build_pulmonary_pf_termination_pipeline(config).process(started)
    pf = config.pf
    return (
        scored.filter(
            (pl.col(config.start_flag_col) == 1)
            | (pl.col(config.termination_flag_col) == 1)
        )
        .with_columns(
            pl.when(pl.col(pf.termination_flag_col) == 1)
            .then(pl.lit("pf_ratio_termination"))
            .when(pl.col(pf.start_flag_col) == 1)
            .then(pl.lit("pf_ratio_start"))
            .otherwise(pl.lit(None, dtype=pl.String))
            .alias(_TRANSITION_TYPE)
        )
        .select(
            config.encounter_col,
            pl.col(pf.pf_ratio_time_col).alias(_CHANGE_TIME),
            config.start_flag_col,
            config.termination_flag_col,
            _TRANSITION_TYPE,
        )
    )


def build_pulmonary_state_timeline(
    df_events: pl.DataFrame,
    df_pf_events: pl.DataFrame,
    *,
    config: PulmonaryDysfunctionConfig = pulmonary_dysfunction_config,
) -> pl.DataFrame:
    """Return pulmonary state at encounter bounds and every transition time."""
    missing_events = sorted(
        set(config.required_event_columns).difference(df_events.columns)
    )
    if missing_events:
        raise ValueError(
            "Pulmonary state event input is missing required columns: "
            f"{missing_events}"
        )
    missing_pf = sorted(
        set(config.required_pf_columns).difference(df_pf_events.columns)
    )
    if missing_pf:
        raise ValueError(
            "Pulmonary state P/F input is missing required columns: "
            f"{missing_pf}"
        )

    output_schema = _timeline_schema(df_events, config)
    if df_events.is_empty():
        return pl.DataFrame(schema=output_schema)
    if df_events.select(
        pl.any_horizontal(
            pl.col([config.encounter_col, config.event_dt_col]).is_null()
        ).any()
    ).item():
        raise ValueError(
            "Pulmonary state encounter identifiers and timestamps cannot be null"
        )

    bounds = df_events.group_by(config.encounter_col).agg(
        pl.col(config.event_dt_col).min().alias("_encounter_start"),
        pl.col(config.event_dt_col).max().alias("_encounter_end"),
    )
    transition_rows = pl.concat(
        [
            _raw_transition_rows(df_events, config),
            _pf_transition_rows(df_pf_events, config),
        ],
        how="vertical_relaxed",
    )
    transitions = (
        transition_rows.group_by(config.encounter_col, _CHANGE_TIME)
        .agg(
            pl.col(config.start_flag_col).max(),
            pl.col(config.termination_flag_col).max(),
            pl.col(_TRANSITION_TYPE)
            .drop_nulls()
            .unique()
            .sort()
            .alias(config.transition_type_col),
        )
        # Approved decision: termination wins when start and termination
        # evidence occur at the same encounter timestamp.
        .with_columns(
            pl.when(pl.col(config.termination_flag_col) == 1)
            .then(pl.lit(0, dtype=pl.Int8))
            .when(pl.col(config.start_flag_col) == 1)
            .then(pl.lit(1, dtype=pl.Int8))
            .otherwise(pl.lit(None, dtype=pl.Int8))
            .alias(_TRANSITION_STATE),
            pl.col(_CHANGE_TIME).alias(config.transition_time_col),
        )
        .sort(config.encounter_col, _CHANGE_TIME)
    )

    points = pl.concat(
        [
            bounds.select(
                config.encounter_col,
                pl.col("_encounter_start").alias(_CHANGE_TIME),
            ),
            bounds.select(
                config.encounter_col,
                pl.col("_encounter_end").alias(_CHANGE_TIME),
            ),
            transitions.select(config.encounter_col, _CHANGE_TIME),
        ],
        how="vertical",
    ).unique().sort(config.encounter_col, _CHANGE_TIME)

    if transitions.is_empty():
        points = points.with_columns(
            pl.lit(None, dtype=pl.Int8).alias(_TRANSITION_STATE),
            pl.lit(None, dtype=df_events.schema[config.event_dt_col]).alias(
                config.transition_time_col
            ),
            pl.lit(None, dtype=pl.List(pl.String)).alias(
                config.transition_type_col
            ),
        )
    else:
        points = points.join_asof(
            transitions.select(
                config.encounter_col,
                _CHANGE_TIME,
                _TRANSITION_STATE,
                config.transition_time_col,
                config.transition_type_col,
            ),
            on=_CHANGE_TIME,
            by=config.encounter_col,
            strategy="backward",
            check_sortedness=False,
        )

    exclusion_evidence = build_pulmonary_exclusion_evidence(
        df_events,
        config=config,
    )
    exclusions = exclusion_evidence.group_by(config.encounter_col).agg(
        pl.col(config.exclusions.flag_col).max(),
        pl.col(config.exclusions.reason_col)
        .unique()
        .sort()
        .alias(config.exclusions.reason_col),
        pl.col(config.exclusions.evidence_time_col)
        .sort()
        .alias(config.exclusions.evidence_time_col),
    )
    points = points.join(
        exclusions,
        on=config.encounter_col,
        how="left",
        validate="m:1",
    ).with_columns(
        pl.col(config.exclusions.flag_col).fill_null(0).cast(pl.Int8)
    )

    # Approved decision: an encounter-level dependency exclusion forces the
    # pulmonary state to 0 for the entire encounter without deleting evidence.
    # Approved decision: before the first transition, do not fill the null
    # state; null explicitly represents unknown pulmonary evidence.
    state = (
        pl.when(pl.col(config.exclusions.flag_col) == 1)
        .then(pl.lit(0, dtype=pl.Int8))
        .otherwise(pl.col(_TRANSITION_STATE))
    )
    return (
        points.with_columns(
            pl.col(_CHANGE_TIME).alias(config.state_time_col),
            state.alias(config.pulmonary_dysfunction_flag),
        )
        .select(output_schema.keys())
        .sort(config.encounter_col, config.state_time_col)
    )


def build_pulmonary_state_segments(
    df_events: pl.DataFrame,
    df_pf_events: pl.DataFrame,
    *,
    config: PulmonaryDysfunctionConfig = pulmonary_dysfunction_config,
) -> pl.DataFrame:
    """Convert pulmonary state change points into half-open intervals."""
    timeline = build_pulmonary_state_timeline(
        df_events,
        df_pf_events,
        config=config,
    )
    return (
        timeline.with_columns(
            pl.col(config.state_time_col).alias(config.segment_start_col),
            pl.col(config.state_time_col)
            .shift(-1)
            .over(config.encounter_col)
            .alias(config.segment_end_col),
        )
        .filter(
            pl.col(config.segment_end_col).is_not_null()
            & (
                pl.col(config.segment_end_col)
                > pl.col(config.segment_start_col)
            )
        )
        .drop(config.state_time_col)
    )
