from datetime import datetime, timedelta

import polars as pl
import pytest

from src_strategy.configs.sirscalculator import sirs_config
from src_strategy.configs.shortdurationfilter import (
    sirs_episode_filter_config,
)
from src_strategy.events.sirs import build_sirs_state_segments


SIRS_FEATURES = [
    sirs_config.temp_feature_col.value,
    sirs_config.hr_feature_col.value,
    sirs_config.resp_feature_col.value,
    sirs_config.wbc_feature_col.value,
]


def test_sirs_episode_filter_is_disabled_by_default() -> None:
    assert sirs_episode_filter_config.enabled is False
    assert sirs_episode_filter_config.bridge_unknown is True
    assert sirs_episode_filter_config.negative_gap_minutes == 20.0
    assert sirs_episode_filter_config.minimum_positive_minutes == 20.0


def _sirs_frame(
    rows: list[tuple[int, int, tuple[float | None, ...], tuple[int | None, ...]]],
) -> pl.DataFrame:
    start = datetime(2026, 1, 1)
    data: dict[str, list[object]] = {
        "EncounterEpicCsn": [row[0] for row in rows],
        "Event_DateTime": [
            start + timedelta(hours=row[1]) for row in rows
        ],
    }
    for index, feature in enumerate(SIRS_FEATURES):
        data[feature] = [row[2][index] for row in rows]
        data[f"{feature}_source_ts"] = [
            start + timedelta(hours=row[3][index])
            if row[3][index] is not None
            else None
            for row in rows
        ]
    return pl.DataFrame(data)


def test_sirs_segments_change_at_feature_expiration() -> None:
    df_sirs = _sirs_frame(
        [
            (1, 0, (102.0, 100.0, None, None), (0, 0, None, None)),
            (1, 10, (None, None, None, None), (None, None, None, None)),
        ]
    )

    result = build_sirs_state_segments(df_sirs)

    assert result["state"].to_list() == [1, 0]
    assert result["sirs_score"].to_list() == [2, 0]
    assert result["segment_start"].to_list() == [
        datetime(2026, 1, 1),
        datetime(2026, 1, 1, 8),
    ]
    assert result["segment_end"].to_list() == [
        datetime(2026, 1, 1, 8),
        datetime(2026, 1, 1, 10),
    ]


def test_state_starting_at_final_event_is_omitted() -> None:
    df_sirs = _sirs_frame(
        [
            (1, 0, (98.6, 80.0, 16.0, 8.0), (0, 0, 0, 0)),
            (1, 5, (102.0, 100.0, 16.0, 8.0), (5, 5, 0, 0)),
        ]
    )

    result = build_sirs_state_segments(df_sirs)

    assert result.select("state", "segment_start", "segment_end").rows() == [
        (0, datetime(2026, 1, 1), datetime(2026, 1, 1, 5))
    ]


def test_one_row_encounter_has_no_positive_duration_segment() -> None:
    df_sirs = _sirs_frame(
        [(1, 0, (102.0, 100.0, None, None), (0, 0, None, None))]
    )

    result = build_sirs_state_segments(df_sirs)

    assert result.is_empty()


def test_sirs_segment_reconstruction_is_encounter_local() -> None:
    df_sirs = _sirs_frame(
        [
            (2, 6, (102.0, 100.0, None, None), (0, 0, None, None)),
            (1, 0, (102.0, 100.0, None, None), (0, 0, None, None)),
            (2, 0, (102.0, 100.0, None, None), (0, 0, None, None)),
            (1, 10, (None, None, None, None), (None, None, None, None)),
        ]
    )

    result = build_sirs_state_segments(df_sirs)

    assert result.select(
        "EncounterEpicCsn", "state", "segment_start", "segment_end"
    ).rows() == [
        (
            1,
            1,
            datetime(2026, 1, 1),
            datetime(2026, 1, 1, 8),
        ),
        (
            1,
            0,
            datetime(2026, 1, 1, 8),
            datetime(2026, 1, 1, 10),
        ),
        (
            2,
            1,
            datetime(2026, 1, 1),
            datetime(2026, 1, 1, 6),
        ),
    ]


def test_sirs_adapter_rejects_duplicate_backbone_keys() -> None:
    df_sirs = _sirs_frame(
        [
            (1, 0, (102.0, 100.0, None, None), (0, 0, None, None)),
            (1, 0, (102.0, 100.0, None, None), (0, 0, None, None)),
        ]
    )

    with pytest.raises(ValueError, match="duplicate keys"):
        build_sirs_state_segments(df_sirs)
