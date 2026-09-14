from datetime import datetime, timedelta

import polars as pl
import pytest

from src_strategy.events.pulmonarydysfunction import (
    build_pulmonary_state_segments,
    build_pulmonary_state_timeline,
)


START = datetime(2026, 1, 1)


def _events(
    rows: list[tuple[int, float, str, str | None]],
) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "EncounterEpicCsn": [row[0] for row in rows],
            "Event_DateTime": [
                START + timedelta(hours=row[1]) for row in rows
            ],
            "Event_Grouper": [row[2] for row in rows],
            "Value": [row[3] for row in rows],
        }
    )


def _pf_events(
    rows: list[tuple[int, float, float | None, str]],
) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "EncounterEpicCsn": [row[0] for row in rows],
            "pf_ratio": [row[2] for row in rows],
            "pf_ratio_time": [
                START + timedelta(hours=row[1]) for row in rows
            ],
            "pf_pair_status": [row[3] for row in rows],
        },
        schema_overrides={
            "EncounterEpicCsn": pl.Int64,
            "pf_ratio": pl.Float64,
            "pf_ratio_time": pl.Datetime,
            "pf_pair_status": pl.String,
        },
    )


def test_state_is_unknown_then_persists_from_start_to_termination() -> None:
    events = _events(
        [
            (1, 0, "Unrelated", None),
            (1, 1, "Vent on Documentation", None),
            (1, 3, "Vent off Documentation", None),
            (1, 4, "Unrelated", None),
        ]
    )

    segments = build_pulmonary_state_segments(events, _pf_events([]))

    assert segments["segment_start"].to_list() == [
        START,
        START + timedelta(hours=1),
        START + timedelta(hours=3),
    ]
    assert segments["segment_end"].to_list() == [
        START + timedelta(hours=1),
        START + timedelta(hours=3),
        START + timedelta(hours=4),
    ]
    assert segments["pulmonary_dysfunction_flag"].to_list() == [None, 1, 0]


def test_simultaneous_termination_wins_and_retains_both_types() -> None:
    events = _events(
        [
            (1, 0, "Unrelated", None),
            (1, 1, "Vent on Documentation", None),
            (1, 1, "Vent off Documentation", None),
            (1, 2, "Unrelated", None),
        ]
    )

    timeline = build_pulmonary_state_timeline(events, _pf_events([]))
    transition = timeline.filter(
        pl.col("pulmonary_state_time") == START + timedelta(hours=1)
    )

    assert transition["pulmonary_dysfunction_flag"].to_list() == [0]
    assert transition["pulmonary_transition_type"].to_list() == [[
        "vent_documentation_start",
        "vent_documentation_termination",
    ]]


@pytest.mark.parametrize("value", ["Z99.11", "Z93.0", "$ Home Vent Used"])
def test_exclusion_forces_zero_for_entire_encounter(value: str) -> None:
    grouper = "Vent On/Off" if value.startswith("$") else "Problem List"
    events = _events(
        [
            (1, 0, "Unrelated", None),
            (1, 1, "Vent on Documentation", None),
            (1, 2, grouper, value),
            (1, 3, "Unrelated", None),
        ]
    )

    timeline = build_pulmonary_state_timeline(events, _pf_events([]))

    assert timeline["pulmonary_dysfunction_flag"].to_list() == [0, 0, 0]
    assert timeline["pulmonary_exclusion_flag"].to_list() == [1, 1, 1]


def test_pf_ratio_events_start_and_terminate_state() -> None:
    events = _events(
        [(1, 0, "Unrelated", None), (1, 4, "Unrelated", None)]
    )
    pf_events = _pf_events(
        [(1, 1, 199.9, "paired"), (1, 3, 200.1, "paired")]
    )

    segments = build_pulmonary_state_segments(events, pf_events)

    assert segments["pulmonary_dysfunction_flag"].to_list() == [None, 1, 0]
    assert segments["pulmonary_transition_type"].to_list() == [
        None,
        ["pf_ratio_start"],
        ["pf_ratio_termination"],
    ]


def test_pf_ratio_exactly_200_creates_no_transition() -> None:
    events = _events(
        [(1, 0, "Unrelated", None), (1, 2, "Unrelated", None)]
    )

    segments = build_pulmonary_state_segments(
        events,
        _pf_events([(1, 1, 200.0, "paired")]),
    )

    assert segments["pulmonary_dysfunction_flag"].to_list() == [None]
    assert segments["pulmonary_transition_time"].to_list() == [None]


def test_state_rejects_missing_event_or_pf_columns() -> None:
    events = _events([(1, 0, "Unrelated", None)])

    with pytest.raises(ValueError, match="Value"):
        build_pulmonary_state_timeline(events.drop("Value"), _pf_events([]))

    with pytest.raises(ValueError, match="pf_pair_status"):
        build_pulmonary_state_timeline(
            events,
            _pf_events([]).drop("pf_pair_status"),
        )
