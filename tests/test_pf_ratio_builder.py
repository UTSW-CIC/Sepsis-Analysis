from datetime import datetime, timedelta

import polars as pl
import pytest

from src_strategy.configs.collision import (
    ResolutionStrategy,
    collision_config,
)
from src_strategy.configs.pulmonarydysfunction import PFConfig
from src_strategy.data_preparation import PFRatioBuilder
from src_strategy.data_preparation.resolvecollision import ResolveCollision


START = datetime(2026, 1, 1, 12)


def _events(
    rows: list[tuple[int, float, str, float | None]],
) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "EncounterEpicCsn": [row[0] for row in rows],
            "Event_DateTime": [
                START + timedelta(hours=row[1]) for row in rows
            ],
            "Event_Grouper": [row[2] for row in rows],
            "NumericValue": [row[3] for row in rows],
            "audit_marker": list(range(len(rows))),
        },
        schema_overrides={"NumericValue": pl.Float64},
    )


def test_pf_source_collision_strategies_are_conservative() -> None:
    pao2 = collision_config.features_resolutions_dict["PAO2"]
    fio2 = collision_config.features_resolutions_dict["FIO2"]

    assert pao2.strategy == ResolutionStrategy.MIN
    assert fio2.strategy == ResolutionStrategy.MAX
    assert pao2.val_col == fio2.val_col == "NumericValue"


def test_collision_resolution_precedes_pf_ratio_construction() -> None:
    source = pl.DataFrame(
        {
            "EncounterEpicCsn": [1] * 4,
            "Event_DateTime": [START] * 4,
            "Type": ["Lab Results"] * 4,
            "Event_Grouper": ["PAO2", "PAO2", "FIO2", "FIO2"],
            "Event_Name": ["pa1", "pa2", "fi1", "fi2"],
            "Value": ["80", "90", "40", "50"],
            "NumericValue": [80.0, 90.0, 40.0, 50.0],
            "sys": [None] * 4,
            "map": [None] * 4,
        },
        schema_overrides={"sys": pl.Float64, "map": pl.Float64},
    )

    resolved = ResolveCollision(collision_config).resolve(source)
    result = PFRatioBuilder().build(resolved)

    assert resolved.select("Event_Grouper", "NumericValue").sort(
        "Event_Grouper"
    ).rows() == [("FIO2", 50.0), ("PAO2", 80.0)]
    assert result["pf_ratio"].to_list() == [160.0]


def test_builder_selects_nearest_fio2_and_prefers_earlier_tie() -> None:
    source = _events(
        [
            (1, 2, "PAO2", 80.0),
            (1, 1, "FIO2", 40.0),
            (1, 3, "FIO2", 50.0),
        ]
    )

    result = PFRatioBuilder().build(source)

    assert result.height == 1
    assert result["pf_fio2_value"].to_list() == [40.0]
    assert result["pf_ratio"].to_list() == [200.0]
    assert result["pf_ratio_time"].to_list() == [START + timedelta(hours=2)]
    assert result["pf_pair_status"].to_list() == ["paired"]


def test_builder_uses_later_time_when_nearest_fio2_is_future() -> None:
    source = _events(
        [
            (1, 2, "PAO2", 80.0),
            (1, 3, "FIO2", 50.0),
        ]
    )

    result = PFRatioBuilder().build(source)

    assert result["pf_ratio"].to_list() == [160.0]
    assert result["pf_ratio_time"].to_list() == [START + timedelta(hours=3)]


def test_builder_includes_exact_two_hour_boundary() -> None:
    source = _events(
        [
            (1, 2, "PAO2", 80.0),
            (1, 0, "FIO2", 40.0),
        ]
    )

    result = PFRatioBuilder().build(source)

    assert result["pf_ratio"].to_list() == [200.0]
    assert result["pf_pair_status"].to_list() == ["paired"]


def test_builder_normalizes_fraction_and_percentage_fio2() -> None:
    source = _events(
        [
            (1, 0, "PAO2", 80.0),
            (1, 0, "FIO2", 0.4),
            (2, 0, "PAO2", 80.0),
            (2, 0, "FIO2", 40.0),
        ]
    )

    result = PFRatioBuilder().build(source)

    assert result["pf_fio2_fraction"].to_list() == [0.4, 0.4]
    assert result["pf_ratio"].to_list() == [200.0, 200.0]


@pytest.mark.parametrize(
    ("rows", "expected_status"),
    [
        (
            [(1, 0, "PAO2", 80.0), (1, 3, "FIO2", 40.0)],
            "no_valid_fio2_within_window",
        ),
        (
            [(1, 0, "PAO2", 80.0), (1, 0, "FIO2", 0.0)],
            "no_valid_fio2_within_window",
        ),
        (
            [(1, 0, "PAO2", None), (1, 0, "FIO2", 40.0)],
            "invalid_pao2",
        ),
    ],
)
def test_builder_retains_unpaired_pao2_with_reason(
    rows: list[tuple[int, float, str, float | None]],
    expected_status: str,
) -> None:
    result = PFRatioBuilder().build(_events(rows))

    assert result.height == 1
    assert result["pf_ratio"].to_list() == [None]
    assert result["pf_ratio_time"].to_list() == [None]
    assert result["pf_pair_status"].to_list() == [expected_status]


def test_builder_returns_one_result_per_pao2_without_mutating_input() -> None:
    source = _events(
        [
            (1, 2, "PAO2", 80.0),
            (1, 1, "FIO2", 40.0),
            (1, 1.5, "FIO2", 50.0),
            (1, 4, "PAO2", 90.0),
        ]
    )
    original = source.clone()

    result = PFRatioBuilder().build(source)

    assert result.height == 2
    assert result["pf_pao2_value"].to_list() == [80.0, 90.0]
    assert source.equals(original)


def test_builder_rejects_unresolved_source_collisions() -> None:
    source = _events(
        [
            (1, 0, "PAO2", 80.0),
            (1, 0, "FIO2", 40.0),
            (1, 0, "FIO2", 50.0),
        ]
    )

    with pytest.raises(ValueError, match="collision-free"):
        PFRatioBuilder().build(source)


def test_builder_rejects_missing_columns() -> None:
    with pytest.raises(ValueError, match="NumericValue"):
        PFRatioBuilder().build(_events([]).drop("NumericValue"))


def test_builder_returns_typed_empty_output_without_pao2() -> None:
    source = _events([(1, 0, "FIO2", 40.0)])
    config = PFConfig()

    result = PFRatioBuilder(config).build(source)

    assert result.is_empty()
    assert result.columns == [
        config.encounter_col,
        config.pao2_value_col,
        config.pao2_time_col,
        config.fio2_value_col,
        config.fio2_fraction_col,
        config.fio2_time_col,
        config.pf_ratio_col,
        config.pf_ratio_time_col,
        config.pair_status_col,
    ]
