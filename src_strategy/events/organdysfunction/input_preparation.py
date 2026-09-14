"""Prepare encounter baselines for organ-dysfunction criteria."""

import polars as pl

from ...configs.organdysfunction import (
    OrganDysfunctionConfig,
    organdysfunction_config,
)


BASELINE_ROW_AVAILABLE = "baseline_encounter_row_available"


def prepare_organ_dysfunction_input(
    df_aggregated: pl.DataFrame,
    df_encounters: pl.DataFrame,
    *,
    config: OrganDysfunctionConfig = organdysfunction_config,
) -> pl.DataFrame:
    """Left-join the baselines required by implemented organ criteria.

    The aggregated timeline remains the authoritative row set. Encounter rows
    add only the four configured baselines and an availability marker so that
    a missing encounter row is distinguishable from null baseline values.
    Existing columns are never overwritten.
    """
    encounter_col = config.encounter_col
    baseline_cols = [
        config.renal.baseline_creatinine_col.value,
        config.renal.baseline_egfr_col.value,
        config.hepatic.baseline_bilirubin_col.value,
        config.coagulation.baseline_platelets_col.value,
    ]

    missing_aggregated = sorted(
        {encounter_col}.difference(df_aggregated.columns)
    )
    if missing_aggregated:
        raise ValueError(
            "Organ-dysfunction aggregate input is missing required columns: "
            f"{missing_aggregated}"
        )

    missing_encounter = sorted(
        {encounter_col, *baseline_cols}.difference(df_encounters.columns)
    )
    if missing_encounter:
        raise ValueError(
            "Organ-dysfunction encounter input is missing required columns: "
            f"{missing_encounter}"
        )

    protected_cols = [*baseline_cols, BASELINE_ROW_AVAILABLE]
    existing_protected = sorted(
        set(protected_cols).intersection(df_aggregated.columns)
    )
    if existing_protected:
        raise ValueError(
            "Organ-dysfunction aggregate input already contains columns that "
            f"the baseline join would overwrite: {existing_protected}"
        )

    if df_aggregated.select(pl.col(encounter_col).is_null().any()).item():
        raise ValueError(
            "Organ-dysfunction aggregate encounter identifiers cannot be null"
        )
    if df_encounters.select(pl.col(encounter_col).is_null().any()).item():
        raise ValueError(
            "Organ-dysfunction encounter identifiers cannot be null"
        )

    duplicate_encounter_count = (
        df_encounters.group_by(encounter_col)
        .len()
        .filter(pl.col("len") > 1)
        .height
    )
    if duplicate_encounter_count:
        raise ValueError(
            "Organ-dysfunction encounter input must have one row per "
            f"encounter; found {duplicate_encounter_count} duplicate "
            "encounter IDs"
        )

    result = (
        df_aggregated.join(
            df_encounters.select(encounter_col, *baseline_cols).with_columns(
                pl.lit(True).alias(BASELINE_ROW_AVAILABLE)
            ),
            on=encounter_col,
            how="left",
            validate="m:1",
        )
        .with_columns(pl.col(BASELINE_ROW_AVAILABLE).fill_null(False))
    )

    if result.height != df_aggregated.height:
        raise RuntimeError(
            "Organ-dysfunction baseline join changed the aggregate row count"
        )

    return result
