"""Identify encounter-wide pulmonary exclusion evidence."""

import polars as pl

from ...configs.pulmonarydysfunction import (
    PulmonaryDysfunctionConfig,
    pulmonary_dysfunction_config,
)


def build_pulmonary_exclusion_evidence(
    df_events: pl.DataFrame,
    *,
    config: PulmonaryDysfunctionConfig = pulmonary_dysfunction_config,
) -> pl.DataFrame:
    """Return every source event supporting a pulmonary exclusion."""
    required = {
        config.encounter_col,
        config.event_dt_col,
        config.grouper_col,
        config.raw_val_col,
    }
    missing = sorted(required.difference(df_events.columns))
    if missing:
        raise ValueError(
            "Pulmonary exclusion input is missing required columns: "
            f"{missing}"
        )

    exclusions = config.exclusions
    diagnosis_code = pl.col(config.raw_val_col).is_in(
        exclusions.diagnosis_codes
    )
    home_vent = (
        (pl.col(config.grouper_col) == exclusions.home_vent_grouper)
        & (pl.col(config.raw_val_col) == exclusions.home_vent_value)
    )

    # Approved decision: any documented dependency code or home-vent event
    # excludes pulmonary dysfunction for the entire encounter. Retain each
    # matching source row so the encounter-wide decision remains auditable.
    result = df_events.filter(diagnosis_code | home_vent).with_columns(
        pl.lit(1, dtype=pl.Int8).alias(exclusions.flag_col),
        pl.when(diagnosis_code)
        .then(
            pl.concat_str(
                pl.lit("diagnosis_code:"),
                pl.col(config.raw_val_col),
            )
        )
        .otherwise(pl.lit("home_vent"))
        .alias(exclusions.reason_col),
        pl.col(config.event_dt_col).alias(exclusions.evidence_time_col),
    )

    if result.select(
        pl.any_horizontal(
            pl.col([config.encounter_col, config.event_dt_col]).is_null()
        ).any()
    ).item():
        raise ValueError(
            "Pulmonary exclusion encounter identifiers and timestamps "
            "cannot be null"
        )

    return result
