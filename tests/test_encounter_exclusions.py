from datetime import date

import polars as pl
import pytest
from pydantic import ValidationError

from src_strategy.configs.dataconfig import BloodPressureConfig, DataConfig
from src_strategy.configs.encounter_exclusions import (
    EncounterExclusionConfig,
    EncounterExclusionRule,
    encounter_exclusion_config,
)
from src_strategy.data_ingest.dataloader_2 import DataLoader
from src_strategy.data_ingest.encounter_exclusions import (
    apply_encounter_exclusions,
)


def _encounters() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "EncounterEpicCsn": [1, 2, 3, 4, 5],
            "DischargeDateValue": [
                date(2026, 9, 30),
                date(2026, 10, 1),
                None,
                date(2026, 10, 2),
                None,
            ],
            "Cancer_Registry_YN": [0, 0, 1, 1, None],
        },
        schema_overrides={
            "EncounterEpicCsn": pl.Int64,
            "Cancer_Registry_YN": pl.Int64,
        },
    )


def test_default_rules_retain_cutoff_and_null_values_and_audit_all_reasons() -> None:
    eligible, audit = apply_encounter_exclusions(
        _encounters(),
        encounter_exclusion_config,
        encounter_col="EncounterEpicCsn",
    )

    assert eligible["EncounterEpicCsn"].to_list() == [1, 5]
    assert audit.height == 4
    assert (
        audit.group_by("exclusion_rule")
        .len()
        .sort("exclusion_rule")
        .rows()
        == [
            ("cancer_registry_positive", 2),
            ("discharge_after_2026_09_30", 2),
        ]
    )
    assert audit.filter(pl.col("EncounterEpicCsn") == 4)[
        "exclusion_rule"
    ].to_list() == [
        "cancer_registry_positive",
        "discharge_after_2026_09_30",
    ]
    assert set(audit.columns) == {
        "EncounterEpicCsn",
        "exclusion_rule",
        "source_column",
        "operator",
        "configured_value",
        "observed_value",
    }


def test_missing_configured_column_fails_clearly() -> None:
    with pytest.raises(ValueError, match="missing columns.*Cancer_Registry_YN"):
        apply_encounter_exclusions(
            _encounters().drop("Cancer_Registry_YN"),
            encounter_exclusion_config,
            encounter_col="EncounterEpicCsn",
        )


def test_excluding_every_encounter_fails() -> None:
    encounters = pl.DataFrame(
        {
            "EncounterEpicCsn": [1],
            "Cancer_Registry_YN": [1],
        },
        schema_overrides={"EncounterEpicCsn": pl.Int64},
    )
    config = EncounterExclusionConfig(
        rules=(
            EncounterExclusionRule(
                name="cancer",
                column="Cancer_Registry_YN",
                operator="eq",
                value=1,
            ),
        )
    )

    with pytest.raises(ValueError, match="removed every encounter"):
        apply_encounter_exclusions(
            encounters,
            config,
            encounter_col="EncounterEpicCsn",
        )


def test_disabled_config_preserves_encounters_and_returns_typed_empty_audit() -> None:
    encounters = pl.DataFrame(
        {"EncounterEpicCsn": [1, 2]},
        schema_overrides={"EncounterEpicCsn": pl.Int64},
    )
    eligible, audit = apply_encounter_exclusions(
        encounters,
        EncounterExclusionConfig(enabled=False),
        encounter_col="EncounterEpicCsn",
    )

    assert eligible.equals(encounters)
    assert audit.is_empty()
    assert audit.schema["EncounterEpicCsn"] == pl.Int64


def test_active_rules_with_no_matches_return_typed_empty_audit() -> None:
    encounters = _encounters().filter(pl.col("EncounterEpicCsn").is_in([1, 5]))

    eligible, audit = apply_encounter_exclusions(
        encounters,
        encounter_exclusion_config,
        encounter_col="EncounterEpicCsn",
    )

    assert eligible.equals(encounters)
    assert audit.is_empty()
    assert audit.schema["EncounterEpicCsn"] == pl.Int64


def test_rule_configuration_rejects_incompatible_operator_value_shape() -> None:
    with pytest.raises(ValidationError, match="requires a tuple value"):
        EncounterExclusionRule(
            name="invalid",
            column="Cancer_Registry_YN",
            operator="in",
            value=1,
        )


def test_loader_filters_every_transactional_source_to_eligible_ids() -> None:
    loader = DataLoader(
        input_output_dataconfig=None,
        data_config=DataConfig(),
        bp_config=BloodPressureConfig(),
        encounter_exclusion_config=encounter_exclusion_config,
    )
    transactional = pl.DataFrame(
        {"EncounterEpicCsn": [1, 2, 3, 4, 5, 5]},
        schema_overrides={"EncounterEpicCsn": pl.Int64},
    )
    sources = {
        name: transactional for name in loader.TRANSACTIONAL_SOURCES
    }
    sources["encounters"] = _encounters()

    filtered, audit = loader._apply_encounter_exclusions(sources)

    assert filtered["encounters"]["EncounterEpicCsn"].to_list() == [1, 5]
    assert audit.height == 4
    for name in loader.TRANSACTIONAL_SOURCES:
        assert filtered[name]["EncounterEpicCsn"].to_list() == [1, 5, 5]
