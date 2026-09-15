from datetime import datetime, timedelta

import polars as pl

from src_strategy.configs.organdysfunction import (
    OrganDysfunctionConfig,
    OrganDysfunctionCriterionName,
)
from src_strategy.events.organdysfunction import (
    build_organ_dysfunction_episodes,
    build_organ_dysfunction_state_segments,
)


START = datetime(2026, 1, 1)


def _cardiovascular_input(
    rows: list[tuple[int, float | None, float | None]],
) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "EncounterEpicCsn": [1] * len(rows),
            "Event_DateTime": [
                START + timedelta(hours=row[0]) for row in rows
            ],
            "last_lactate_6h": [row[1] for row in rows],
            "last_lactate_6h_source_ts": [
                START + timedelta(hours=row[2])
                if row[2] is not None
                else None
                for row in rows
            ],
        },
        schema_overrides={
            "last_lactate_6h": pl.Float64,
            "last_lactate_6h_source_ts": pl.Datetime,
        },
    )


def _cardiovascular_config() -> OrganDysfunctionConfig:
    return OrganDysfunctionConfig(
        selected=[OrganDysfunctionCriterionName.CARDIOVASCULAR]
    )


def test_organ_state_expires_at_exact_feature_validity_boundary() -> None:
    segments = build_organ_dysfunction_state_segments(
        _cardiovascular_input([(0, 3.0, 0), (10, None, None)]),
        config=_cardiovascular_config(),
    )

    assert segments["segment_start"].to_list() == [
        START,
        START + timedelta(hours=6),
    ]
    assert segments["segment_end"].to_list() == [
        START + timedelta(hours=6),
        START + timedelta(hours=10),
    ]
    assert segments["state"].to_list() == [1, 0]


def test_new_negative_measurement_ends_organ_state_before_expiration() -> None:
    segments = build_organ_dysfunction_state_segments(
        _cardiovascular_input(
            [(0, 3.0, 0), (4, 2.0, 4), (10, None, None)]
        ),
        config=_cardiovascular_config(),
    )

    positive = segments.filter(pl.col("state") == 1)
    assert positive["segment_start"].to_list() == [START]
    assert positive["segment_end"].to_list() == [
        START + timedelta(hours=4)
    ]


def test_organ_episodes_retain_contributing_organ_flags() -> None:
    config = _cardiovascular_config()
    segments = build_organ_dysfunction_state_segments(
        _cardiovascular_input([(0, 3.0, 0), (10, None, None)]),
        config=config,
    )

    episodes = build_organ_dysfunction_episodes(segments, config=config)

    assert episodes["organ_episode_state"].to_list() == [1, 0]
    assert episodes["cardiovascular_failure_flag"].to_list() == [1, None]
    assert episodes["max_organ_dysfunction_total"].to_list() == [1, 0]


def test_pulmonary_transitions_contribute_exact_organ_boundaries() -> None:
    config = OrganDysfunctionConfig(
        selected=[OrganDysfunctionCriterionName.PULMONARY]
    )
    organ_input = pl.DataFrame(
        {
            "EncounterEpicCsn": [1, 1],
            "Event_DateTime": [START, START + timedelta(hours=4)],
        }
    )
    pulmonary_timeline = pl.DataFrame(
        {
            "EncounterEpicCsn": [1, 1, 1, 1],
            "pulmonary_state_time": [
                START,
                START + timedelta(hours=1),
                START + timedelta(hours=3),
                START + timedelta(hours=4),
            ],
            "pulmonary_dysfunction_flag": [None, 1, 0, 0],
        },
        schema_overrides={"pulmonary_dysfunction_flag": pl.Int8},
    )

    segments = build_organ_dysfunction_state_segments(
        organ_input,
        pulmonary_timeline,
        config=config,
    )

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
    assert segments["state"].to_list() == [0, 1, 0]

