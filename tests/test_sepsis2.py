from datetime import datetime, timedelta

import polars as pl

from src_strategy.configs.severitysepsis import SeveritySepsisConfig
from src_strategy.events.sepsis import (
    build_infection_anchors,
    build_sepsis2_associations,
    build_sepsis2_encounter_summary,
    select_first_organ_episodes_by_type,
)


START = datetime(2026, 1, 1)


def _infection_frame() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "EncounterEpicCsn": [1, 1, 1, 2],
            "criterion": ["iv_dt", "culture_dt", "culture_dt", "iv_dt"],
            "infect_dt": [
                START,
                START + timedelta(hours=30),
                START + timedelta(hours=30),
                START,
            ],
            "suspicion_infection_type": ["IV+Culture"] * 4,
        }
    )


def _organ_episodes() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "EncounterEpicCsn": [1, 1, 2],
            "organ_episode_id": [1, 2, 1],
            "organ_episode_state": [1, 1, 1],
            "organ_episode_start": [
                START + timedelta(hours=20),
                START + timedelta(hours=80),
                START + timedelta(hours=60),
            ],
            "organ_episode_end": [
                START + timedelta(hours=24),
                START + timedelta(hours=82),
                START + timedelta(hours=61),
            ],
            "organ_episode_duration_minutes": [240.0, 120.0, 60.0],
            "max_organ_dysfunction_total": [2, 1, 1],
            "cardiovascular_failure_flag": [1, 0, 1],
            "pulmonary_failure_flag": [0, 1, 0],
            "renal_failure_flag": [1, 0, 0],
            "hepatic_failure_flag": [0, 0, 0],
            "coagulation_failure_flag": [0, 0, 0],
            "neurological_failure_flag": [0, 0, 0],
        },
        schema_overrides={"organ_episode_state": pl.Int8},
    )


def test_sepsis2_uses_every_distinct_anchor_and_configured_48_hour_window() -> None:
    config = SeveritySepsisConfig()
    anchors = build_infection_anchors(_infection_frame(), config=config)

    associations = build_sepsis2_associations(
        anchors,
        _organ_episodes(),
        config=config,
    )

    encounter_one = associations.filter(pl.col("EncounterEpicCsn") == 1)
    assert anchors.height == 3
    assert encounter_one.height == 2
    assert encounter_one["infection_anchor_id"].n_unique() == 2
    assert encounter_one["organ_episode_id"].unique().to_list() == [1]
    assert associations.filter(pl.col("EncounterEpicCsn") == 2).is_empty()


def test_sepsis2_selects_only_earliest_episode_for_each_organ_type() -> None:
    config = SeveritySepsisConfig()
    organ = pl.concat(
        [
            _organ_episodes().filter(pl.col("EncounterEpicCsn") == 1),
            _organ_episodes()
            .filter(
                (pl.col("EncounterEpicCsn") == 1)
                & (pl.col("organ_episode_id") == 1)
            )
            .with_columns(
                pl.lit(3, dtype=pl.Int64).alias("organ_episode_id"),
                pl.lit(START + timedelta(hours=40)).alias(
                    "organ_episode_start"
                ),
                pl.lit(START + timedelta(hours=44)).alias(
                    "organ_episode_end"
                ),
                pl.lit(0, dtype=pl.Int64).alias(
                    "cardiovascular_failure_flag"
                ),
            ),
        ]
    )

    selected = select_first_organ_episodes_by_type(organ, config=config)

    assert selected["organ_episode_id"].to_list() == [1, 2]
    assert selected["first_organ_dysfunction_types"].to_list() == [
        ["cardiovascular", "renal"],
        ["pulmonary"],
    ]


def test_first_organ_selection_uses_episode_id_to_break_start_ties() -> None:
    config = SeveritySepsisConfig()
    renal_episode = (
        _organ_episodes()
        .filter(
            (pl.col("EncounterEpicCsn") == 1)
            & (pl.col("organ_episode_id") == 1)
        )
        .with_columns(
            pl.lit(0, dtype=pl.Int64).alias(
                "cardiovascular_failure_flag"
            )
        )
    )
    organ = pl.concat(
        [
            renal_episode.with_columns(
                pl.lit(2, dtype=pl.Int64).alias("organ_episode_id")
            ),
            renal_episode,
        ]
    )

    selected = select_first_organ_episodes_by_type(organ, config=config)

    assert selected["organ_episode_id"].to_list() == [1]
    assert selected["first_organ_dysfunction_types"].to_list() == [
        ["renal"]
    ]


def test_later_same_organ_episode_cannot_rescue_unmatched_first_episode() -> None:
    config = SeveritySepsisConfig()
    infection = pl.DataFrame(
        {
            "EncounterEpicCsn": [1],
            "criterion": ["iv_dt"],
            "infect_dt": [START],
            "suspicion_infection_type": ["IV+Culture"],
        }
    )
    organ = pl.DataFrame(
        {
            "EncounterEpicCsn": [1, 1],
            "organ_episode_id": [1, 2],
            "organ_episode_state": [1, 1],
            "organ_episode_start": [
                START - timedelta(hours=60),
                START,
            ],
            "organ_episode_end": [
                START - timedelta(hours=59),
                START + timedelta(hours=1),
            ],
            "organ_episode_duration_minutes": [60.0, 60.0],
            "max_organ_dysfunction_total": [1, 1],
            "cardiovascular_failure_flag": [0, 0],
            "pulmonary_failure_flag": [0, 0],
            "renal_failure_flag": [1, 1],
            "hepatic_failure_flag": [0, 0],
            "coagulation_failure_flag": [0, 0],
            "neurological_failure_flag": [0, 0],
        },
        schema_overrides={"organ_episode_state": pl.Int8},
    )

    associations = build_sepsis2_associations(
        build_infection_anchors(infection, config=config),
        organ,
        config=config,
    )

    assert associations.is_empty()


def test_sepsis2_timestamp_uses_later_and_retains_earlier_evidence() -> None:
    config = SeveritySepsisConfig()
    associations = build_sepsis2_associations(
        build_infection_anchors(_infection_frame(), config=config),
        _organ_episodes(),
        config=config,
    ).sort("infect_dt")

    assert associations["sepsis_2_dt"].to_list() == [
        START + timedelta(hours=20),
        START + timedelta(hours=30),
    ]
    assert associations["sepsis_2_earliest_evidence_dt"].to_list() == [
        START,
        START + timedelta(hours=20),
    ]


def test_sepsis2_exact_window_boundary_contact_does_not_qualify() -> None:
    config = SeveritySepsisConfig()
    infection = _infection_frame().filter(
        (pl.col("EncounterEpicCsn") == 1)
        & (pl.col("criterion") == "culture_dt")
    )
    organ = (
        _organ_episodes()
        .filter(pl.col("organ_episode_id") == 2)
        .with_columns(
            pl.lit(START + timedelta(hours=78)).alias(
                "organ_episode_start"
            )
        )
    )

    associations = build_sepsis2_associations(
        build_infection_anchors(infection, config=config),
        organ,
        config=config,
    )

    assert associations.is_empty()


def test_sepsis2_summary_includes_negative_encounters_without_sirs_input() -> None:
    config = SeveritySepsisConfig()
    associations = build_sepsis2_associations(
        build_infection_anchors(_infection_frame(), config=config),
        _organ_episodes(),
        config=config,
    )
    encounters = pl.DataFrame({"EncounterEpicCsn": [1, 2, 3]})

    summary = build_sepsis2_encounter_summary(
        encounters,
        associations,
        config=config,
    )

    assert summary["sepsis_2_flag"].to_list() == [1, 0, 0]
    assert summary["sepsis_2_association_count"].to_list() == [2, 0, 0]
    assert summary["sepsis_2_anchor_count"].to_list() == [2, 0, 0]
    assert summary["sepsis_2_organ_episode_count"].to_list() == [1, 0, 0]
    assert summary["sepsis_2_dt"].to_list() == [
        START + timedelta(hours=20),
        None,
        None,
    ]
