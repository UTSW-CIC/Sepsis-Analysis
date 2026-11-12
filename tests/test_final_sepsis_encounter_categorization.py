from datetime import datetime, timedelta

import polars as pl
import pytest

from src_strategy.configs.severitysepsis import SeveritySepsisConfig
from src_strategy.events.sepsis import build_final_sepsis_encounter_summary


START = datetime(2026, 1, 1)


def _encounters() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "EncounterEpicCsn": [1, 2, 3, 4],
            "Arrival_Instant": [START] * 4,
            "InpatientAdmissionInstant": [START + timedelta(hours=2)] * 4,
            "LengthOfStayInDays": [5, 4, 3, 2],
            "Death_Flag": [0, 1, 0, 0],
            "Sepsis_Category": ["POA-3", "NPOA-3", "NPOA-1", "POA-1"],
        }
    )


def _summary(
    severity: int,
    flags: list[int],
    onset_hours: list[int | None],
    earliest_evidence_hours: list[int | None] | None = None,
) -> pl.DataFrame:
    onsets = [
        None if hours is None else START + timedelta(hours=hours)
        for hours in onset_hours
    ]
    earliest_evidence = [
        None if hours is None else START + timedelta(hours=hours)
        for hours in (
            onset_hours
            if earliest_evidence_hours is None
            else earliest_evidence_hours
        )
    ]
    return pl.DataFrame(
        {
            "EncounterEpicCsn": [1, 2, 3, 4],
            f"sepsis_{severity}_flag": flags,
            f"sepsis_{severity}_earliest_evidence_dt": earliest_evidence,
            f"sepsis_{severity}_dt": onsets,
            f"sepsis_{severity}_association_count": flags,
        },
        schema_overrides={
            f"sepsis_{severity}_earliest_evidence_dt": pl.Datetime("us"),
            f"sepsis_{severity}_dt": pl.Datetime("us"),
        },
    )


def test_final_summary_uses_maximum_severity_and_first_positive_onset() -> None:
    result = build_final_sepsis_encounter_summary(
        _encounters(),
        _summary(
            1,
            [1, 0, 1, 0],
            [10, None, 48, None],
            [8, None, 48, None],
        ),
        _summary(
            2,
            [1, 0, 0, 0],
            [5, None, None, None],
            [3, None, None, None],
        ),
        _summary(
            3,
            [1, 1, 0, 0],
            [20, 49, None, None],
            [2, 49, None, None],
        ),
    )

    assert result["calculated_sepsis_severity"].to_list() == [3, 3, 1, 0]
    assert result["first_sepsis_dt"].to_list() == [
        START + timedelta(hours=2),
        START + timedelta(hours=49),
        START + timedelta(hours=48),
        None,
    ]
    assert result["calculated_poa_status"].to_list() == [
        "POA",
        "NPOA",
        "POA",
        None,
    ]
    assert result["calculated_sepsis_category"].to_list() == [
        "POA-3",
        "NPOA-3",
        "POA-1",
        "No Sepsis",
    ]
    assert result["sepsis_category_match"].to_list() == [
        True,
        True,
        False,
        False,
    ]
    assert result["sepsis_1_association_count"].to_list() == [1, 0, 1, 0]
    assert result.columns[:6] == [
        "EncounterEpicCsn",
        "Arrival_Instant",
        "InpatientAdmissionInstant",
        "LengthOfStayInDays",
        "Death_Flag",
        "Sepsis_Category",
    ]


def test_final_summary_requires_arrival_for_positive_sepsis() -> None:
    encounters = _encounters().with_columns(
        pl.when(pl.col("EncounterEpicCsn") == 1)
        .then(pl.lit(None, dtype=pl.Datetime("us")))
        .otherwise(pl.col("Arrival_Instant"))
        .alias("Arrival_Instant")
    )

    with pytest.raises(ValueError, match="sepsis-positive encounters"):
        build_final_sepsis_encounter_summary(
            encounters,
            _summary(1, [1, 0, 0, 0], [1, None, None, None]),
            _summary(2, [0, 0, 0, 0], [None, None, None, None]),
            _summary(3, [0, 0, 0, 0], [None, None, None, None]),
        )


def test_final_summary_rejects_flag_onset_inconsistency() -> None:
    with pytest.raises(ValueError, match="flag/onset inconsistencies"):
        build_final_sepsis_encounter_summary(
            _encounters(),
            _summary(1, [0, 0, 0, 0], [1, None, None, None]),
            _summary(2, [0, 0, 0, 0], [None, None, None, None]),
            _summary(3, [0, 0, 0, 0], [None, None, None, None]),
        )


def test_poa_window_must_be_non_negative() -> None:
    with pytest.raises(ValueError, match="finite and non-negative"):
        SeveritySepsisConfig(poa_arrival_hours=-1)
