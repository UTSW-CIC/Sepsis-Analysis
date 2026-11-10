from datetime import datetime, timedelta

import polars as pl

from src_strategy.events.sepsis import (
    build_sepsis3_associations,
    build_sepsis3_encounter_summary,
)


START = datetime(2026, 1, 3)


def _anchors() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "EncounterEpicCsn": [1],
            "infection_anchor_id": [1],
            "infection_episode_id": [10],
            "criterion": ["iv_dt"],
            "infect_dt": [START],
            "criterion_met_dt": [START + timedelta(hours=1)],
            "suspicion_infection_type": ["IV+Culture"],
        }
    )


def _sepsis2(hours: list[float]) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "EncounterEpicCsn": [1] * len(hours),
            "infection_anchor_id": [1] * len(hours),
            "criterion": ["iv_dt"] * len(hours),
            "infect_dt": [START] * len(hours),
            "criterion_met_dt": [START + timedelta(hours=1)] * len(hours),
            "suspicion_infection_type": ["IV+Culture"] * len(hours),
            "organ_episode_id": list(range(1, len(hours) + 1)),
            "sepsis_2_flag": [1] * len(hours),
            "sepsis_2_dt": [
                START + timedelta(hours=value) for value in hours
            ],
        },
        schema_overrides={
            "EncounterEpicCsn": pl.Int64,
            "infection_anchor_id": pl.Int64,
            "organ_episode_id": pl.Int64,
            "sepsis_2_flag": pl.Int8,
            "sepsis_2_dt": pl.Datetime,
        },
    )


def _hypotension(hours: list[float]) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "EncounterEpicCsn": [1] * len(hours),
            "raw_hypotension_episode_id": list(range(1, len(hours) + 1)),
            "hypotension_episode_start": [
                START + timedelta(hours=value) for value in hours
            ],
            "hypotension_episode_end": [
                START + timedelta(hours=value, minutes=30)
                for value in hours
            ],
            "effective_hypotension_flag": [1] * len(hours),
        },
        schema_overrides={
            "EncounterEpicCsn": pl.Int64,
            "raw_hypotension_episode_id": pl.Int64,
            "hypotension_episode_start": pl.Datetime,
            "hypotension_episode_end": pl.Datetime,
            "effective_hypotension_flag": pl.Int8,
        },
    )


def _lactate(hours: list[float]) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "EncounterEpicCsn": [1] * len(hours),
            "lactate_gt2_evidence_id": list(range(1, len(hours) + 1)),
            "lactate_gt2_dt": [
                START + timedelta(hours=value) for value in hours
            ],
            "lactate_gt2_value": [3.0] * len(hours),
        },
        schema_overrides={
            "EncounterEpicCsn": pl.Int64,
            "lactate_gt2_evidence_id": pl.Int64,
            "lactate_gt2_dt": pl.Datetime,
            "lactate_gt2_value": pl.Float64,
        },
    )


def _vasopressors(rows: list[tuple[float, float]]) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "EncounterEpicCsn": [1] * len(rows),
            "shock_point_id": list(range(1, len(rows) + 1)),
            "shock_point_time": [
                START + timedelta(hours=admin) for _, admin in rows
            ],
            "vasopressor_order_time": [
                START + timedelta(hours=anchor) for anchor, _ in rows
            ],
            "vasopressor_administration_time": [
                START + timedelta(hours=admin) for _, admin in rows
            ],
            "vasopressor_anchor_time": [
                START + timedelta(hours=anchor) for anchor, _ in rows
            ],
            "qualifying_vasopressor_dose_count": [1] * len(rows),
            "qualifying_vasopressor_groupers": [
                ["Norepinephrine"] for _ in rows
            ],
        },
        schema_overrides={
            "EncounterEpicCsn": pl.Int64,
            "shock_point_id": pl.Int64,
            "shock_point_time": pl.Datetime,
            "vasopressor_order_time": pl.Datetime,
            "vasopressor_administration_time": pl.Datetime,
            "vasopressor_anchor_time": pl.Datetime,
            "qualifying_vasopressor_dose_count": pl.Int64,
            "qualifying_vasopressor_groupers": pl.List(pl.String),
        },
    )


def _associations(
    *,
    sepsis2_hours: list[float] | None = None,
    hypotension_hours: list[float] | None = None,
    lactate_hours: list[float] | None = None,
    vasopressor_rows: list[tuple[float, float]] | None = None,
) -> pl.DataFrame:
    return build_sepsis3_associations(
        _anchors(),
        _sepsis2(sepsis2_hours or []),
        _hypotension(hypotension_hours or []),
        _lactate(lactate_hours or []),
        _vasopressors(vasopressor_rows or []),
    )


def test_pathway_a_requires_occurrences_but_not_temporal_overlap() -> None:
    associations = _associations(
        sepsis2_hours=[10],
        hypotension_hours=[20],
        lactate_hours=[30],
    )

    assert associations.height == 1
    assert associations["sepsis_3_pathway"].to_list() == [
        "hypotension_lactate_sepsis2"
    ]
    assert associations["sepsis_3_dt"].to_list() == [START]
    assert associations["sepsis_3_criterion_met_dt"].to_list() == [
        START + timedelta(hours=30)
    ]


def test_pathway_a_window_boundaries_are_inclusive() -> None:
    associations = _associations(
        sepsis2_hours=[-48],
        hypotension_hours=[48],
        lactate_hours=[-48],
    )

    assert associations.height == 1
    assert associations["sepsis_3_dt"].to_list() == [
        START - timedelta(hours=48)
    ]
    assert associations["sepsis_3_criterion_met_dt"].to_list() == [
        START + timedelta(hours=48)
    ]


def test_pathway_a_excludes_an_occurrence_outside_the_window() -> None:
    associations = _associations(
        sepsis2_hours=[10],
        hypotension_hours=[20],
        lactate_hours=[48.1],
    )

    assert associations.is_empty()


def test_pathway_b_is_independent_of_sepsis2_and_uses_order_anchor() -> None:
    associations = _associations(vasopressor_rows=[(-10, 20)])

    assert associations.height == 1
    assert associations["sepsis_3_pathway"].to_list() == [
        "infection_vasopressor"
    ]
    assert associations["organ_episode_id"].to_list() == [None]
    assert associations["sepsis_3_dt"].to_list() == [
        START - timedelta(hours=10)
    ]
    assert associations["sepsis_3_criterion_met_dt"].to_list() == [
        START + timedelta(hours=20)
    ]


def test_pathway_b_uses_inclusive_administration_window() -> None:
    associations = _associations(
        vasopressor_rows=[(-60, -48), (0, 48), (0, 48.1)]
    )

    assert associations.height == 2
    assert associations["vasopressor_administration_time"].to_list() == [
        START - timedelta(hours=48),
        START + timedelta(hours=48),
    ]


def test_or_composition_retains_both_pathways_and_summary_counts() -> None:
    associations = _associations(
        sepsis2_hours=[10],
        hypotension_hours=[20],
        lactate_hours=[30],
        vasopressor_rows=[(5, 15)],
    )
    encounters = pl.DataFrame({"EncounterEpicCsn": [1, 2]})

    summary = build_sepsis3_encounter_summary(encounters, associations)

    assert associations["sepsis_3_pathway"].sort().to_list() == [
        "hypotension_lactate_sepsis2",
        "infection_vasopressor",
    ]
    assert summary["sepsis_3_flag"].to_list() == [1, 0]
    assert summary["sepsis_3_criterion_met_dt"].to_list() == [
        START + timedelta(hours=15),
        None,
    ]
    assert summary["sepsis_3_association_count"].to_list() == [2, 0]
    assert summary["sepsis_3_organ_episode_count"].to_list() == [1, 0]
