from datetime import datetime, timedelta

import polars as pl

from src_strategy.configs.septicshock import (
    SepticShockConfig,
    SepticShockCriterionName,
)
from src_strategy.events.septicshock import (
    build_septic_shock_interval_episodes,
    build_septic_shock_interval_segments,
    build_septic_shock_point_evidence,
)


START = datetime(2026, 1, 1)


def test_lactate_shock_interval_ends_at_exact_six_hour_expiration() -> None:
    config = SepticShockConfig(
        selected=[SepticShockCriterionName.LACTATE_4]
    )
    source = pl.DataFrame(
        {
            "EncounterEpicCsn": [1, 1],
            "Event_DateTime": [START, START + timedelta(hours=10)],
            "last_lactate_6h": [5.0, None],
            "last_lactate_6h_source_ts": [START, None],
        },
        schema_overrides={
            "last_lactate_6h": pl.Float64,
            "last_lactate_6h_source_ts": pl.Datetime,
        },
    )

    segments = build_septic_shock_interval_segments(
        source,
        use_filtered_hypotension=False,
        config=config,
    )
    episodes = build_septic_shock_interval_episodes(
        segments,
        use_filtered_hypotension=False,
        config=config,
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
    assert episodes["shock_episode_state"].to_list() == [1, 0]
    assert episodes["lactate4_flag"].to_list() == [1, None]


def test_multiple_shock_features_restore_each_source_timestamp() -> None:
    config = SepticShockConfig(
        selected=[
            SepticShockCriterionName.SBP_90,
            SepticShockCriterionName.LACTATE_4,
        ]
    )
    source = pl.DataFrame(
        {
            "EncounterEpicCsn": [1, 1],
            "Event_DateTime": [START, START + timedelta(hours=10)],
            "last_sbp_8h": [80.0, None],
            "last_sbp_8h_source_ts": [START, None],
            "last_lactate_6h": [5.0, None],
            "last_lactate_6h_source_ts": [START, None],
        },
        schema_overrides={
            "last_sbp_8h": pl.Float64,
            "last_sbp_8h_source_ts": pl.Datetime,
            "last_lactate_6h": pl.Float64,
            "last_lactate_6h_source_ts": pl.Datetime,
        },
    )

    segments = build_septic_shock_interval_segments(
        source,
        use_filtered_hypotension=False,
        config=config,
    )

    assert segments["state"].to_list() == [1, 1, 0]
    assert segments["lactate4_flag"].to_list() == [1, None, None]
    assert segments["sbp90_flag"].to_list() == [1, 1, None]


def test_filtered_hypotension_controls_bp_shock_interval() -> None:
    config = SepticShockConfig(selected=[SepticShockCriterionName.SBP_90])
    source = pl.DataFrame(
        {
            "EncounterEpicCsn": [1, 1],
            "Event_DateTime": [START, START + timedelta(hours=10)],
            "last_sbp_8h": [80.0, None],
            "last_sbp_8h_source_ts": [START, None],
        },
        schema_overrides={
            "last_sbp_8h": pl.Float64,
            "last_sbp_8h_source_ts": pl.Datetime,
        },
    )
    effective = pl.DataFrame(
        {
            "EncounterEpicCsn": [1, 1],
            "raw_hypotension_episode_id": [1, 2],
            "raw_hypotension_state": [1, 0],
            "hypotension_episode_start": [
                START,
                START + timedelta(hours=4),
            ],
            "hypotension_episode_end": [
                START + timedelta(hours=4),
                START + timedelta(hours=10),
            ],
            "hypotension_episode_retained_flag": [1, 0],
            "effective_hypotension_flag": [1, 0],
        },
        schema_overrides={
            "raw_hypotension_state": pl.Int8,
            "hypotension_episode_retained_flag": pl.Int8,
            "effective_hypotension_flag": pl.Int8,
        },
    )

    segments = build_septic_shock_interval_segments(
        source,
        effective,
        use_filtered_hypotension=True,
        config=config,
    )

    assert segments["segment_start"].to_list() == [
        START,
        START + timedelta(hours=4),
        START + timedelta(hours=8),
    ]
    assert segments["segment_end"].to_list() == [
        START + timedelta(hours=4),
        START + timedelta(hours=8),
        START + timedelta(hours=10),
    ]
    assert segments["state"].to_list() == [1, 0, 0]
    assert segments["sbp90_flag"].to_list() == [1, 1, None]
    assert segments["effective_hypotension_flag"].to_list() == [1, 0, 0]


def test_vasopressor_points_keep_only_positive_administrations() -> None:
    config = SepticShockConfig()
    evidence = pl.DataFrame(
        {
            "EncounterEpicCsn": [1, 1, 1, 1],
            "Event_DateTime": [
                START,
                START,
                START + timedelta(hours=1),
                START + timedelta(hours=2),
            ],
            "Event_Grouper": [
                "Norepinephrine",
                "Vasopressin",
                "Norepinephrine",
                "Phenylephrine",
            ],
            "vasopressor_qualifying_dose_flag": [1, 1, 0, 0],
        },
        schema_overrides={"vasopressor_qualifying_dose_flag": pl.Int8},
    )

    points = build_septic_shock_point_evidence(evidence, config=config)

    assert points.height == 1
    assert points["shock_point_time"].to_list() == [START]
    assert points["qualifying_vasopressor_dose_count"].to_list() == [2]
    assert points["qualifying_vasopressor_groupers"].to_list() == [[
        "Norepinephrine",
        "Vasopressin",
    ]]
