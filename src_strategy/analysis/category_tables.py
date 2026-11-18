"""Category counts, POA counts, and calculated-versus-billed crosstabs."""

import polars as pl

from .config import (
    BILLED_CATEGORY_COL,
    BILLED_POA_STATUS_COL,
    BILLED_SEVERITY_COL,
    CALCULATED_CATEGORY_COL,
    CALCULATED_POA_STATUS_COL,
    CALCULATED_SEVERITY_COL,
    ENCOUNTER_COL,
    INPATIENT_CATEGORY_COL,
    INPATIENT_POA_STATUS_COL,
    ICU_COL,
    ORGAN_DYSFUNCTION_PATHWAY_VALUE,
    SEPSIS3_ASSOCIATION_FILENAME,
    SEPSIS3_PATHWAY_COL,
    VASOPRESSORS_PATHWAY_VALUE,
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


def build_icu_by_category_crosstab(
    cohort: pl.DataFrame,
    config: Phase4AnalysisConfig,
) -> pl.DataFrame:
    """Count ICU encounters by Arrival + 48-hour and billed category."""
    icu_encounters = cohort.filter(pl.col(ICU_COL) == 1)
    return category_crosstab_long(
        icu_encounters,
        CALCULATED_CATEGORY_COL,
        "arrival_plus_48h",
        config,
    )


def build_icu_by_severity_crosstab(cohort: pl.DataFrame) -> pl.DataFrame:
    """Count ICU encounters for every computed/billed severity pairing."""
    severities = [1, 2, 3]
    grid = pl.DataFrame(
        {"calculated_severity": severities},
        schema={"calculated_severity": pl.Int8},
    ).join(
        pl.DataFrame(
            {"billed_severity": severities},
            schema={"billed_severity": pl.Int8},
        ),
        how="cross",
    )
    counts = (
        cohort.filter(pl.col(ICU_COL) == 1)
        .group_by(CALCULATED_SEVERITY_COL, BILLED_SEVERITY_COL)
        .len()
        .rename(
            {
                CALCULATED_SEVERITY_COL: "calculated_severity",
                BILLED_SEVERITY_COL: "billed_severity",
                "len": "icu_encounter_count",
            }
        )
    )
    return (
        grid.join(
            counts,
            on=["calculated_severity", "billed_severity"],
            how="left",
        )
        .with_columns(
            pl.col("icu_encounter_count").fill_null(0).cast(pl.Int64)
        )
        .with_columns(
            pl.col("icu_encounter_count")
            .sum()
            .over("calculated_severity")
            .alias("calculated_severity_total"),
            pl.col("icu_encounter_count")
            .sum()
            .over("billed_severity")
            .alias("billed_severity_total"),
        )
        .sort("calculated_severity", "billed_severity")
    )


def _icu_status_counts(
    cohort: pl.DataFrame,
    *,
    classification_col: str,
    classification_source: str,
    classifications: list[str],
) -> pl.DataFrame:
    """Return complete ICU 0/1 counts for one classification source."""
    classification_grid = pl.DataFrame(
        {
            "classification": classifications,
            "classification_order": range(len(classifications)),
        }
    )
    status_grid = pl.DataFrame(
        {"icu_status": [0, 1]},
        schema={"icu_status": pl.Int64},
    )
    counts = (
        cohort.filter(pl.col(ICU_COL).is_in([0, 1]))
        .with_columns(
            pl.col(classification_col).cast(pl.String).alias("classification")
        )
        .group_by("classification", ICU_COL)
        .len()
        .rename({ICU_COL: "icu_status", "len": "encounter_count"})
    )
    return (
        classification_grid.join(status_grid, how="cross")
        .join(counts, on=["classification", "icu_status"], how="left")
        .with_columns(
            pl.col("encounter_count").fill_null(0).cast(pl.Int64),
            pl.lit(classification_source).alias("classification_source"),
        )
        .sort("classification_order", "icu_status")
        .select(
            "classification_source",
            "classification",
            "icu_status",
            "encounter_count",
        )
    )


def build_icu_status_counts(
    cohort: pl.DataFrame,
    config: Phase4AnalysisConfig,
) -> pl.DataFrame:
    """Build ICU 0/1 counts for computed and billed categories/severities."""
    severity_order = ["1", "2", "3"]
    category_order = list(config.sepsis_categories)
    return pl.concat(
        [
            _icu_status_counts(
                cohort,
                classification_col=CALCULATED_SEVERITY_COL,
                classification_source="computed_severity",
                classifications=severity_order,
            ),
            _icu_status_counts(
                cohort,
                classification_col=BILLED_SEVERITY_COL,
                classification_source="billed_severity",
                classifications=severity_order,
            ),
            _icu_status_counts(
                cohort,
                classification_col=CALCULATED_CATEGORY_COL,
                classification_source="computed_category",
                classifications=category_order,
            ),
            _icu_status_counts(
                cohort,
                classification_col=BILLED_CATEGORY_COL,
                classification_source="billed_category",
                classifications=category_order,
            ),
        ],
        how="vertical",
    )


def build_icu_sepsis3_pathway_counts(
    cohort: pl.DataFrame,
    sepsis3_associations: pl.DataFrame,
) -> pl.DataFrame:
    """Count ICU status within Sepsis 3 by mutually exclusive pathway group."""
    required = {ENCOUNTER_COL, SEPSIS3_PATHWAY_COL}
    missing = sorted(required.difference(sepsis3_associations.columns))
    if missing:
        raise ValueError(
            f"{SEPSIS3_ASSOCIATION_FILENAME} is missing columns: {missing}"
        )
    invalid_pathways = sorted(
        set(sepsis3_associations[SEPSIS3_PATHWAY_COL].drop_nulls().unique())
        - {
            ORGAN_DYSFUNCTION_PATHWAY_VALUE,
            VASOPRESSORS_PATHWAY_VALUE,
        }
    )
    if invalid_pathways:
        raise ValueError(f"Unexpected Sepsis 3 pathways: {invalid_pathways}")

    pathway_flags = sepsis3_associations.group_by(ENCOUNTER_COL).agg(
        (pl.col(SEPSIS3_PATHWAY_COL) == ORGAN_DYSFUNCTION_PATHWAY_VALUE)
        .any()
        .alias("organ_dysfunction_pathway_met"),
        (pl.col(SEPSIS3_PATHWAY_COL) == VASOPRESSORS_PATHWAY_VALUE)
        .any()
        .alias("vasopressors_pathway_met"),
    )
    classified = (
        cohort.join(pathway_flags, on=ENCOUNTER_COL, how="left", validate="1:1")
        .with_columns(
            pl.col(
                "organ_dysfunction_pathway_met",
                "vasopressors_pathway_met",
            ).fill_null(False)
        )
        .with_columns(
            pl.when(
                pl.col("organ_dysfunction_pathway_met")
                & pl.col("vasopressors_pathway_met")
            )
            .then(pl.lit("both"))
            .when(pl.col("organ_dysfunction_pathway_met"))
            .then(pl.lit("organ_dysfunction"))
            .when(pl.col("vasopressors_pathway_met"))
            .then(pl.lit("vasopressors"))
            .otherwise(pl.lit("neither"))
            .alias("pathway_group")
        )
    )

    source_rows = pl.concat(
        [
            classified.filter(
                pl.col(CALCULATED_SEVERITY_COL) == 3
            ).with_columns(
                pl.lit("computed_sepsis3").alias("classification_source")
            ),
            classified.filter(pl.col(BILLED_SEVERITY_COL) == 3).with_columns(
                pl.lit("billed_sepsis3").alias("classification_source")
            ),
        ],
        how="vertical",
    ).filter(pl.col(ICU_COL).is_in([0, 1]))

    pathway_groups = [
        "organ_dysfunction",
        "vasopressors",
        "both",
        "neither",
    ]
    grid = (
        pl.DataFrame(
            {"classification_source": ["computed_sepsis3", "billed_sepsis3"]}
        )
        .join(pl.DataFrame({"pathway_group": pathway_groups}), how="cross")
        .join(
            pl.DataFrame(
                {"icu_status": [0, 1]},
                schema={"icu_status": pl.Int64},
            ),
            how="cross",
        )
    )
    counts = (
        source_rows.group_by("classification_source", "pathway_group", ICU_COL)
        .len()
        .rename({ICU_COL: "icu_status", "len": "encounter_count"})
    )
    return (
        grid.join(
            counts,
            on=["classification_source", "pathway_group", "icu_status"],
            how="left",
        )
        .with_columns(pl.col("encounter_count").fill_null(0).cast(pl.Int64))
        .with_columns(
            pl.col("encounter_count")
            .sum()
            .over("classification_source")
            .alias("denominator")
        )
        .with_columns(
            pl.when(pl.col("denominator") > 0)
            .then(pl.col("encounter_count") / pl.col("denominator"))
            .otherwise(pl.lit(0.0))
            .alias("proportion")
        )
        .with_columns(
            pl.col("classification_source")
            .replace_strict(
                {"computed_sepsis3": 0, "billed_sepsis3": 1},
                return_dtype=pl.Int8,
            )
            .alias("source_order"),
            pl.col("pathway_group")
            .replace_strict(
                {group: index for index, group in enumerate(pathway_groups)},
                return_dtype=pl.Int8,
            )
            .alias("pathway_order"),
        )
        .sort("source_order", "pathway_order", "icu_status")
        .select(
            "classification_source",
            "pathway_group",
            "icu_status",
            "encounter_count",
            "denominator",
            "proportion",
        )
    )
