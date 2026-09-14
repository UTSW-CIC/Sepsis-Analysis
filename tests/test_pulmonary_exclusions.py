from datetime import datetime, timedelta

import polars as pl
import pytest

from src_strategy.events.pulmonarydysfunction import (
    build_pulmonary_exclusion_evidence,
)


START = datetime(2026, 1, 1)


def test_exclusions_retain_every_matching_source_event() -> None:
    source = pl.DataFrame(
        {
            "EncounterEpicCsn": [1, 1, 2, 3],
            "Event_DateTime": [
                START,
                START + timedelta(hours=1),
                START,
                START,
            ],
            "Event_Grouper": [
                "Encounter Diagnosis",
                "Vent On/Off",
                "Problem List",
                "Vent On/Off",
            ],
            "Value": ["Z99.11", "$ Home Vent Used", "Z93.0", "Standby"],
            "Event_Name": ["a", "b", "c", "d"],
        }
    )

    result = build_pulmonary_exclusion_evidence(source)

    assert result.height == 3
    assert result["pulmonary_exclusion_reason"].to_list() == [
        "diagnosis_code:Z99.11",
        "home_vent",
        "diagnosis_code:Z93.0",
    ]
    assert result["pulmonary_exclusion_time"].to_list() == [
        START,
        START + timedelta(hours=1),
        START,
    ]
    assert result["pulmonary_exclusion_flag"].to_list() == [1, 1, 1]
    assert result.select(source.columns).equals(source.head(3))


def test_exclusions_return_typed_added_columns_when_no_match() -> None:
    source = pl.DataFrame(
        {
            "EncounterEpicCsn": [1],
            "Event_DateTime": [START],
            "Event_Grouper": ["Vent On/Off"],
            "Value": ["Standby"],
        }
    )

    result = build_pulmonary_exclusion_evidence(source)

    assert result.is_empty()
    assert result.schema["pulmonary_exclusion_flag"] == pl.Int8
    assert result.schema["pulmonary_exclusion_reason"] == pl.String
    assert result.schema["pulmonary_exclusion_time"] == pl.Datetime


def test_exclusions_reject_missing_required_columns() -> None:
    source = pl.DataFrame(
        {
            "EncounterEpicCsn": [1],
            "Event_DateTime": [START],
            "Event_Grouper": ["Problem List"],
        }
    )

    with pytest.raises(ValueError, match="Value"):
        build_pulmonary_exclusion_evidence(source)
