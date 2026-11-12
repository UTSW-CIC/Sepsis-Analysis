"""Category counts, POA counts, and calculated-versus-billed crosstabs."""

import polars as pl

from .config import (
    BILLED_CATEGORY_COL,
    BILLED_POA_STATUS_COL,
    CALCULATED_CATEGORY_COL,
    CALCULATED_POA_STATUS_COL,
    INPATIENT_CATEGORY_COL,
    INPATIENT_POA_STATUS_COL,
    Phase4AnalysisConfig,
)


def category_counts(
    dataframe: pl.DataFrame,
    category_col: str,
    source: str,
    config: Phase4AnalysisConfig,
) -> pl.DataFrame:
    """Count all configured categories, including categories with zero rows."""
    counts = dataframe.group_by(category_col).len().rename(
        {category_col: "category", "len": "encounter_count"}
    )
    denominator = dataframe.height
    return (
        pl.DataFrame({"category": config.sepsis_categories})
        .join(counts, on="category", how="left")
        .with_columns(
            pl.col("encounter_count").fill_null(0).cast(pl.Int64),
            pl.lit(denominator, dtype=pl.Int64).alias("denominator"),
            pl.lit(source).alias("category_source"),
        )
        .with_columns(
            pl.when(pl.col("denominator") > 0)
            .then(pl.col("encounter_count") / pl.col("denominator"))
            .otherwise(pl.lit(0.0))
            .alias("proportion")
        )
        .select(
            "category_source",
            "category",
            "encounter_count",
            "denominator",
            "proportion",
        )
    )


def build_category_counts(
    cohort: pl.DataFrame,
    config: Phase4AnalysisConfig,
) -> pl.DataFrame:
    """Count categories for billing and both calculated timing references."""
    return pl.concat(
        [
            category_counts(cohort, BILLED_CATEGORY_COL, "billed", config),
            category_counts(
                cohort,
                CALCULATED_CATEGORY_COL,
                "calculated_arrival_plus_48h",
                config,
            ),
            category_counts(
                cohort,
                INPATIENT_CATEGORY_COL,
                "calculated_inpatient_admission",
                config,
            ),
        ],
        how="vertical",
    )


def _poa_status_counts(
    dataframe: pl.DataFrame,
    status_col: str,
    source: str,
    config: Phase4AnalysisConfig,
) -> pl.DataFrame:
    counts = dataframe.group_by(status_col).len().rename(
        {status_col: "poa_status", "len": "encounter_count"}
    )
    denominator = dataframe.height
    return (
        pl.DataFrame({"poa_status": config.poa_statuses})
        .join(counts, on="poa_status", how="left")
        .with_columns(
            pl.col("encounter_count").fill_null(0).cast(pl.Int64),
            pl.lit(denominator, dtype=pl.Int64).alias("denominator"),
            pl.lit(source).alias("category_source"),
        )
        .with_columns(
            pl.when(pl.col("denominator") > 0)
            .then(pl.col("encounter_count") / pl.col("denominator"))
            .otherwise(pl.lit(0.0))
            .alias("proportion")
        )
        .select(
            "category_source",
            "poa_status",
            "encounter_count",
            "denominator",
            "proportion",
        )
    )


def build_poa_status_counts(
    cohort: pl.DataFrame,
    config: Phase4AnalysisConfig,
) -> pl.DataFrame:
    """Reproduce the legacy three-source POA/NPOA count comparison."""
    return pl.concat(
        [
            _poa_status_counts(
                cohort,
                BILLED_POA_STATUS_COL,
                "billed",
                config,
            ),
            _poa_status_counts(
                cohort,
                CALCULATED_POA_STATUS_COL,
                "calculated_arrival_plus_48h",
                config,
            ),
            _poa_status_counts(
                cohort,
                INPATIENT_POA_STATUS_COL,
                "calculated_inpatient_admission",
                config,
            ),
        ],
        how="vertical",
    )


def category_crosstab_long(
    dataframe: pl.DataFrame,
    calculated_col: str,
    reference: str,
    config: Phase4AnalysisConfig,
) -> pl.DataFrame:
    """Return a complete 6x6 calculated-versus-billed contingency table."""
    calculated_grid = pl.DataFrame(
        {"calculated_category": config.sepsis_categories}
    )
    billed_grid = pl.DataFrame({"billed_category": config.sepsis_categories})
    grid = calculated_grid.join(billed_grid, how="cross")
    counts = (
        dataframe.group_by(calculated_col, BILLED_CATEGORY_COL)
        .len()
        .rename(
            {
                calculated_col: "calculated_category",
                BILLED_CATEGORY_COL: "billed_category",
                "len": "encounter_count",
            }
        )
    )
    return (
        grid.join(
            counts,
            on=["calculated_category", "billed_category"],
            how="left",
        )
        .with_columns(pl.col("encounter_count").fill_null(0).cast(pl.Int64))
        .with_columns(
            pl.col("encounter_count")
            .sum()
            .over("billed_category")
            .alias("billed_category_total"),
            pl.col("encounter_count")
            .sum()
            .over("calculated_category")
            .alias("calculated_category_total"),
            pl.lit(reference).alias("calculated_reference"),
        )
        .with_columns(
            pl.when(pl.col("billed_category_total") > 0)
            .then(pl.col("encounter_count") / pl.col("billed_category_total"))
            .otherwise(pl.lit(0.0))
            .alias("column_proportion"),
            pl.when(pl.col("calculated_category_total") > 0)
            .then(pl.col("encounter_count") / pl.col("calculated_category_total"))
            .otherwise(pl.lit(0.0))
            .alias("row_proportion"),
        )
        .select(
            "calculated_reference",
            "calculated_category",
            "billed_category",
            "encounter_count",
            "calculated_category_total",
            "billed_category_total",
            "row_proportion",
            "column_proportion",
        )
    )


def build_category_crosstabs(
    cohort: pl.DataFrame,
    config: Phase4AnalysisConfig,
) -> pl.DataFrame:
    """Build arrival+48-hour and inpatient-admission contingency tables."""
    return pl.concat(
        [
            category_crosstab_long(
                cohort,
                CALCULATED_CATEGORY_COL,
                "arrival_plus_48h",
                config,
            ),
            category_crosstab_long(
                cohort,
                INPATIENT_CATEGORY_COL,
                "inpatient_admission",
                config,
            ),
        ],
        how="vertical",
    )
