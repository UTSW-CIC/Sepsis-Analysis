"""Construct and validate the Phase 4 encounter-level analysis cohort."""

import polars as pl

from .config import (
    ARRIVAL_COL,
    ARRIVAL_TO_SEPSIS_HOURS_COL,
    BILLED_CATEGORY_COL,
    BILLED_POA_STATUS_COL,
    BILLED_SEVERITY_COL,
    CALCULATED_CATEGORY_COL,
    CALCULATED_POA_STATUS_COL,
    CALCULATED_SEVERITY_COL,
    DEATH_COL,
    ENCOUNTER_COL,
    FIRST_SEPSIS_DT_COL,
    INPATIENT_ADMISSION_COL,
    INPATIENT_CATEGORY_COL,
    INPATIENT_POA_STATUS_COL,
    LOS_COL,
    SEPSIS_ENCOUNTER_FILENAME,
    Phase4AnalysisConfig,
)


def require_columns(
    dataframe: pl.DataFrame,
    required: set[str],
    table_name: str,
) -> None:
    """Raise a readable boundary error when an input schema is incomplete."""
    missing = sorted(required.difference(dataframe.columns))
    if missing:
        raise ValueError(f"{table_name} is missing columns: {missing}")


def build_analysis_cohort(
    df_sepsis_encounters: pl.DataFrame,
    config: Phase4AnalysisConfig,
) -> pl.DataFrame:
    """Create the one-row-per-encounter positive-sepsis analysis cohort."""
    required = {
        ENCOUNTER_COL,
        BILLED_CATEGORY_COL,
        CALCULATED_CATEGORY_COL,
        CALCULATED_SEVERITY_COL,
        CALCULATED_POA_STATUS_COL,
        FIRST_SEPSIS_DT_COL,
        ARRIVAL_COL,
        INPATIENT_ADMISSION_COL,
        LOS_COL,
        DEATH_COL,
    }
    require_columns(df_sepsis_encounters, required, SEPSIS_ENCOUNTER_FILENAME)
    if df_sepsis_encounters.select(pl.col(ENCOUNTER_COL).is_null().any()).item():
        raise ValueError("Encounter identifiers cannot be null")
    duplicate_count = (
        df_sepsis_encounters.group_by(ENCOUNTER_COL)
        .len()
        .filter(pl.col("len") > 1)
        .height
    )
    if duplicate_count:
        raise ValueError(
            "Sepsis encounter table must have one row per encounter; found "
            f"{duplicate_count} duplicate encounter identifiers"
        )

    # Preserve legacy CoreAnalysis scope while applying the owner's explicit
    # request to remove billed UPOA encounters before every denominator.
    cohort = df_sepsis_encounters.filter(
        (pl.col(CALCULATED_SEVERITY_COL) > 0)
        & pl.col(BILLED_CATEGORY_COL).is_not_null()
        & ~pl.col(BILLED_CATEGORY_COL).str.starts_with("UPOA-")
    )
    expected_categories = set(config.sepsis_categories)
    invalid_billed = sorted(
        set(cohort[BILLED_CATEGORY_COL].unique().to_list())
        .difference(expected_categories)
    )
    invalid_calculated = sorted(
        set(cohort[CALCULATED_CATEGORY_COL].unique().to_list())
        .difference(expected_categories)
    )
    if invalid_billed:
        raise ValueError(f"Unexpected billed sepsis categories: {invalid_billed}")
    if invalid_calculated:
        raise ValueError(
            f"Unexpected calculated sepsis categories: {invalid_calculated}"
        )

    required_non_null = [
        FIRST_SEPSIS_DT_COL,
        ARRIVAL_COL,
        INPATIENT_ADMISSION_COL,
        LOS_COL,
        DEATH_COL,
    ]
    null_counts = cohort.select(
        pl.col(column).is_null().sum().alias(column)
        for column in required_non_null
    ).row(0, named=True)
    missing_values = {column: count for column, count in null_counts.items() if count}
    if missing_values:
        raise ValueError(
            "Positive-sepsis analysis cohort has missing required values: "
            f"{missing_values}"
        )
    invalid_death_count = cohort.filter(~pl.col(DEATH_COL).is_in([0, 1])).height
    if invalid_death_count:
        raise ValueError(
            f"Analysis cohort has {invalid_death_count} invalid Death_Flag values"
        )

    return (
        cohort.with_columns(
            pl.when(pl.col(FIRST_SEPSIS_DT_COL) <= pl.col(INPATIENT_ADMISSION_COL))
            .then(pl.lit("POA"))
            .otherwise(pl.lit("NPOA"))
            .alias(INPATIENT_POA_STATUS_COL),
            pl.col(BILLED_CATEGORY_COL)
            .str.extract(r"(\d+)$", 1)
            .cast(pl.Int8)
            .alias(BILLED_SEVERITY_COL),
            pl.col(BILLED_CATEGORY_COL)
            .str.extract(r"^(NPOA|POA)", 1)
            .alias(BILLED_POA_STATUS_COL),
            (pl.col(FIRST_SEPSIS_DT_COL) - pl.col(ARRIVAL_COL))
            .dt.total_hours(fractional=True)
            .alias(ARRIVAL_TO_SEPSIS_HOURS_COL),
        )
        .with_columns(
            pl.concat_str(
                INPATIENT_POA_STATUS_COL,
                pl.col(CALCULATED_SEVERITY_COL).cast(pl.String),
                separator="-",
            ).alias(INPATIENT_CATEGORY_COL)
        )
        .sort(ENCOUNTER_COL)
    )
