"""Compose final encounter-level sepsis severity, onset, and POA status."""

from datetime import timedelta

import polars as pl

from ...configs.severitysepsis import SeveritySepsisConfig, severitysepsisconfig


def _validate_encounter_grain(
    dataframe: pl.DataFrame,
    *,
    encounter_col: str,
    table_name: str,
) -> None:
    """Require exactly one non-null row per encounter in an input table."""
    if encounter_col not in dataframe.columns:
        raise ValueError(
            f"{table_name} is missing encounter column {encounter_col!r}"
        )
    if dataframe.select(pl.col(encounter_col).is_null().any()).item():
        raise ValueError(f"{table_name} encounter identifiers cannot be null")
    duplicate_count = (
        dataframe.group_by(encounter_col)
        .len()
        .filter(pl.col("len") > 1)
        .height
    )
    if duplicate_count:
        raise ValueError(
            f"{table_name} must have one row per encounter; found "
            f"{duplicate_count} duplicate encounter IDs"
        )


def build_final_sepsis_encounter_summary(
    df_encounters: pl.DataFrame,
    df_sepsis1_encounters: pl.DataFrame,
    df_sepsis2_encounters: pl.DataFrame,
    df_sepsis3_encounters: pl.DataFrame,
    *,
    config: SeveritySepsisConfig = severitysepsisconfig,
) -> pl.DataFrame:
    """Return one analysis-ready categorization row for every encounter.

    Severity is the highest positive Sepsis 1/2/3 flag. Onset is the minimum
    earliest-evidence timestamp across the positive severity groups,
    independent of that maximum severity. The Arrival + 48-hour POA boundary
    is inclusive.
    """
    encounter_col = config.encounter_col
    encounter_columns = [
        encounter_col,
        config.arrival_datetime_col,
        config.inpatient_admission_datetime_col,
        config.length_of_stay_col,
        config.death_flag_col,
        config.billed_sepsis_category_col,
    ]
    missing_encounter_columns = sorted(
        set(encounter_columns).difference(df_encounters.columns)
    )
    if missing_encounter_columns:
        raise ValueError(
            "Encounter input is missing analysis columns: "
            f"{missing_encounter_columns}"
        )

    summaries = [
        (
            "Sepsis 1 encounter summary",
            df_sepsis1_encounters,
            config.sepsis1_flag_col,
            config.sepsis1_earliest_evidence_dt_col,
        ),
        (
            "Sepsis 2 encounter summary",
            df_sepsis2_encounters,
            config.sepsis2_flag_col,
            config.sepsis2_earliest_evidence_dt_col,
        ),
        (
            "Sepsis 3 encounter summary",
            df_sepsis3_encounters,
            config.sepsis3_flag_col,
            config.sepsis3_earliest_evidence_dt_col,
        ),
    ]
    _validate_encounter_grain(
        df_encounters,
        encounter_col=encounter_col,
        table_name="Encounter input",
    )
    encounter_keys = df_encounters.select(encounter_col)

    seen_columns = set(encounter_columns)
    for table_name, summary, flag_col, onset_col in summaries:
        _validate_encounter_grain(
            summary,
            encounter_col=encounter_col,
            table_name=table_name,
        )
        missing_summary_columns = sorted(
            {flag_col, onset_col}.difference(summary.columns)
        )
        if missing_summary_columns:
            raise ValueError(
                f"{table_name} is missing columns: {missing_summary_columns}"
            )
        if (
            summary.height != df_encounters.height
            or not encounter_keys.join(
                summary.select(encounter_col),
                on=encounter_col,
                how="anti",
            ).is_empty()
            or not summary.select(encounter_col).join(
                encounter_keys,
                on=encounter_col,
                how="anti",
            ).is_empty()
        ):
            raise ValueError(
                f"{table_name} must contain the same encounters as "
                "the encounter input"
            )
        invalid_flag_count = summary.filter(
            pl.col(flag_col).is_null() | ~pl.col(flag_col).is_in([0, 1])
        ).height
        if invalid_flag_count:
            raise ValueError(
                f"{table_name} has {invalid_flag_count} invalid {flag_col!r} "
                "values"
            )
        invalid_timestamp_count = summary.filter(
            ((pl.col(flag_col) == 1) & pl.col(onset_col).is_null())
            | ((pl.col(flag_col) == 0) & pl.col(onset_col).is_not_null())
        ).height
        if invalid_timestamp_count:
            raise ValueError(
                f"{table_name} has {invalid_timestamp_count} flag/onset "
                "inconsistencies"
            )
        overlapping_columns = (
            set(summary.columns).difference({encounter_col}) & seen_columns
        )
        if overlapping_columns:
            raise ValueError(
                f"{table_name} overlaps existing output columns: "
                f"{sorted(overlapping_columns)}"
            )
        seen_columns.update(summary.columns)

    result = df_encounters.select(encounter_columns)
    for _, summary, _, _ in summaries:
        result = result.join(
            summary,
            on=encounter_col,
            how="left",
            validate="1:1",
        )

    severity_col = config.calculated_sepsis_severity_col
    first_dt_col = config.first_sepsis_dt_col
    poa_status_col = config.calculated_poa_status_col
    category_col = config.calculated_sepsis_category_col
    result = result.with_columns(
        pl.max_horizontal(
            pl.col(config.sepsis1_flag_col) * pl.lit(1),
            pl.col(config.sepsis2_flag_col) * pl.lit(2),
            pl.col(config.sepsis3_flag_col) * pl.lit(3),
        )
        .cast(pl.Int8)
        .alias(severity_col),
        pl.min_horizontal(
            pl.when(pl.col(config.sepsis1_flag_col) == 1)
            .then(pl.col(config.sepsis1_earliest_evidence_dt_col)),
            pl.when(pl.col(config.sepsis2_flag_col) == 1)
            .then(pl.col(config.sepsis2_earliest_evidence_dt_col)),
            pl.when(pl.col(config.sepsis3_flag_col) == 1)
            .then(pl.col(config.sepsis3_earliest_evidence_dt_col)),
        ).alias(first_dt_col),
    )

    missing_arrival_count = result.filter(
        (pl.col(severity_col) > 0)
        & pl.col(config.arrival_datetime_col).is_null()
    ).height
    if missing_arrival_count:
        raise ValueError(
            f"{missing_arrival_count} sepsis-positive encounters are missing "
            f"{config.arrival_datetime_col!r}"
        )

    result = result.with_columns(
        pl.when(pl.col(severity_col) == 0)
        .then(pl.lit(None, dtype=pl.String))
        .when(
            pl.col(first_dt_col)
            <= pl.col(config.arrival_datetime_col)
            + pl.lit(timedelta(hours=config.poa_arrival_hours))
        )
        .then(pl.lit("POA"))
        .otherwise(pl.lit("NPOA"))
        .alias(poa_status_col)
    ).with_columns(
        pl.when(pl.col(severity_col) == 0)
        .then(pl.lit(config.no_sepsis_category))
        .otherwise(
            pl.concat_str(
                poa_status_col,
                pl.col(severity_col).cast(pl.String),
                separator="-",
            )
        )
        .alias(category_col)
    ).with_columns(
        pl.when(pl.col(config.billed_sepsis_category_col).is_null())
        .then(pl.lit(None, dtype=pl.Boolean))
        .otherwise(
            pl.col(category_col) == pl.col(config.billed_sepsis_category_col)
        )
        .alias(config.sepsis_category_match_col)
    )
    return result.sort(encounter_col)
