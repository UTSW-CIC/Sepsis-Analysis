from datetime import datetime, timedelta

import polars as pl

from src_strategy.configs.shortdurationfilter import EpisodeFilterConfig
from src_strategy.events.episode_filter import run_episode_filter
from src_strategy.events.hypotension import (
    attach_effective_hypotension,
    build_effective_hypotension_episodes,
)


START = datetime(2026, 1, 1)


def _segments(rows: list[tuple[int, int, int]]) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "EncounterEpicCsn": [1] * len(rows),
            "state": [row[0] for row in rows],
            "segment_start": [
                START + timedelta(minutes=row[1]) for row in rows
            ],
            "segment_end": [
                START + timedelta(minutes=row[2]) for row in rows
            ],
        },
        schema_overrides={"state": pl.Int8},
    )


def _config(*, bridge_unknown: bool = True) -> EpisodeFilterConfig:
    return EpisodeFilterConfig(
        status_name="hypotension",
        bridge_unknown=bridge_unknown,
        negative_gap_minutes=20,
        minimum_positive_minutes=20,
    )


def test_retained_episode_does_not_turn_merged_negative_gap_positive() -> None:
    results = run_episode_filter(
        _segments([(1, 0, 10), (0, 10, 15), (1, 15, 25)]),
        config=_config(),
    )

    effective = build_effective_hypotension_episodes(results)

    assert effective["raw_hypotension_state"].to_list() == [1, 0, 1]
    assert effective["hypotension_episode_retained_flag"].to_list() == [1, 0, 1]
    assert effective["effective_hypotension_flag"].to_list() == [1, 0, 1]


def test_unknown_gap_remains_unknown_after_retained_bridge() -> None:
    results = run_episode_filter(
        _segments([(1, 0, 10), (-1, 10, 12), (1, 12, 25)]),
        config=_config(),
    )

    effective = build_effective_hypotension_episodes(results)

    assert effective["raw_hypotension_state"].to_list() == [1, -1, 1]
    assert effective["effective_hypotension_flag"].to_list() == [1, None, 1]


def test_short_positive_episode_becomes_effective_negative() -> None:
    results = run_episode_filter(
        _segments([(1, 0, 10), (0, 10, 30)]),
        config=_config(),
    )

    effective = build_effective_hypotension_episodes(results)

    assert results["filtered"].is_empty()
    assert effective["hypotension_episode_retained_flag"].to_list() == [0, 0]
    assert effective["effective_hypotension_flag"].to_list() == [0, 0]


def test_exact_minimum_positive_duration_is_retained() -> None:
    results = run_episode_filter(
        _segments([(1, 0, 20)]),
        config=_config(),
    )

    effective = build_effective_hypotension_episodes(results)

    assert effective["effective_hypotension_flag"].to_list() == [1]


def test_attachment_uses_half_open_intervals_and_clears_final_event() -> None:
    results = run_episode_filter(
        _segments([(1, 0, 10), (0, 10, 15), (1, 15, 25)]),
        config=_config(),
    )
    effective = build_effective_hypotension_episodes(results)
    timeline = pl.DataFrame(
        {
            "EncounterEpicCsn": [1, 1, 1, 1],
            "Event_DateTime": [
                START + timedelta(minutes=5),
                START + timedelta(minutes=12),
                START + timedelta(minutes=20),
                START + timedelta(minutes=25),
            ],
            "existing": ["positive", "negative-gap", "positive", "final"],
        }
    )

    attached = attach_effective_hypotension(timeline, effective)

    assert attached["effective_hypotension_flag"].to_list() == [1, 0, 1, 0]
    assert attached["raw_hypotension_state"].to_list() == [1, 0, 1, None]
    assert attached["existing"].to_list() == timeline["existing"].to_list()
