"""Mortality, time-to-sepsis, and length-of-stay aggregate tables."""

import polars as pl

from .config import (
    ARRIVAL_TO_SEPSIS_HOURS_COL,
    BILLED_CATEGORY_COL,
    BILLED_SEVERITY_COL,
    CALCULATED_CATEGORY_COL,
    CALCULATED_SEVERITY_COL,
    DEATH_COL,
    LOS_COL,
    Phase4AnalysisConfig,
)


def summarize_numeric(
    dataframe: pl.DataFrame,
    value_col: str,
    group_cols: list[str],
) -> pl.DataFrame:
    """Return statistics needed to reconstruct the legacy distribution plots."""
    return (
        dataframe.filter(pl.col(value_col).is_not_null())
        .group_by(group_cols)
        .agg(
            pl.len().cast(pl.Int64).alias("encounter_count"),
            pl.col(value_col).min().cast(pl.Float64).alias("minimum"),
            pl.col(value_col)
            .quantile(0.25, interpolation="linear")
            .cast(pl.Float64)
            .alias("q1"),
            pl.col(value_col).median().cast(pl.Float64).alias("median"),
            pl.col(value_col)
            .quantile(0.75, interpolation="linear")
            .cast(pl.Float64)
            .alias("q3"),
            pl.col(value_col).max().cast(pl.Float64).alias("maximum"),
            pl.col(value_col).mean().cast(pl.Float64).alias("mean"),
        )
        .sort(group_cols)
    )


def build_mortality_by_category(
    cohort: pl.DataFrame,
    config: Phase4AnalysisConfig,
) -> pl.DataFrame:
    """Calculate mortality counts and rates by billed/calculated category."""
    outputs = []
    for category_col, source in [
        (BILLED_CATEGORY_COL, "billed"),
        (CALCULATED_CATEGORY_COL, "calculated_arrival_plus_48h"),
    ]:
        rates = (
            cohort.group_by(category_col)
            .agg(
                pl.len().cast(pl.Int64).alias("encounter_count"),
                (pl.col(DEATH_COL) == 1)
                .sum()
                .cast(pl.Int64)
                .alias("death_count"),
            )
            .rename({category_col: "category"})
        )
        outputs.append(
            pl.DataFrame({"category": config.sepsis_categories})
            .join(rates, on="category", how="left")
            .with_columns(
                pl.col("encounter_count").fill_null(0).cast(pl.Int64),
                pl.col("death_count").fill_null(0).cast(pl.Int64),
                pl.lit(source).alias("category_source"),
            )
            .with_columns(
                pl.when(pl.col("encounter_count") > 0)
                .then(pl.col("death_count") / pl.col("encounter_count"))
                .otherwise(pl.lit(0.0))
                .alias("mortality_rate")
            )
            .select(
                "category_source",
                "category",
                "death_count",
                "encounter_count",
                "mortality_rate",
            )
        )
    return pl.concat(outputs, how="vertical")


def build_arrival_to_sepsis_summary(
    cohort: pl.DataFrame,
    config: Phase4AnalysisConfig,
) -> pl.DataFrame:
    """Summarize positive, below-cutoff arrival-to-sepsis times."""
    upper_cutoff = cohort[ARRIVAL_TO_SEPSIS_HOURS_COL].quantile(
        config.distribution_upper_quantile,
        interpolation="linear",
    )
    time_filter = pl.col(ARRIVAL_TO_SEPSIS_HOURS_COL) < upper_cutoff
    if config.arrival_to_sepsis_positive_hours_only:
        time_filter &= pl.col(ARRIVAL_TO_SEPSIS_HOURS_COL) > 0
    filtered = cohort.filter(time_filter)
    summaries = []
    for category_col, source in [
        (BILLED_CATEGORY_COL, "billed"),
        (CALCULATED_CATEGORY_COL, "calculated_arrival_plus_48h"),
    ]:
        summaries.append(
            summarize_numeric(
                filtered.rename({category_col: "category"}),
                ARRIVAL_TO_SEPSIS_HOURS_COL,
                ["category"],
            ).with_columns(
                pl.lit(source).alias("category_source"),
                pl.lit(upper_cutoff).alias("global_99th_percentile_hours"),
            )
        )
    return pl.concat(summaries, how="vertical").select(
        "category_source",
        "category",
        "global_99th_percentile_hours",
        "encounter_count",
        "minimum",
        "q1",
        "median",
        "q3",
        "maximum",
        "mean",
    )


def _length_of_stay_filtered(
    cohort: pl.DataFrame,
    config: Phase4AnalysisConfig,
) -> tuple[pl.DataFrame, float]:
    upper_cutoff = float(
        cohort[LOS_COL].quantile(
            config.distribution_upper_quantile,
            interpolation="linear",
        )
    )
    return cohort.filter(pl.col(LOS_COL) < upper_cutoff), upper_cutoff


def build_length_of_stay_by_category(
    cohort: pl.DataFrame,
    config: Phase4AnalysisConfig,
) -> pl.DataFrame:
    """Summarize LOS by billed and Arrival+48 calculated categories."""
    filtered, upper_cutoff = _length_of_stay_filtered(cohort, config)
    summaries = []
    for category_col, source in [
        (BILLED_CATEGORY_COL, "billed"),
        (CALCULATED_CATEGORY_COL, "calculated_arrival_plus_48h"),
    ]:
        summaries.append(
            summarize_numeric(
                filtered.rename({category_col: "category"}),
                LOS_COL,
                ["category"],
            ).with_columns(
                pl.lit(source).alias("category_source"),
                pl.lit(upper_cutoff).alias("global_99th_percentile_days"),
            )
        )
    return pl.concat(summaries, how="vertical").select(
        "category_source",
        "category",
        "global_99th_percentile_days",
        "encounter_count",
        "minimum",
        "q1",
        "median",
        "q3",
        "maximum",
        "mean",
    )


def _agreement_rows(
    cohort: pl.DataFrame,
    value_col: str,
    category_targets: list[str],
) -> pl.DataFrame:
    """Build temporary rows for active agreement/disagreement comparisons."""
    comparisons = [
        (
            "severity",
            str(severity),
            pl.col(CALCULATED_SEVERITY_COL) == severity,
            pl.col(BILLED_SEVERITY_COL) == severity,
        )
        for severity in [1, 2, 3]
    ]
    comparisons.extend(
        [
            (
                "category",
                category,
                pl.col(CALCULATED_CATEGORY_COL) == category,
                pl.col(BILLED_CATEGORY_COL) == category,
            )
            for category in category_targets
        ]
    )

    frames = []
    for comparison, target, calculated_match, billed_match in comparisons:
        for group, condition in [
            ("billing_only", billed_match & ~calculated_match),
            ("calculated_only", calculated_match & ~billed_match),
            ("billing_and_calculated", billed_match & calculated_match),
        ]:
            frames.append(
                cohort.filter(condition)
                .select(value_col)
                .with_columns(
                    pl.lit(comparison).alias("comparison"),
                    pl.lit(target).alias("target"),
                    pl.lit(group).alias("agreement_group"),
                )
            )
    return pl.concat(frames, how="vertical")


def build_length_of_stay_agreement(
    cohort: pl.DataFrame,
    config: Phase4AnalysisConfig,
) -> pl.DataFrame:
    """Summarize LOS for each active legacy concordance comparison."""
    filtered, upper_cutoff = _length_of_stay_filtered(cohort, config)
    rows = _agreement_rows(
        filtered,
        LOS_COL,
        category_targets=["POA-3", "NPOA-3"],
    )
    return summarize_numeric(
        rows,
        LOS_COL,
        ["comparison", "target", "agreement_group"],
    ).with_columns(
        pl.lit(upper_cutoff).alias("global_99th_percentile_days"),
    )


def build_mortality_agreement(
    cohort: pl.DataFrame,
) -> pl.DataFrame:
    """Aggregate Death_Flag within each legacy concordance comparison."""
    rows = _agreement_rows(
        cohort,
        DEATH_COL,
        category_targets=["POA-3", "POA-2", "NPOA-3"],
    )
    return (
        rows.group_by("comparison", "target", "agreement_group", DEATH_COL)
        .len()
        .rename({"len": "encounter_count", DEATH_COL: "death_flag"})
        .with_columns(
            pl.col("encounter_count")
            .sum()
            .over("comparison", "target", "agreement_group")
            .alias("group_total")
        )
        .with_columns(
            (pl.col("encounter_count") / pl.col("group_total")).alias(
                "proportion"
            )
        )
        .sort("comparison", "target", "agreement_group", "death_flag")
    )
