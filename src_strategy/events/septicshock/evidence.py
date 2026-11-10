"""Build and attach auditable vasopressor evidence for septic shock."""

import polars as pl

from ...configs.septicshock import SepticShockConfig, septicshock_config


_ROW_ORDER = "__septic_shock_input_row_order"


def build_vasopressor_evidence(
    df_events: pl.DataFrame,
    *,
    config: SepticShockConfig = septicshock_config,
) -> pl.DataFrame:
    """Link orders to administrations and mark positive administered doses.

    Every source vasopressor row remains visible. An order supplies an audit
    anchor only when it shares encounter, grouper, and Event_ID with an
    administration. Administration without a linked order remains eligible and
    uses its own timestamp as the anchor.
    """
    criterion = config.vasopressor_criteria
    required = {
        config.encounter_col,
        config.event_dt_col,
        config.type_col,
        config.grouper_col,
        config.event_name_col,
        criterion.dose_col,
    }
    missing = sorted(required.difference(df_events.columns))
    if missing:
        raise ValueError(
            "Vasopressor evidence input is missing required columns: "
            f"{missing}"
        )

    evidence = df_events.filter(
        pl.col(config.grouper_col).is_in(criterion.grouper_values)
    )
    if evidence.select(
        pl.any_horizontal(
            pl.col([config.encounter_col, config.event_dt_col]).is_null()
        ).any()
    ).item():
        raise ValueError(
            "Vasopressor evidence encounter identifiers and timestamps "
            "cannot be null"
        )

    event_id_col = config.event_id
    if event_id_col not in evidence.columns:
        evidence = evidence.with_columns(
            pl.lit(None, dtype=pl.Int64).alias(event_id_col)
        )

    link_keys = [config.encounter_col, config.grouper_col, event_id_col]
    linked_orders = (
        evidence.filter(
            (pl.col(config.type_col) == criterion.order_type_value)
            & pl.col(event_id_col).is_not_null()
        )
        .group_by(link_keys)
        .agg(
            pl.col(config.event_dt_col)
            .min()
            .alias(criterion.order_datetime_col),
            pl.col(config.event_dt_col).n_unique().alias("_order_time_count"),
        )
    )
    ambiguous_order_links = linked_orders.filter(
        pl.col("_order_time_count") > 1
    ).height
    if ambiguous_order_links:
        raise ValueError(
            "Vasopressor linkage found "
            f"{ambiguous_order_links} encounter/grouper/Event_ID keys with "
            "multiple distinct order timestamps"
        )
    linked_orders = linked_orders.drop("_order_time_count")
    evidence = evidence.join(
        linked_orders,
        on=link_keys,
        how="left",
        validate="m:1",
    )

    # Approved decision: an order alone does not establish shock. A row
    # qualifies only when it records an actual medication administration with
    # a positive dose. Zero and null doses remain in this evidence table.
    qualifying_dose = (
        (pl.col(config.type_col) == criterion.administration_type_value)
        & pl.col(criterion.dose_col).is_not_null()
        & (pl.col(criterion.dose_col) > 0)
    )
    return (
        evidence.with_columns(
            pl.when(
                pl.col(config.type_col) == criterion.administration_type_value
            )
            .then(pl.col(config.event_dt_col))
            .otherwise(pl.lit(None, dtype=evidence.schema[config.event_dt_col]))
            .alias(criterion.administration_datetime_col),
            qualifying_dose.cast(pl.Int8).alias(
                criterion.qualifying_dose_flag_col
            ),
        )
        .with_columns(
            pl.when(pl.col(criterion.qualifying_dose_flag_col) == 1)
            .then(
                pl.coalesce(
                    criterion.order_datetime_col,
                    criterion.administration_datetime_col,
                )
            )
            .otherwise(pl.lit(None, dtype=evidence.schema[config.event_dt_col]))
            .alias(criterion.anchor_datetime_col)
        )
        .select(
            config.encounter_col,
            config.event_dt_col,
            event_id_col,
            config.type_col,
            config.grouper_col,
            config.event_name_col,
            criterion.dose_col,
            criterion.order_datetime_col,
            criterion.administration_datetime_col,
            criterion.anchor_datetime_col,
            criterion.qualifying_dose_flag_col,
        )
        .sort(
            config.encounter_col,
            config.event_dt_col,
            config.grouper_col,
            config.event_name_col,
        )
    )


def build_lactate_gt2_evidence(
    df_events: pl.DataFrame,
    *,
    config: SepticShockConfig = septicshock_config,
) -> pl.DataFrame:
    """Return one auditable event row for every lactate result above 2."""
    criterion = config.lactate2_criteria
    required = {
        config.encounter_col,
        config.event_dt_col,
        config.type_col,
        config.grouper_col,
        config.event_name_col,
        config.val_col,
    }
    missing = sorted(required.difference(df_events.columns))
    if missing:
        raise ValueError(
            f"Lactate >2 evidence input is missing required columns: {missing}"
        )

    event_id_col = config.event_id
    events = df_events
    if event_id_col not in events.columns:
        events = events.with_columns(
            pl.lit(None, dtype=pl.Int64).alias(event_id_col)
        )

    evidence = (
        events.filter(
            (pl.col(config.type_col) == criterion.event_type_value)
            & (pl.col(config.grouper_col) == criterion.event_grouper_value)
            & pl.col(config.val_col).is_not_null()
            & (pl.col(config.val_col) > criterion.lactate_threshold)
        )
        .sort(
            config.encounter_col,
            config.event_dt_col,
            event_id_col,
            config.event_name_col,
        )
        .with_columns(
            pl.int_range(1, pl.len() + 1)
            .over(config.encounter_col)
            .cast(pl.Int64)
            .alias(criterion.evidence_id_col),
            pl.col(config.event_dt_col).alias(criterion.evidence_datetime_col),
            pl.col(config.val_col).alias(criterion.evidence_value_col),
        )
        .select(
            config.encounter_col,
            criterion.evidence_id_col,
            criterion.evidence_datetime_col,
            criterion.evidence_value_col,
            pl.col(config.type_col).alias("lactate_source_type"),
            pl.col(event_id_col).alias("lactate_source_event_id"),
            pl.col(config.event_name_col).alias("lactate_source_event_name"),
        )
    )
    return evidence


def attach_vasopressor_evidence(
    df_timeline: pl.DataFrame,
    df_vasopressor_evidence: pl.DataFrame,
    *,
    config: SepticShockConfig = septicshock_config,
) -> pl.DataFrame:
    """Attach exact-time vasopressor counts and administration state."""
    criterion = config.vasopressor_criteria
    keys = [config.encounter_col, config.event_dt_col]
    output_cols = [
        criterion.evidence_event_count_col,
        criterion.qualifying_dose_count_col,
        criterion.administered_flag_col,
    ]

    missing_timeline = sorted(set(keys).difference(df_timeline.columns))
    if missing_timeline:
        raise ValueError(
            "Septic-shock timeline is missing required columns: "
            f"{missing_timeline}"
        )
    required_evidence = {*keys, criterion.qualifying_dose_flag_col}
    missing_evidence = sorted(
        required_evidence.difference(df_vasopressor_evidence.columns)
    )
    if missing_evidence:
        raise ValueError(
            "Vasopressor evidence is missing required columns: "
            f"{missing_evidence}"
        )
    existing_outputs = sorted(set(output_cols).intersection(df_timeline.columns))
    if existing_outputs:
        raise ValueError(
            "Septic-shock timeline already contains vasopressor outputs: "
            f"{existing_outputs}"
        )
    if _ROW_ORDER in df_timeline.columns:
        raise ValueError(
            f"Septic-shock timeline contains reserved column {_ROW_ORDER!r}"
        )
    if df_timeline.select(pl.any_horizontal(pl.col(keys).is_null()).any()).item():
        raise ValueError("Septic-shock timeline keys cannot be null")
    duplicate_timeline_count = (
        df_timeline.group_by(keys)
        .len()
        .filter(pl.col("len") > 1)
        .height
    )
    if duplicate_timeline_count:
        raise ValueError(
            "Septic-shock timeline must have one row per encounter and "
            f"timestamp; found {duplicate_timeline_count} duplicate keys"
        )

    timeline_keys = df_timeline.select(keys)
    unmatched_evidence_count = (
        df_vasopressor_evidence.select(keys)
        .unique()
        .join(timeline_keys, on=keys, how="anti")
        .height
    )
    if unmatched_evidence_count:
        raise ValueError(
            f"Vasopressor evidence has {unmatched_evidence_count} timestamps "
            "that are absent from the septic-shock timeline"
        )

    by_instant = df_vasopressor_evidence.group_by(keys).agg(
        pl.len().cast(pl.Int64).alias(criterion.evidence_event_count_col),
        pl.col(criterion.qualifying_dose_flag_col)
        .sum()
        .cast(pl.Int64)
        .alias(criterion.qualifying_dose_count_col),
    ).with_columns(
        (pl.col(criterion.qualifying_dose_count_col) > 0)
        .cast(pl.Int8)
        .alias(criterion.administered_flag_col)
    )

    original_cols = df_timeline.columns
    result = (
        df_timeline.with_row_index(_ROW_ORDER)
        .join(by_instant, on=keys, how="left", validate="1:1")
        .with_columns(
            pl.col(criterion.evidence_event_count_col).fill_null(0),
            pl.col(criterion.qualifying_dose_count_col).fill_null(0),
            pl.col(criterion.administered_flag_col).fill_null(0),
        )
        .sort(_ROW_ORDER)
        .select(*original_cols, *output_cols)
    )
    if result.height != df_timeline.height:
        raise RuntimeError("Vasopressor attachment changed the timeline row count")
    if not result.select(original_cols).equals(df_timeline):
        raise RuntimeError("Vasopressor attachment changed existing timeline values")
    return result


def prepare_septic_shock_input(
    df_timeline: pl.DataFrame,
    df_encounters: pl.DataFrame,
    df_vasopressor_evidence: pl.DataFrame,
    *,
    config: SepticShockConfig = septicshock_config,
) -> pl.DataFrame:
    """Add the approved SBP baseline and exact-time vasopressor evidence."""
    encounter_col = config.encounter_col
    baseline_col = config.sbpdelta40_criteria.baseline_sbp_col.value
    availability_col = config.baseline_encounter_row_available_col
    missing_encounter = sorted(
        {encounter_col, baseline_col}.difference(df_encounters.columns)
    )
    if missing_encounter:
        raise ValueError(
            "Septic-shock encounter input is missing required columns: "
            f"{missing_encounter}"
        )
    protected = {baseline_col, availability_col}
    existing_protected = sorted(protected.intersection(df_timeline.columns))
    if existing_protected:
        raise ValueError(
            "Septic-shock timeline already contains baseline outputs: "
            f"{existing_protected}"
        )
    if df_encounters.select(pl.col(encounter_col).is_null().any()).item():
        raise ValueError("Septic-shock encounter identifiers cannot be null")
    duplicate_encounter_count = (
        df_encounters.group_by(encounter_col)
        .len()
        .filter(pl.col("len") > 1)
        .height
    )
    if duplicate_encounter_count:
        raise ValueError(
            "Septic-shock encounter input must have one row per encounter; "
            f"found {duplicate_encounter_count} duplicate encounter IDs"
        )

    original_cols = df_timeline.columns
    with_baseline = (
        df_timeline.join(
            df_encounters.select(encounter_col, baseline_col).with_columns(
                pl.lit(True).alias(availability_col)
            ),
            on=encounter_col,
            how="left",
            validate="m:1",
        )
        .with_columns(pl.col(availability_col).fill_null(False))
    )
    if with_baseline.height != df_timeline.height:
        raise RuntimeError("Septic-shock baseline join changed the timeline row count")
    if not with_baseline.select(original_cols).equals(df_timeline):
        raise RuntimeError("Septic-shock baseline join changed existing values")

    return attach_vasopressor_evidence(
        with_baseline,
        df_vasopressor_evidence,
        config=config,
    )
