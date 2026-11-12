"""Aggregate analyses of qualifying Phase 4 vasopressor administrations."""

import polars as pl

from .category_tables import category_counts, category_crosstab_long
from .cohort import require_columns
from .config import (
    ARRIVAL_COL,
    BILLED_CATEGORY_COL,
    CALCULATED_CATEGORY_COL,
    ENCOUNTER_COL,
    INPATIENT_ADMISSION_COL,
    VASOPRESSOR_EVIDENCE_FILENAME,
    Phase4AnalysisConfig,
)


def build_first_vasopressor_table(
    cohort: pl.DataFrame,
    df_vasopressor_evidence: pl.DataFrame,
) -> pl.DataFrame:
    """Attach first qualifying Phase 4 vasopressor administration per encounter."""
    required = {
        ENCOUNTER_COL,
        "vasopressor_administration_time",
        "vasopressor_qualifying_dose_flag",
    }
    require_columns(
        df_vasopressor_evidence,
        required,
        VASOPRESSOR_EVIDENCE_FILENAME,
    )
    first_administration = (
        df_vasopressor_evidence.filter(
            (pl.col("vasopressor_qualifying_dose_flag") == 1)
            & pl.col("vasopressor_administration_time").is_not_null()
        )
        .group_by(ENCOUNTER_COL)
        .agg(
            pl.col("vasopressor_administration_time")
            .min()
            .alias("first_vasopressor_administration_time")
        )
    )
    return (
        cohort.join(
            first_administration,
            on=ENCOUNTER_COL,
            how="inner",
            validate="1:1",
        )
        .with_columns(
            (
                pl.col("first_vasopressor_administration_time")
                - pl.col(ARRIVAL_COL)
            )
            .dt.total_hours(fractional=True)
            .alias("arrival_to_first_vasopressor_hours"),
            (
                pl.col("first_vasopressor_administration_time")
                - pl.col(INPATIENT_ADMISSION_COL)
            )
            .dt.total_hours(fractional=True)
            .alias("admission_to_first_vasopressor_hours"),
        )
    )


def _vasopressor_windows(
    first_vasopressor: pl.DataFrame,
    config: Phase4AnalysisConfig,
) -> list[tuple[str, pl.DataFrame]]:
    return [
        (
            "within_48h_of_arrival",
            first_vasopressor.filter(
                pl.col("arrival_to_first_vasopressor_hours")
                < config.arrival_vasopressor_window_hours
            ),
        ),
        (
            "within_24h_of_inpatient_admission",
            first_vasopressor.filter(
                pl.col("admission_to_first_vasopressor_hours")
                < config.inpatient_vasopressor_window_hours
            ),
        ),
    ]


def build_vasopressor_window_category_counts(
    first_vasopressor: pl.DataFrame,
    config: Phase4AnalysisConfig,
) -> pl.DataFrame:
    """Count billed/calculated categories in the two legacy pressor windows."""
    outputs = []
    for window, subset in _vasopressor_windows(first_vasopressor, config):
        outputs.extend(
            [
                category_counts(
                    subset,
                    BILLED_CATEGORY_COL,
                    "billed",
                    config,
                ).with_columns(pl.lit(window).alias("vasopressor_window")),
                category_counts(
                    subset,
                    CALCULATED_CATEGORY_COL,
                    "calculated_arrival_plus_48h",
                    config,
                ).with_columns(pl.lit(window).alias("vasopressor_window")),
            ]
        )
    return pl.concat(outputs, how="vertical").select(
        "vasopressor_window",
        "category_source",
        "category",
        "encounter_count",
        "denominator",
        "proportion",
    )


def build_vasopressor_window_crosstabs(
    first_vasopressor: pl.DataFrame,
    config: Phase4AnalysisConfig,
) -> pl.DataFrame:
    """Build the two legacy pressor-window calculated/billed crosstabs."""
    outputs = []
    for window, subset in _vasopressor_windows(first_vasopressor, config):
        outputs.append(
            category_crosstab_long(
                subset,
                CALCULATED_CATEGORY_COL,
                "arrival_plus_48h",
                config,
            ).with_columns(pl.lit(window).alias("vasopressor_window"))
        )
    return pl.concat(outputs, how="vertical").select(
        "vasopressor_window",
        "calculated_reference",
        "calculated_category",
        "billed_category",
        "encounter_count",
        "calculated_category_total",
        "billed_category_total",
        "row_proportion",
        "column_proportion",
    )
