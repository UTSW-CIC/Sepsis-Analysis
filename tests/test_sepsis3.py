from datetime import datetime, timedelta

import polars as pl

from src_strategy.configs.severitysepsis import SeveritySepsisConfig
from src_strategy.events.sepsis import (
    build_sepsis3_associations,
    build_sepsis3_encounter_summary,
)


START = datetime(2026, 1, 3)


def _sepsis2(
    *,
    organ_start_hours: float = 10,
    organ_end_hours: float = 30,
) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "EncounterEpicCsn": [1],
            "infection_anchor_id": [1],
            "criterion": ["iv_dt"],
            "infect_dt": [START],
            "suspicion_infection_type": ["IV+Culture"],
            "organ_episode_id": [1],
            "organ_episode_start": [
                START + timedelta(hours=organ_start_hours)
            ],
            "organ_episode_end": [
                START + timedelta(hours=organ_end_hours)
            ],
            "sepsis_2_flag": [1],
            "sepsis_2_earliest_evidence_dt": [START],
            "sepsis_2_dt": [
                max(START, START + timedelta(hours=organ_start_hours))
            ],
        },
        schema_overrides={"sepsis_2_flag": pl.Int8},
    )


def _shock_episodes(
    rows: list[tuple[int, float, float]],
) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "EncounterEpicCsn": [1] * len(rows),
            "shock_episode_id": [row[0] for row in rows],
            "shock_episode_state": [1] * len(rows),
            "shock_episode_start": [
                START + timedelta(hours=row[1]) for row in rows
            ],
            "shock_episode_end": [
                START + timedelta(hours=row[2]) for row in rows
            ],
            "shock_episode_duration_minutes": [
                (row[2] - row[1]) * 60 for row in rows
            ],
            "lactate4_flag": [1] * len(rows),
        },
        schema_overrides={
            "EncounterEpicCsn": pl.Int64,
            "shock_episode_id": pl.Int64,
            "shock_episode_state": pl.Int8,
            "shock_episode_start": pl.Datetime,
            "shock_episode_end": pl.Datetime,
            "shock_episode_duration_minutes": pl.Float64,
            "lactate4_flag": pl.Int8,
        },
    )


def _shock_points(times: list[float]) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "EncounterEpicCsn": [1] * len(times),
            "shock_point_id": list(range(1, len(times) + 1)),
            "shock_point_time": [
                START + timedelta(hours=value) for value in times
            ],
            "shock_point_type": ["vasopressor_administration"] * len(times),
            "qualifying_vasopressor_dose_count": [1] * len(times),
            "qualifying_vasopressor_groupers": [
                ["Norepinephrine"] for _ in times
            ],
        },
        schema_overrides={
            "EncounterEpicCsn": pl.Int64,
            "shock_point_id": pl.Int64,
            "shock_point_time": pl.Datetime,
            "shock_point_type": pl.String,
            "qualifying_vasopressor_dose_count": pl.Int64,
            "qualifying_vasopressor_groupers": pl.List(pl.String),
        },
    )


def test_interval_shock_must_overlap_organ_and_infection_window() -> None:
    associations = build_sepsis3_associations(
        _sepsis2(),
        _shock_episodes([(1, 20, 25), (2, 30, 35)]),
        _shock_points([]),
    )

    assert associations.height == 1
    assert associations["shock_episode_id"].to_list() == [1]
    assert associations["sepsis_3_dt"].to_list() == [
        START + timedelta(hours=20)
    ]
    assert associations["sepsis_3_earliest_evidence_dt"].to_list() == [START]


def test_interval_touching_window_end_is_excluded() -> None:
    associations = build_sepsis3_associations(
        _sepsis2(organ_start_hours=40, organ_end_hours=70),
        _shock_episodes([(1, 48, 55)]),
        _shock_points([]),
    )

    assert associations.is_empty()


def test_vasopressor_point_must_be_inside_both_half_open_intervals() -> None:
    associations = build_sepsis3_associations(
        _sepsis2(),
        _shock_episodes([]),
        _shock_points([20, 30, 48]),
    )

    assert associations.height == 1
    assert associations["shock_point_time"].to_list() == [
        START + timedelta(hours=20)
    ]
    assert associations["shock_evidence_type"].to_list() == [
        "vasopressor_administration"
    ]


def test_point_at_backward_window_boundary_qualifies_when_organ_is_active() -> None:
    associations = build_sepsis3_associations(
        _sepsis2(organ_start_hours=-50, organ_end_hours=-40),
        _shock_episodes([]),
        _shock_points([-48]),
    )

    assert associations.height == 1
    assert associations["sepsis_3_dt"].to_list() == [START]
    assert associations["sepsis_3_earliest_evidence_dt"].to_list() == [
        START + timedelta(hours=-50)
    ]


def test_sepsis3_summary_preserves_negative_encounters_and_counts_evidence() -> None:
    associations = build_sepsis3_associations(
        _sepsis2(),
        _shock_episodes([(1, 20, 25)]),
        _shock_points([20]),
    )
    encounters = pl.DataFrame({"EncounterEpicCsn": [1, 2]})

    summary = build_sepsis3_encounter_summary(encounters, associations)

    assert summary["sepsis_3_flag"].to_list() == [1, 0]
    assert summary["sepsis_3_association_count"].to_list() == [2, 0]
    assert summary["sepsis_3_anchor_count"].to_list() == [1, 0]
    assert summary["sepsis_3_organ_episode_count"].to_list() == [1, 0]
    assert summary["sepsis_3_shock_evidence_count"].to_list() == [2, 0]
