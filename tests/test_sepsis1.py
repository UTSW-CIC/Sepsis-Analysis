from datetime import datetime, timedelta

import polars as pl
import pytest
from pydantic import ValidationError

from src_strategy.configs.severitysepsis import SeveritySepsisConfig
from src_strategy.configs.shortdurationfilter import EpisodeFilterConfig
from src_strategy.events.episode_filter import (
    build_state_episodes,
    run_episode_filter,
)
from src_strategy.events.sepsis import (
    build_infection_anchors,
    build_sepsis1_associations,
    build_sepsis1_encounter_summary,
)
from src_strategy.events.sirs import build_effective_sirs_episodes


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


def _filter_config() -> EpisodeFilterConfig:
    return EpisodeFilterConfig(
        status_name="sirs",
        bridge_unknown=True,
        negative_gap_minutes=20,
        minimum_positive_minutes=20,
    )


def test_effective_sirs_reuses_retained_source_episode_lineage() -> None:
    results = run_episode_filter(
        _segments([(1, 0, 10), (0, 10, 15), (1, 15, 25)]),
        config=_filter_config(),
    )

    effective = build_effective_sirs_episodes(
        results,
        filter_enabled=True,
        config=SeveritySepsisConfig(),
    )

    assert effective["raw_sirs_state"].to_list() == [1, 0, 1]
    assert effective["sirs_episode_retained_flag"].to_list() == [1, 0, 1]
    assert effective["effective_sirs_positive_flag"].to_list() == [1, 0, 1]
    assert effective["sirs_filter_applied"].to_list() == [True, True, True]


def test_disabled_sirs_filter_retains_short_raw_positive_episode() -> None:
    raw = build_state_episodes(_segments([(1, 0, 10), (0, 10, 30)]))

    effective = build_effective_sirs_episodes(
        {"raw": raw},
        filter_enabled=False,
        config=SeveritySepsisConfig(),
    )

    assert effective["sirs_episode_retained_flag"].to_list() == [1, 0]
    assert effective["effective_sirs_positive_flag"].to_list() == [1, 0]
    assert effective["sirs_filter_applied"].to_list() == [False, False]


def _infection_frame() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "EncounterEpicCsn": [1, 1, 1, 1, 2],
            "criterion": [
                "iv_dt",
                "iv_dt",
                "culture_dt",
                "first_ev_time_codesepsis",
                "iv_dt",
            ],
            "infect_dt": [
                START,
                START,
                START + timedelta(hours=10),
                START,
                START,
            ],
            "suspicion_infection_type": [
                "IV+Culture",
                "IV+Culture",
                "IV+Culture",
                "CODE_SEPSIS_ORDER",
                "IV+Culture",
            ],
        }
    )


def _effective_sirs_frame() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "EncounterEpicCsn": [1, 1, 2],
            "sirs_episode_id": [1, 2, 1],
            "raw_sirs_state": [1, 1, 1],
            "sirs_episode_start": [
                START + timedelta(hours=23),
                START + timedelta(hours=34),
                START + timedelta(hours=30),
            ],
            "sirs_episode_end": [
                START + timedelta(hours=25),
                START + timedelta(hours=35),
                START + timedelta(hours=31),
            ],
            "sirs_episode_duration_minutes": [120.0, 60.0, 60.0],
            "sirs_episode_retained_flag": [1, 1, 1],
            "effective_sirs_positive_flag": [1, 1, 1],
            "sirs_filter_applied": [True, True, True],
        },
        schema_overrides={
            "raw_sirs_state": pl.Int8,
            "sirs_episode_retained_flag": pl.Int8,
            "effective_sirs_positive_flag": pl.Int8,
        },
    )


def test_infection_anchors_deduplicate_only_identical_rows() -> None:
    anchors = build_infection_anchors(_infection_frame())

    assert anchors.height == 4
    assert anchors.filter(pl.col("EncounterEpicCsn") == 1).height == 3
    assert anchors.filter(
        (pl.col("EncounterEpicCsn") == 1)
        & (pl.col("infect_dt") == START)
    ).height == 2


def test_sepsis1_uses_independent_24_hour_anchors_and_later_onset() -> None:
    config = SeveritySepsisConfig()
    anchors = build_infection_anchors(_infection_frame(), config=config)

    associations = build_sepsis1_associations(
        anchors,
        _effective_sirs_frame(),
        use_filtered_sirs=True,
        config=config,
    )

    encounter_one = associations.filter(pl.col("EncounterEpicCsn") == 1)
    assert encounter_one.height == 3
    assert encounter_one["sirs_episode_id"].unique().to_list() == [1]
    assert encounter_one["sepsis_1_dt"].to_list() == [
        START + timedelta(hours=23),
        START + timedelta(hours=23),
        START + timedelta(hours=23),
    ]
    assert encounter_one["sepsis_1_earliest_evidence_dt"].to_list() == [
        START,
        START,
        START + timedelta(hours=10),
    ]
    assert associations.filter(pl.col("EncounterEpicCsn") == 2).is_empty()


def test_sepsis1_onset_is_infection_time_when_sirs_was_established_first() -> None:
    config = SeveritySepsisConfig()
    infection = _infection_frame().filter(
        (pl.col("EncounterEpicCsn") == 1)
        & (pl.col("criterion") == "culture_dt")
    )
    sirs = _effective_sirs_frame().filter(
        (pl.col("EncounterEpicCsn") == 1)
        & (pl.col("sirs_episode_id") == 1)
    ).with_columns(
        pl.lit(START).alias("sirs_episode_start"),
        pl.lit(START + timedelta(hours=1)).alias("sirs_episode_end"),
    )

    associations = build_sepsis1_associations(
        build_infection_anchors(infection, config=config),
        sirs,
        use_filtered_sirs=True,
        config=config,
    )

    assert associations["sepsis_1_earliest_evidence_dt"].to_list() == [START]
    assert associations["sepsis_1_dt"].to_list() == [
        START + timedelta(hours=10)
    ]


def test_sepsis1_episode_touching_window_boundary_does_not_overlap() -> None:
    config = SeveritySepsisConfig()
    anchors = build_infection_anchors(
        _infection_frame().filter(
            (pl.col("EncounterEpicCsn") == 1)
            & (pl.col("criterion") == "culture_dt")
        ),
        config=config,
    )

    associations = build_sepsis1_associations(
        anchors,
        _effective_sirs_frame().filter(pl.col("sirs_episode_id") == 2),
        use_filtered_sirs=True,
        config=config,
    )

    assert associations.is_empty()


def test_sepsis1_summary_retains_encounters_without_sepsis() -> None:
    config = SeveritySepsisConfig()
    anchors = build_infection_anchors(_infection_frame(), config=config)
    associations = build_sepsis1_associations(
        anchors,
        _effective_sirs_frame(),
        use_filtered_sirs=True,
        config=config,
    )
    encounters = pl.DataFrame({"EncounterEpicCsn": [1, 2, 3]})

    summary = build_sepsis1_encounter_summary(
        encounters,
        associations,
        config=config,
    )

    assert summary["sepsis_1_flag"].to_list() == [1, 0, 0]
    assert summary["sepsis_1_association_count"].to_list() == [3, 0, 0]
    assert summary["sepsis_1_anchor_count"].to_list() == [3, 0, 0]
    assert summary["sepsis_1_sirs_episode_count"].to_list() == [1, 0, 0]
    assert summary["sepsis_1_dt"].to_list() == [
        START + timedelta(hours=23),
        None,
        None,
    ]


def test_sepsis1_rejects_mismatched_filter_argument() -> None:
    config = SeveritySepsisConfig()
    with pytest.raises(ValueError, match="requested filter state"):
        build_sepsis1_associations(
            build_infection_anchors(_infection_frame(), config=config),
            _effective_sirs_frame(),
            use_filtered_sirs=False,
            config=config,
        )


def test_sepsis_windows_must_be_non_negative() -> None:
    with pytest.raises(ValidationError, match="finite and non-negative"):
        SeveritySepsisConfig(infection_2_sirs_forward_hrs=-1)
