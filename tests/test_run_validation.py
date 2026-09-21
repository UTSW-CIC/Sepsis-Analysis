from datetime import datetime, timedelta

import polars as pl
import pytest

from src_strategy.configs.severitysepsis import SeveritySepsisConfig
from src_strategy.run_validation import (
    RunValidationError,
    validate_binary_flag,
    validate_encounter_summary,
    validate_positive_flags_have_timestamps,
    validate_sepsis2_uses_selected_first_organ_episodes,
    validate_sepsis3_is_subset_of_sepsis2,
    validate_unique_association_grain,
    validate_written_output_tables,
)


START = datetime(2026, 1, 1)


def test_written_outputs_must_exist_and_match_in_memory_rows(tmp_path) -> None:
    dataframe = pl.DataFrame({"encounter": [1, 2]})
    dataframe.write_parquet(tmp_path / "output.parquet")

    result = validate_written_output_tables(
        tmp_path,
        {"output.parquet": dataframe},
    )

    assert result.passed is True

    with pytest.raises(RunValidationError, match="matching_row_counts"):
        validate_written_output_tables(
            tmp_path,
            {"output.parquet": dataframe.head(1)},
        )


def test_encounter_summary_requires_the_exact_input_encounter_set() -> None:
    encounters = pl.DataFrame({"EncounterEpicCsn": [1, 2]})
    summary = pl.DataFrame({"EncounterEpicCsn": [1, 2], "flag": [1, 0]})

    result = validate_encounter_summary(
        encounters,
        summary,
        encounter_col="EncounterEpicCsn",
        validation_name="sepsis1_one_row_per_encounter",
    )

    assert result.passed is True

    invalid = pl.DataFrame({"EncounterEpicCsn": [1, 999], "flag": [1, 0]})
    with pytest.raises(RunValidationError) as error:
        validate_encounter_summary(
            encounters,
            invalid,
            encounter_col="EncounterEpicCsn",
            validation_name="sepsis1_one_row_per_encounter",
        )
    assert "999" not in str(error.value)


def test_binary_flags_and_positive_timestamps_are_required() -> None:
    valid = pl.DataFrame(
        {
            "flag": [1, 0],
            "onset": [START, None],
        },
        schema_overrides={"flag": pl.Int8, "onset": pl.Datetime},
    )

    assert validate_binary_flag(
        valid,
        flag_col="flag",
        validation_name="binary_flag",
    ).passed
    assert validate_positive_flags_have_timestamps(
        valid,
        flag_col="flag",
        timestamp_col="onset",
        validation_name="positive_timestamp",
    ).passed

    with pytest.raises(RunValidationError, match="binary_flag"):
        validate_binary_flag(
            valid.with_columns(pl.Series("flag", [2, 0])),
            flag_col="flag",
            validation_name="binary_flag",
        )
    with pytest.raises(RunValidationError, match="positive_timestamp"):
        validate_positive_flags_have_timestamps(
            valid.with_columns(pl.lit(None).alias("onset")),
            flag_col="flag",
            timestamp_col="onset",
            validation_name="positive_timestamp",
        )


def test_sepsis3_positive_must_be_sepsis2_positive() -> None:
    config = SeveritySepsisConfig()
    sepsis2 = pl.DataFrame(
        {"EncounterEpicCsn": [1, 2], config.sepsis2_flag_col: [1, 0]}
    )
    sepsis3 = pl.DataFrame(
        {"EncounterEpicCsn": [1, 2], config.sepsis3_flag_col: [1, 0]}
    )

    assert validate_sepsis3_is_subset_of_sepsis2(
        sepsis2,
        sepsis3,
        config=config,
    ).passed

    with pytest.raises(RunValidationError, match="subset"):
        validate_sepsis3_is_subset_of_sepsis2(
            sepsis2,
            sepsis3.with_columns(pl.Series(config.sepsis3_flag_col, [1, 1])),
            config=config,
        )


def test_association_grain_must_be_unique() -> None:
    associations = pl.DataFrame(
        {
            "EncounterEpicCsn": [1, 1],
            "infection_anchor_id": [1, 2],
            "organ_episode_id": [1, 1],
        }
    )
    keys = ["EncounterEpicCsn", "infection_anchor_id", "organ_episode_id"]

    assert validate_unique_association_grain(
        associations,
        key_columns=keys,
        validation_name="sepsis2_association_grain",
    ).passed

    with pytest.raises(RunValidationError, match="association_grain"):
        validate_unique_association_grain(
            pl.concat([associations, associations.head(1)]),
            key_columns=keys,
            validation_name="sepsis2_association_grain",
        )


def _organ_episodes() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "EncounterEpicCsn": [1, 1],
            "organ_episode_id": [1, 2],
            "organ_episode_state": [1, 1],
            "organ_episode_start": [START, START + timedelta(hours=2)],
            "organ_episode_end": [
                START + timedelta(hours=1),
                START + timedelta(hours=3),
            ],
            "cardiovascular_failure_flag": [0, 0],
            "pulmonary_failure_flag": [0, 0],
            "renal_failure_flag": [1, 1],
            "hepatic_failure_flag": [0, 0],
            "coagulation_failure_flag": [0, 0],
            "neurological_failure_flag": [0, 0],
        },
        schema_overrides={"organ_episode_state": pl.Int8},
    )


def test_sepsis2_may_reference_only_selected_first_organ_episodes() -> None:
    config = SeveritySepsisConfig()
    valid = pl.DataFrame(
        {"EncounterEpicCsn": [1], "organ_episode_id": [1]}
    )

    assert validate_sepsis2_uses_selected_first_organ_episodes(
        valid,
        _organ_episodes(),
        config=config,
    ).passed

    invalid = pl.DataFrame(
        {"EncounterEpicCsn": [1], "organ_episode_id": [2]}
    )
    with pytest.raises(RunValidationError, match="first_per_organ"):
        validate_sepsis2_uses_selected_first_organ_episodes(
            invalid,
            _organ_episodes(),
            config=config,
        )
