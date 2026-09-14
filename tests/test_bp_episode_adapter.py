from datetime import datetime, timedelta

import polars as pl
import pytest

from src_strategy.configs.shortdurationfilter import bp_episode_filter_config
from src_strategy.events.episode_filter import run_episode_filter
from src_strategy.events.hypotension import build_bp_state_segments


START = datetime(2026, 1, 1)


def _bp_frame(
    rows: list[
        tuple[
            int,
            int,
            float | None,
            int | None,
            float | None,
            int | None,
        ]
    ],
) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "EncounterEpicCsn": [row[0] for row in rows],
            "Event_DateTime": [START + timedelta(hours=row[1]) for row in rows],
            "last_sbp_8h": [row[2] for row in rows],
            "last_sbp_8h_source_ts": [
                START + timedelta(hours=row[3]) if row[3] is not None else None
                for row in rows
            ],
            "last_map_8h": [row[4] for row in rows],
            "last_map_8h_source_ts": [
                START + timedelta(hours=row[5]) if row[5] is not None else None
                for row in rows
            ],
        },
        schema_overrides={
            "EncounterEpicCsn": pl.Int64,
            "Event_DateTime": pl.Datetime,
            "last_sbp_8h": pl.Float64,
            "last_sbp_8h_source_ts": pl.Datetime,
            "last_map_8h": pl.Float64,
            "last_map_8h_source_ts": pl.Datetime,
        },
    )


def _encounters(rows: list[tuple[int, float | None]]) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "EncounterEpicCsn": [row[0] for row in rows],
            "Baseline_SBP": [row[1] for row in rows],
        },
        schema_overrides={
            "EncounterEpicCsn": pl.Int64,
            "Baseline_SBP": pl.Float64,
        },
    )


def test_bp_episode_filter_is_independent_and_disabled_by_default() -> None:
    assert bp_episode_filter_config.status_name == "hypotension"
    assert bp_episode_filter_config.enabled is False
    assert bp_episode_filter_config.bridge_unknown is True
    assert bp_episode_filter_config.negative_gap_minutes == 20.0
    assert bp_episode_filter_config.minimum_positive_minutes == 20.0


@pytest.mark.parametrize(
    ("sbp", "baseline", "map_value", "positive_flag"),
    [
        (85.0, 120.0, 70.0, "sbp90_flag"),
        (100.0, 145.0, 70.0, "sbpdelta40_flag"),
        (100.0, 120.0, 60.0, "map65_flag"),
        (85.0, None, 70.0, "sbp90_flag"),
    ],
)
def test_each_approved_driver_can_establish_hypotension(
    sbp: float,
    baseline: float | None,
    map_value: float,
    positive_flag: str,
) -> None:
    aggregated = _bp_frame(
        [
            (1, 0, sbp, 0, map_value, 0),
            (1, 2, sbp, 0, map_value, 0),
        ]
    )

    result = build_bp_state_segments(aggregated, _encounters([(1, baseline)]))

    assert result["state"].to_list() == [1]
    assert result[positive_flag].to_list() == [1]
    assert result["hypotension_flag"].to_list() == [1]


def test_strict_threshold_boundaries_are_measured_negative() -> None:
    aggregated = _bp_frame(
        [
            (1, 0, 90.0, 0, 65.0, 0),
            (1, 2, 90.0, 0, 65.0, 0),
        ]
    )

    result = build_bp_state_segments(aggregated, _encounters([(1, 130.0)]))

    assert result.select(
        "sbp90_flag",
        "sbpdelta40_flag",
        "map65_flag",
        "state",
    ).row(0) == (0, 0, 0, 0)


def test_positive_driver_change_does_not_interrupt_combined_state() -> None:
    aggregated = _bp_frame(
        [
            (1, 0, 85.0, 0, 70.0, 0),
            (1, 4, 100.0, 4, 60.0, 4),
            (1, 6, 100.0, 4, 60.0, 4),
        ]
    )

    result = build_bp_state_segments(aggregated, _encounters([(1, 120.0)]))

    assert result.select(
        "state", "sbp_hypotension_flag", "map65_flag"
    ).rows() == [(1, 1, 0), (1, 0, 1)]
    assert result["segment_start"].to_list() == [
        START,
        START + timedelta(hours=4),
    ]
    assert result["segment_end"].to_list() == [
        START + timedelta(hours=4),
        START + timedelta(hours=6),
    ]


def test_missing_evidence_remains_unknown_unless_another_driver_is_positive() -> None:
    aggregated = _bp_frame(
        [
            (1, 0, 100.0, 0, None, None),
            (1, 2, 100.0, 0, None, None),
            (2, 0, None, None, 70.0, 0),
            (2, 2, None, None, 70.0, 0),
            (3, 0, 100.0, 0, 70.0, 0),
            (3, 2, 100.0, 0, 70.0, 0),
            (4, 0, None, None, 60.0, 0),
            (4, 2, None, None, 60.0, 0),
        ]
    )
    encounters = _encounters(
        [(1, 120.0), (2, 120.0), (3, 120.0), (4, 120.0)]
    )

    result = build_bp_state_segments(aggregated, encounters)

    assert result.select("EncounterEpicCsn", "state").rows() == [
        (1, -1),
        (2, -1),
        (3, 0),
        (4, 1),
    ]


def test_measurements_expire_at_eight_hours() -> None:
    aggregated = _bp_frame(
        [
            (1, 0, 85.0, 0, 70.0, 0),
            (1, 10, None, None, None, None),
        ]
    )

    result = build_bp_state_segments(aggregated, _encounters([(1, 120.0)]))

    assert result["state"].to_list() == [1, -1]
    assert result["segment_start"].to_list() == [
        START,
        START + timedelta(hours=8),
    ]
    assert result["segment_end"].to_list() == [
        START + timedelta(hours=8),
        START + timedelta(hours=10),
    ]
    assert result["last_sbp_8h_source_ts"].to_list() == [START, None]
    assert result["last_map_8h_source_ts"].to_list() == [START, None]


def test_measurement_at_final_event_has_no_observable_segment() -> None:
    aggregated = _bp_frame(
        [
            (1, 0, 100.0, 0, 70.0, 0),
            (1, 5, 85.0, 5, 70.0, 0),
        ]
    )

    result = build_bp_state_segments(aggregated, _encounters([(1, 120.0)]))

    assert result.select("state", "segment_start", "segment_end").rows() == [
        (0, START, START + timedelta(hours=5))
    ]


def test_bp_segments_use_the_shared_episode_filter_contract() -> None:
    aggregated = _bp_frame(
        [
            (1, 0, 85.0, 0, 70.0, 0),
            (1, 2, 85.0, 0, 70.0, 0),
        ]
    )
    segments = build_bp_state_segments(
        aggregated,
        _encounters([(1, 120.0)]),
    )

    result = run_episode_filter(segments, config=bp_episode_filter_config)

    assert result["raw"]["state"].to_list() == [1]
    assert result["filtered"]["episode_duration_minutes"].to_list() == [120.0]


def test_raw_map_column_is_not_used() -> None:
    aggregated = _bp_frame(
        [
            (1, 0, 100.0, 0, 70.0, 0),
            (1, 2, 100.0, 0, 70.0, 0),
        ]
    ).with_columns(pl.lit(50.0).alias("map"))

    result = build_bp_state_segments(aggregated, _encounters([(1, 120.0)]))

    assert result["map65_flag"].to_list() == [0]
    assert result["state"].to_list() == [0]


def test_adapter_rejects_duplicate_backbone_keys() -> None:
    aggregated = _bp_frame(
        [
            (1, 0, 100.0, 0, 70.0, 0),
            (1, 0, 100.0, 0, 70.0, 0),
        ]
    )

    with pytest.raises(ValueError, match="duplicate keys"):
        build_bp_state_segments(aggregated, _encounters([(1, 120.0)]))


def test_adapter_rejects_value_source_timestamp_mismatch() -> None:
    aggregated = _bp_frame(
        [
            (1, 0, 100.0, None, 70.0, 0),
            (1, 2, 100.0, None, 70.0, 0),
        ]
    )

    with pytest.raises(ValueError, match="mismatched values"):
        build_bp_state_segments(aggregated, _encounters([(1, 120.0)]))


def test_missing_encounter_row_is_retained_as_auditable_missing_baseline() -> None:
    aggregated = _bp_frame(
        [
            (1, 0, 100.0, 0, 70.0, 0),
            (1, 2, 100.0, 0, 70.0, 0),
        ]
    )

    result = build_bp_state_segments(aggregated, _encounters([]))

    assert result["state"].to_list() == [-1]
    assert result["Baseline_SBP"].to_list() == [None]
    assert result["baseline_encounter_row_available"].to_list() == [False]
