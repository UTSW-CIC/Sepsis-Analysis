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
    source_times = [
        START + timedelta(hours=row[2]) if row[2] is not None else None
        for row in rows
    ]
    return pl.DataFrame(
        {
            "EncounterEpicCsn": [1] * len(rows),
            "Event_DateTime": [
                START + timedelta(hours=row[0]) for row in rows
            ],
            "last_lactate_6h": [row[1] for row in rows],
            "last_lactate_6h_source_ts": source_times,
            "last_lactate_6h_source_type": [
                "Lab Results" if value is not None else None
                for value in source_times
            ],
            "last_lactate_6h_source_event_id": [
                100 + index if value is not None else None
                for index, value in enumerate(source_times)
            ],
            "last_lactate_6h_source_event_name": [
                "LACTATE" if value is not None else None
                for value in source_times
            ],
        },
        schema_overrides={
            "last_lactate_6h": pl.Float64,
            "last_lactate_6h_source_ts": pl.Datetime,
            "last_lactate_6h_source_event_id": pl.Int64,
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
    assert episodes["last_lactate_6h_source_evidence"].to_list()[0] == [
        {
            "value": 3.0,
            "result_dt": START,
            "type": "Lab Results",
            "event_id": 100,
            "event_name": "LACTATE",
        }
    ]
    assert episodes["last_lactate_6h_source_evidence"].to_list()[1] == []


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
            "pulmonary_transition_time": [
                None,
                START + timedelta(hours=1),
                START + timedelta(hours=3),
                START + timedelta(hours=3),
            ],
            "pulmonary_transition_type": [
                None,
                ["vent_onoff_start"],
                ["vent_onoff_termination"],
                ["vent_onoff_termination"],
            ],
            "pulmonary_transition_event_ids": [
                None,
                [101],
                [102],
                [102],
            ],
        },
        schema_overrides={
            "pulmonary_dysfunction_flag": pl.Int8,
            "pulmonary_transition_time": pl.Datetime,
            "pulmonary_transition_type": pl.List(pl.String),
            "pulmonary_transition_event_ids": pl.List(pl.Int64),
        },
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

    episodes = build_organ_dysfunction_episodes(segments, config=config)
    positive = episodes.filter(pl.col("organ_episode_state") == 1)
    assert positive["pulmonary_source_evidence"].to_list() == [
        [
            {
                "transition_dt": START + timedelta(hours=1),
                "transition_type": ["vent_onoff_start"],
                "event_ids": [101],
            }
        ]
    ]


def test_missing_aptt_remains_auditable_without_crashing_episodes() -> None:
    end = START + timedelta(hours=2)
    data: dict[str, list] = {
        "EncounterEpicCsn": [1, 1],
        "Event_DateTime": [START, end],
        "Baseline_Platelets": [None, None],
    }
    feature_values = {
        "last_platelets_24h": (50.0, 101, "PLATELETS"),
        "last_inr_12h": (None, None, None),
        "last_aptt_24h": (None, None, None),
    }
    for feature, (value, event_id, event_name) in feature_values.items():
        has_evidence = value is not None
        data[feature] = [value, value]
        data[f"{feature}_source_ts"] = [
            START if has_evidence else None,
            START if has_evidence else None,
        ]
        data[f"{feature}_source_type"] = [
            "Lab Results" if has_evidence else None,
            "Lab Results" if has_evidence else None,
        ]
        data[f"{feature}_source_event_id"] = [event_id, event_id]
        data[f"{feature}_source_event_name"] = [event_name, event_name]

    source = pl.DataFrame(
        data,
        schema_overrides={
            "Baseline_Platelets": pl.Float64,
            "last_inr_12h": pl.Float64,
            "last_aptt_24h": pl.Float64,
            "last_inr_12h_source_ts": pl.Datetime,
            "last_aptt_24h_source_ts": pl.Datetime,
            "last_inr_12h_source_event_id": pl.Int64,
            "last_aptt_24h_source_event_id": pl.Int64,
        },
    )
    config = OrganDysfunctionConfig(
        selected=[OrganDysfunctionCriterionName.COAGULATION]
    )

    segments = build_organ_dysfunction_state_segments(source, config=config)
    episodes = build_organ_dysfunction_episodes(segments, config=config)

    positive = episodes.filter(pl.col("organ_episode_state") == 1)
    assert positive.height == 1
    assert positive["last_aptt_24h_source_evidence"].to_list() == [[]]
