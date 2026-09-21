"""Patient-neutral validation gates required before publishing a run."""

from collections.abc import Mapping, Sequence
from pathlib import Path

import polars as pl

from .configs.severitysepsis import SeveritySepsisConfig, severitysepsisconfig
# from .events.sepsis import select_first_organ_episodes_by_type
from .run_manifest import ValidationResult


class RunValidationError(RuntimeError):
    """A publish-blocking invariant failed without exposing row-level data."""


def _passed_or_raise(name: str, condition: bool) -> ValidationResult:
    if not condition:
        raise RunValidationError(f"Clinical run validation failed: {name}")
    return ValidationResult(name=name, passed=True)


def validate_written_output_tables(
    run_directory: str | Path,
    output_tables: Mapping[str, pl.DataFrame],
) -> ValidationResult:
    """Require every registered parquet to be readable with matching rows."""
    directory = Path(run_directory)
    valid = True
    for filename, dataframe in output_tables.items():
        artifact = directory / filename
        if not artifact.is_file():
            valid = False
            break
        try:
            written_rows = (
                pl.scan_parquet(artifact)
                .select(pl.len().alias("row_count"))
                .collect()
                .item()
            )
        except Exception:
            valid = False
            break
        if written_rows != dataframe.height:
            valid = False
            break
    return _passed_or_raise(
        "all_output_tables_readable_with_matching_row_counts",
        valid,
    )


def validate_encounter_summary(
    encounters: pl.DataFrame,
    summary: pl.DataFrame,
    *,
    encounter_col: str,
    validation_name: str,
) -> ValidationResult:
    """Require exactly one summary row for every input encounter."""
    if encounter_col not in encounters.columns or encounter_col not in summary.columns:
        return _passed_or_raise(validation_name, False)
    valid = (
        not encounters.select(pl.col(encounter_col).is_null().any()).item()
        and not summary.select(pl.col(encounter_col).is_null().any()).item()
        and encounters[encounter_col].n_unique() == encounters.height
        and summary[encounter_col].n_unique() == summary.height
        and summary.height == encounters.height
        and encounters.join(summary, on=encounter_col, how="anti").is_empty()
        and summary.join(encounters, on=encounter_col, how="anti").is_empty()
    )
    return _passed_or_raise(validation_name, valid)


def validate_binary_flag(
    dataframe: pl.DataFrame,
    *,
    flag_col: str,
    validation_name: str,
) -> ValidationResult:
    """Require a non-null flag containing only zero or one."""
    valid = flag_col in dataframe.columns
    if valid:
        valid = dataframe.filter(
            pl.col(flag_col).is_null() | ~pl.col(flag_col).is_in([0, 1])
        ).is_empty()
    return _passed_or_raise(validation_name, valid)


def validate_positive_flags_have_timestamps(
    dataframe: pl.DataFrame,
    *,
    flag_col: str,
    timestamp_col: str,
    validation_name: str,
) -> ValidationResult:
    """Require every positive classification to retain its onset timestamp."""
    valid = {flag_col, timestamp_col}.issubset(dataframe.columns)
    if valid:
        valid = dataframe.filter(
            (pl.col(flag_col) == 1) & pl.col(timestamp_col).is_null()
        ).is_empty()
    return _passed_or_raise(validation_name, valid)


def validate_sepsis3_is_subset_of_sepsis2(
    sepsis2_summary: pl.DataFrame,
    sepsis3_summary: pl.DataFrame,
    *,
    config: SeveritySepsisConfig = severitysepsisconfig,
) -> ValidationResult:
    """Require every Sepsis 3-positive encounter to be Sepsis 2-positive."""
    required2 = {config.encounter_col, config.sepsis2_flag_col}
    required3 = {config.encounter_col, config.sepsis3_flag_col}
    valid = required2.issubset(sepsis2_summary.columns) and required3.issubset(
        sepsis3_summary.columns
    )
    if valid:
        joined = sepsis3_summary.select(*required3).join(
            sepsis2_summary.select(*required2),
            on=config.encounter_col,
            how="left",
            validate="1:1",
        )
        valid = joined.filter(
            (pl.col(config.sepsis3_flag_col) == 1)
            & (pl.col(config.sepsis2_flag_col) != 1)
        ).is_empty()
    return _passed_or_raise("sepsis3_positive_is_subset_of_sepsis2", valid)


def validate_unique_association_grain(
    associations: pl.DataFrame,
    *,
    key_columns: Sequence[str],
    validation_name: str,
) -> ValidationResult:
    """Require one evidence association per documented composite key."""
    valid = set(key_columns).issubset(associations.columns)
    if valid:
        valid = (
            associations.select(key_columns).n_unique()
            == associations.height
        )
    return _passed_or_raise(validation_name, valid)


def validate_sepsis2_uses_selected_first_organ_episodes(
    sepsis2_associations: pl.DataFrame,
    organ_episodes: pl.DataFrame,
    *,
    config: SeveritySepsisConfig = severitysepsisconfig,
) -> ValidationResult:
    """Require Sepsis 2 evidence to reference only first-per-type episodes."""
    keys = [config.encounter_col, config.organ_episode_id_col]
    valid = set(keys).issubset(sepsis2_associations.columns)
    if valid:
        selected = select_first_organ_episodes_by_type(
            organ_episodes,
            config=config,
        ).select(keys)
        used = sepsis2_associations.select(keys).unique()
        valid = used.join(selected, on=keys, how="anti").is_empty()
    return _passed_or_raise(
        "sepsis2_uses_only_selected_first_per_organ_episodes",
        valid,
    )
