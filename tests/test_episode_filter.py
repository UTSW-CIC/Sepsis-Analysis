from datetime import datetime, timedelta

import polars as pl
import pytest

from src_strategy.events.episode_filter import (
    bridge_equal_states_across_unknown,
    build_state_episodes,
    filter_short_positive_episodes,
    merge_positive_across_short_negative_gaps,
    run_episode_filter,
)
from src_strategy.configs.shortdurationfilter import EpisodeFilterConfig


def _segment_frame(rows: list[tuple[int, int, int, int]]) -> pl.DataFrame:
    start = datetime(2026, 1, 1)
    return pl.DataFrame(
        {
            "EncounterEpicCsn": [row[0] for row in rows],
            "state": [row[1] for row in rows],
            "segment_start": [
                start + timedelta(minutes=row[2]) for row in rows
            ],
            "segment_end": [
                start + timedelta(minutes=row[3]) for row in rows
            ],
        }
    )


def test_build_state_episodes_collapses_only_contiguous_equal_states() -> None:
    segments = _segment_frame(
        [
            (1, 1, 0, 5),
            (1, 1, 5, 10),
            (1, 0, 10, 20),
            (1, -1, 20, 25),
            (1, -1, 25, 30),
            (1, 1, 30, 40),
        ]
    )

    result = build_state_episodes(segments)

    assert result["episode_id"].to_list() == [1, 2, 3, 4]
    assert result["state"].to_list() == [1, 0, -1, 1]
    assert result["episode_duration_minutes"].to_list() == [
        10.0,
        10.0,
        10.0,
        10.0,
    ]
    assert result["source_segment_count"].to_list() == [2, 1, 2, 1]


def test_episode_ids_restart_per_encounter_and_input_is_sorted() -> None:
    segments = _segment_frame(
        [
            (2, 0, 5, 10),
            (1, 1, 10, 20),
            (2, 1, 0, 5),
            (1, 1, 0, 10),
        ]
    )

    result = build_state_episodes(segments)

    assert result.select("EncounterEpicCsn", "episode_id").rows() == [
        (1, 1),
        (2, 1),
        (2, 2),
    ]
    assert result["state"].to_list() == [1, 1, 0]


@pytest.mark.parametrize(
    "rows",
    [
        [(1, 1, 0, 5), (1, 0, 6, 10)],
        [(1, 1, 0, 6), (1, 0, 5, 10)],
    ],
)
def test_gaps_and_overlaps_must_be_explicit_unknown_segments(
    rows: list[tuple[int, int, int, int]],
) -> None:
    with pytest.raises(ValueError, match="gaps or overlaps"):
        build_state_episodes(_segment_frame(rows))


@pytest.mark.parametrize("state", [-2, 2])
def test_rejects_states_outside_the_three_state_contract(state: int) -> None:
    with pytest.raises(ValueError, match="outside"):
        build_state_episodes(_segment_frame([(1, state, 0, 5)]))


def test_rejects_non_positive_segments() -> None:
    with pytest.raises(ValueError, match="non-positive"):
        build_state_episodes(_segment_frame([(1, 1, 5, 5)]))


def test_empty_input_returns_the_episode_schema() -> None:
    result = build_state_episodes(_segment_frame([]))

    assert result.is_empty()
    assert result.columns == [
        "EncounterEpicCsn",
        "episode_id",
        "state",
        "episode_start",
        "episode_end",
        "episode_duration_minutes",
        "source_segment_count",
    ]


def test_bridges_positive_states_across_one_unknown_episode() -> None:
    raw = build_state_episodes(
        _segment_frame(
            [
                (1, 1, 0, 10),
                (1, -1, 10, 15),
                (1, 1, 15, 30),
            ]
        )
    )

    result = bridge_equal_states_across_unknown(raw)

    assert result.height == 1
    assert result["state"].to_list() == [1]
    assert result["episode_duration_minutes"].to_list() == [30.0]
    assert result["source_episode_ids"].to_list() == [[1, 2, 3]]
    assert result["source_episode_count"].to_list() == [3]
    assert result["bridged_unknown_gap_count"].to_list() == [1]


def test_bridges_negative_states_across_one_unknown_episode() -> None:
    raw = build_state_episodes(
        _segment_frame(
            [
                (1, 0, 0, 10),
                (1, -1, 10, 12),
                (1, 0, 12, 20),
            ]
        )
    )

    result = bridge_equal_states_across_unknown(raw)

    assert result.height == 1
    assert result["state"].to_list() == [0]
    assert result["source_episode_ids"].to_list() == [[1, 2, 3]]
    assert result["bridged_unknown_gap_count"].to_list() == [1]


def test_different_states_do_not_absorb_the_unknown_interval() -> None:
    raw = build_state_episodes(
        _segment_frame(
            [
                (1, 1, 0, 10),
                (1, -1, 10, 15),
                (1, 0, 15, 25),
            ]
        )
    )

    result = bridge_equal_states_across_unknown(raw)

    assert result["state"].to_list() == [1, -1, 0]
    assert result["episode_duration_minutes"].to_list() == [10.0, 5.0, 10.0]
    assert result["source_episode_ids"].to_list() == [[1], [2], [3]]
    assert result["bridged_unknown_gap_count"].to_list() == [0, 0, 0]


def test_leading_and_trailing_unknown_episodes_remain_explicit() -> None:
    raw = build_state_episodes(
        _segment_frame(
            [
                (1, -1, 0, 5),
                (1, 1, 5, 15),
                (1, -1, 15, 20),
            ]
        )
    )

    result = bridge_equal_states_across_unknown(raw)

    assert result["state"].to_list() == [-1, 1, -1]
    assert result["bridged_unknown_gap_count"].to_list() == [0, 0, 0]


def test_connected_unknown_bridges_collapse_into_one_episode() -> None:
    raw = build_state_episodes(
        _segment_frame(
            [
                (1, 1, 0, 10),
                (1, -1, 10, 12),
                (1, 1, 12, 20),
                (1, -1, 20, 23),
                (1, 1, 23, 30),
            ]
        )
    )

    result = bridge_equal_states_across_unknown(raw)

    assert result.height == 1
    assert result["episode_duration_minutes"].to_list() == [30.0]
    assert result["source_episode_ids"].to_list() == [[1, 2, 3, 4, 5]]
    assert result["bridged_unknown_gap_count"].to_list() == [2]


def test_unknown_bridge_groups_and_ids_are_encounter_local() -> None:
    raw = build_state_episodes(
        _segment_frame(
            [
                (2, 0, 0, 5),
                (1, 1, 0, 10),
                (2, -1, 5, 7),
                (1, -1, 10, 12),
                (2, 0, 7, 10),
                (1, 0, 12, 20),
            ]
        )
    )

    result = bridge_equal_states_across_unknown(raw)

    assert result.select("EncounterEpicCsn", "episode_id", "state").rows() == [
        (1, 1, 1),
        (1, 2, -1),
        (1, 3, 0),
        (2, 1, 0),
    ]
    assert result["bridged_unknown_gap_count"].to_list() == [0, 0, 0, 1]


def test_merges_one_short_negative_gap_and_retains_other_states() -> None:
    bridged = bridge_equal_states_across_unknown(
        build_state_episodes(
            _segment_frame(
                [
                    (1, 1, 0, 10),
                    (1, 0, 10, 15),
                    (1, 1, 15, 30),
                    (1, 0, 30, 50),
                    (1, 1, 50, 60),
                    (1, -1, 60, 65),
                ]
            )
        )
    )

    result = merge_positive_across_short_negative_gaps(
        bridged,
        threshold_minutes=10,
    )

    assert result["state"].to_list() == [1, 0, 1, -1]
    assert result["episode_duration_minutes"].to_list() == [30.0, 20.0, 10.0, 5.0]
    assert result["source_episode_ids"].to_list() == [[1, 2, 3], [4], [5], [6]]
    assert result["bridged_negative_gap_count"].to_list() == [1, 0, 0, 0]


@pytest.mark.parametrize("gap_minutes", [5, 6])
def test_equal_or_longer_negative_gap_remains_separate(gap_minutes: int) -> None:
    bridged = bridge_equal_states_across_unknown(
        build_state_episodes(
            _segment_frame(
                [
                    (1, 1, 0, 10),
                    (1, 0, 10, 10 + gap_minutes),
                    (1, 1, 10 + gap_minutes, 30),
                ]
            )
        )
    )

    result = merge_positive_across_short_negative_gaps(
        bridged,
        threshold_minutes=5,
    )

    assert result["state"].to_list() == [1, 0, 1]
    assert result["bridged_negative_gap_count"].to_list() == [0, 0, 0]


def test_connected_short_negative_gaps_collapse_into_one_positive_episode() -> None:
    bridged = bridge_equal_states_across_unknown(
        build_state_episodes(
            _segment_frame(
                [
                    (1, 1, 0, 10),
                    (1, 0, 10, 12),
                    (1, 1, 12, 20),
                    (1, 0, 20, 23),
                    (1, 1, 23, 30),
                ]
            )
        )
    )

    result = merge_positive_across_short_negative_gaps(
        bridged,
        threshold_minutes=5,
    )

    assert result.height == 1
    assert result["state"].to_list() == [1]
    assert result["episode_duration_minutes"].to_list() == [30.0]
    assert result["source_episode_ids"].to_list() == [[1, 2, 3, 4, 5]]
    assert result["bridged_negative_gap_count"].to_list() == [2]


def test_leading_and_trailing_negative_episodes_are_retained() -> None:
    bridged = bridge_equal_states_across_unknown(
        build_state_episodes(
            _segment_frame(
                [
                    (1, 0, 0, 2),
                    (1, 1, 2, 20),
                    (1, 0, 20, 23),
                ]
            )
        )
    )

    result = merge_positive_across_short_negative_gaps(
        bridged,
        threshold_minutes=5,
    )

    assert result["state"].to_list() == [0, 1, 0]
    assert result["bridged_negative_gap_count"].to_list() == [0, 0, 0]


def test_explicit_unknown_episode_blocks_negative_gap_merging() -> None:
    bridged = bridge_equal_states_across_unknown(
        build_state_episodes(
            _segment_frame(
                [
                    (1, 1, 0, 10),
                    (1, 0, 10, 12),
                    (1, -1, 12, 14),
                    (1, 1, 14, 20),
                ]
            )
        )
    )

    result = merge_positive_across_short_negative_gaps(
        bridged,
        threshold_minutes=5,
    )

    assert result["state"].to_list() == [1, 0, -1, 1]
    assert result["bridged_negative_gap_count"].to_list() == [0, 0, 0, 0]


def test_short_negative_gap_groups_and_ids_are_encounter_local() -> None:
    bridged = bridge_equal_states_across_unknown(
        build_state_episodes(
            _segment_frame(
                [
                    (2, 1, 0, 5),
                    (1, 1, 0, 10),
                    (2, 0, 5, 7),
                    (1, 0, 10, 20),
                    (2, 1, 7, 10),
                    (1, 1, 20, 30),
                ]
            )
        )
    )

    result = merge_positive_across_short_negative_gaps(
        bridged,
        threshold_minutes=5,
    )

    assert result.select("EncounterEpicCsn", "episode_id", "state").rows() == [
        (1, 1, 1),
        (1, 2, 0),
        (1, 3, 1),
        (2, 1, 1),
    ]
    assert result["bridged_negative_gap_count"].to_list() == [0, 0, 0, 1]


def test_preserves_lineage_from_unknown_and_negative_gap_bridging() -> None:
    bridged = bridge_equal_states_across_unknown(
        build_state_episodes(
            _segment_frame(
                [
                    (1, 1, 0, 5),
                    (1, -1, 5, 7),
                    (1, 1, 7, 10),
                    (1, 0, 10, 12),
                    (1, 1, 12, 20),
                ]
            )
        )
    )

    result = merge_positive_across_short_negative_gaps(
        bridged,
        threshold_minutes=5,
    )

    assert result.height == 1
    assert result["source_segment_count"].to_list() == [5]
    assert result["source_episode_ids"].to_list() == [[1, 2, 3, 4, 5]]
    assert result["source_episode_count"].to_list() == [5]
    assert result["bridged_unknown_gap_count"].to_list() == [1]
    assert result["bridged_negative_gap_count"].to_list() == [1]


def test_zero_threshold_is_valid_and_does_not_merge() -> None:
    bridged = bridge_equal_states_across_unknown(
        build_state_episodes(
            _segment_frame(
                [
                    (1, 1, 0, 10),
                    (1, 0, 10, 12),
                    (1, 1, 12, 20),
                ]
            )
        )
    )

    result = merge_positive_across_short_negative_gaps(
        bridged,
        threshold_minutes=0,
    )

    assert result["state"].to_list() == [1, 0, 1]


@pytest.mark.parametrize("threshold", [-1, float("inf"), float("nan"), "bad"])
def test_rejects_invalid_negative_gap_thresholds(threshold: object) -> None:
    bridged = bridge_equal_states_across_unknown(
        build_state_episodes(_segment_frame([(1, 1, 0, 10)]))
    )

    with pytest.raises(ValueError, match="finite non-negative"):
        merge_positive_across_short_negative_gaps(
            bridged,
            threshold_minutes=threshold,  # type: ignore[arg-type]
        )


def test_short_gap_merge_empty_input_returns_the_output_schema() -> None:
    bridged = bridge_equal_states_across_unknown(
        build_state_episodes(_segment_frame([]))
    )

    result = merge_positive_across_short_negative_gaps(
        bridged,
        threshold_minutes=5,
    )

    assert result.is_empty()
    assert result.columns == [
        "EncounterEpicCsn",
        "episode_id",
        "state",
        "episode_start",
        "episode_end",
        "episode_duration_minutes",
        "source_segment_count",
        "source_episode_ids",
        "source_episode_count",
        "bridged_unknown_gap_count",
        "bridged_negative_gap_count",
    ]


def test_short_gap_merge_rejects_discontinuous_episode_timeline() -> None:
    bridged = bridge_equal_states_across_unknown(
        build_state_episodes(
            _segment_frame(
                [
                    (1, 1, 0, 10),
                    (1, 0, 10, 12),
                    (1, 1, 12, 20),
                ]
            )
        )
    ).with_columns(
        pl.when(pl.col("episode_id") == 2)
        .then(pl.col("episode_start") + pl.duration(minutes=1))
        .otherwise(pl.col("episode_start"))
        .alias("episode_start")
    )

    with pytest.raises(ValueError, match="gaps or overlaps"):
        merge_positive_across_short_negative_gaps(
            bridged,
            threshold_minutes=5,
        )


def test_positive_duration_filter_retains_equal_and_longer_episodes() -> None:
    merged = merge_positive_across_short_negative_gaps(
        bridge_equal_states_across_unknown(
            build_state_episodes(
                _segment_frame(
                    [
                        (1, 1, 0, 5),
                        (1, 0, 5, 10),
                        (1, 1, 10, 20),
                        (1, 0, 20, 25),
                        (1, 1, 25, 40),
                    ]
                )
            )
        ),
        threshold_minutes=0,
    )

    result = filter_short_positive_episodes(
        merged,
        threshold_minutes=10,
    )

    assert result["episode_id"].to_list() == [3, 5]
    assert result["state"].to_list() == [1, 1]
    assert result["episode_duration_minutes"].to_list() == [10.0, 15.0]
    assert result["source_episode_ids"].to_list() == [[3], [5]]


def test_zero_positive_duration_threshold_retains_every_positive_episode() -> None:
    merged = merge_positive_across_short_negative_gaps(
        bridge_equal_states_across_unknown(
            build_state_episodes(
                _segment_frame(
                    [
                        (1, 0, 0, 2),
                        (1, 1, 2, 5),
                        (1, -1, 5, 7),
                    ]
                )
            )
        ),
        threshold_minutes=0,
    )

    result = filter_short_positive_episodes(
        merged,
        threshold_minutes=0,
    )

    assert result["episode_id"].to_list() == [2]
    assert result["episode_duration_minutes"].to_list() == [3.0]


@pytest.mark.parametrize("threshold", [-1, float("inf"), float("nan"), "bad"])
def test_rejects_invalid_positive_duration_thresholds(threshold: object) -> None:
    merged = merge_positive_across_short_negative_gaps(
        bridge_equal_states_across_unknown(
            build_state_episodes(_segment_frame([(1, 1, 0, 10)]))
        ),
        threshold_minutes=0,
    )

    with pytest.raises(ValueError, match="finite non-negative"):
        filter_short_positive_episodes(
            merged,
            threshold_minutes=threshold,  # type: ignore[arg-type]
        )


def test_positive_duration_filter_empty_input_preserves_schema() -> None:
    merged = merge_positive_across_short_negative_gaps(
        bridge_equal_states_across_unknown(
            build_state_episodes(_segment_frame([]))
        ),
        threshold_minutes=0,
    )

    result = filter_short_positive_episodes(
        merged,
        threshold_minutes=10,
    )

    assert result.is_empty()
    assert result.schema == merged.schema


@pytest.mark.parametrize("state", [0.5, 1.9, float("inf"), float("nan")])
def test_rejects_non_integer_state_values(state: float) -> None:
    with pytest.raises(ValueError, match="outside"):
        build_state_episodes(_segment_frame([(1, state, 0, 5)]))


def test_unknown_bridge_rejects_non_positive_episode_intervals() -> None:
    raw = build_state_episodes(_segment_frame([(1, 1, 0, 5)]))
    invalid = raw.with_columns(
        pl.col("episode_start").alias("episode_end")
    )

    with pytest.raises(ValueError, match="non-positive"):
        bridge_equal_states_across_unknown(invalid)


def test_generic_runner_uses_independent_status_settings() -> None:
    segments = _segment_frame(
        [
            (1, 1, 0, 10),
            (1, -1, 10, 12),
            (1, 1, 12, 25),
        ]
    )
    bridged_config = EpisodeFilterConfig(
        status_name="status_a",
        bridge_unknown=True,
        negative_gap_minutes=20,
        minimum_positive_minutes=20,
    )
    unbridged_config = EpisodeFilterConfig(
        status_name="status_b",
        bridge_unknown=False,
        negative_gap_minutes=5,
        minimum_positive_minutes=12,
    )

    status_a = run_episode_filter(segments, config=bridged_config)
    status_b = run_episode_filter(segments, config=unbridged_config)

    assert list(status_a) == ["raw", "bridged", "merged", "filtered"]
    assert status_a["bridged"]["state"].to_list() == [1]
    assert status_a["filtered"]["episode_duration_minutes"].to_list() == [25.0]
    assert status_b["bridged"]["state"].to_list() == [1, -1, 1]
    assert status_b["bridged"]["bridged_unknown_gap_count"].to_list() == [0, 0, 0]
    assert status_b["filtered"]["episode_duration_minutes"].to_list() == [13.0]
