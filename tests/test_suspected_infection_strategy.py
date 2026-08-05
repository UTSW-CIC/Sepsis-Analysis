from datetime import datetime, timedelta

import polars as pl

from src_strategy.configs.suspected_infection import (
    SuspectedInfectionConfig,
    SuspectedInfectionCriterionName,
)
from src_strategy.events.suspected_infection import (
    build_suspected_infection_pipeline,
)


BASE_TIME = datetime(2026, 1, 1, 12)


def make_event_frame(rows: list[dict]) -> pl.DataFrame:
    columns = {
        "EncounterEpicCsn": [],
        "Event_DateTime": [],
        "Type": [],
        "Event_Grouper": [],
        "Event_Name": [],
        "Value": [],
    }
    for row in rows:
        for column in columns:
            columns[column].append(row.get(column))
    return pl.DataFrame(columns)


def event(
    encounter: int,
    event_time: datetime,
    *,
    event_type: str = "Other",
    grouper: str = "Other",
    name: str = "event",
    value: str | None = None,
) -> dict:
    return {
        "EncounterEpicCsn": encounter,
        "Event_DateTime": event_time,
        "Type": event_type,
        "Event_Grouper": grouper,
        "Event_Name": name,
        "Value": value,
    }


def test_antibiotic_type_uses_prefix_and_inclusive_timing_boundaries() -> None:
    rows = []
    qualifying = {
        1: ("IV Antibiotics - Single", BASE_TIME - timedelta(hours=72)),
        2: ("IV Antibiotics - First", BASE_TIME + timedelta(hours=24)),
        3: ("IV Antibiotics - Last", BASE_TIME),
        4: ("IV Antibiotics", BASE_TIME),
    }
    for encounter, (antibiotic_type, culture_time) in qualifying.items():
        rows.extend(
            [
                event(
                    encounter,
                    BASE_TIME,
                    event_type=antibiotic_type,
                    name="antibiotic",
                ),
                event(
                    encounter,
                    culture_time,
                    grouper="Blood Culture Order",
                    name="culture",
                ),
            ]
        )

    rows.extend(
        [
            event(5, BASE_TIME, event_type="Oral Antibiotics", name="oral"),
            event(5, BASE_TIME, grouper="Blood Culture Order", name="culture"),
            event(6, BASE_TIME, event_type="IV Antibiotics - Single", name="iv"),
            event(
                6,
                BASE_TIME - timedelta(hours=72, minutes=1),
                grouper="Blood Culture Order",
                name="too early",
            ),
            event(7, BASE_TIME, event_type="IV Antibiotics - Single", name="iv"),
            event(
                7,
                BASE_TIME + timedelta(hours=24, minutes=1),
                grouper="Blood Culture Order",
                name="too late",
            ),
        ]
    )
    config = SuspectedInfectionConfig(
        selected=[SuspectedInfectionCriterionName.ANTIBIOTIC_CULTURE]
    )

    result = build_suspected_infection_pipeline(config).process(
        make_event_frame(rows)
    )

    assert result["EncounterEpicCsn"].unique().sort().to_list() == [1, 2, 3, 4]
    assert result.height == 8
    assert set(result["criterion"].to_list()) == {"iv_dt", "culture_dt"}
    assert result["suspicion_infection_type"].unique().to_list() == [
        "IV+Culture"
    ]


def test_lactate_requires_two_distinct_culture_orders_within_six_hours() -> None:
    rows = [
        event(10, BASE_TIME, grouper="Lactate", name="lactate"),
        event(
            10,
            BASE_TIME - timedelta(hours=6),
            grouper="Blood Culture Order",
            name="culture A",
        ),
        event(
            10,
            BASE_TIME + timedelta(hours=6),
            grouper="Blood Culture Order",
            name="culture B",
        ),
        event(11, BASE_TIME, grouper="Lactate", name="lactate"),
        event(11, BASE_TIME, grouper="Blood Culture Order", name="only culture"),
        event(12, BASE_TIME, grouper="Lactate", name="lactate"),
        event(12, BASE_TIME, grouper="Blood Culture Order", name="duplicate"),
        event(12, BASE_TIME, grouper="Blood Culture Order", name="duplicate"),
        event(13, BASE_TIME, grouper="Lactate", name="lactate"),
        event(13, BASE_TIME, grouper="Blood Culture Order", name="culture A"),
        event(13, BASE_TIME, grouper="Blood Culture Order", name="culture B"),
        event(14, BASE_TIME, grouper="Lactate", name="lactate"),
        event(14, BASE_TIME, grouper="Blood Culture Order", name="culture A"),
        event(
            14,
            BASE_TIME + timedelta(hours=6, minutes=1),
            grouper="Blood Culture Order",
            name="outside window",
        ),
    ]
    config = SuspectedInfectionConfig(
        selected=[SuspectedInfectionCriterionName.LACTATE_CULTURE]
    )

    result = build_suspected_infection_pipeline(config).process(
        make_event_frame(rows)
    )

    assert result["EncounterEpicCsn"].unique().sort().to_list() == [10, 13]
    assert result.filter(pl.col("EncounterEpicCsn") == 10).height == 3
    assert result.filter(pl.col("EncounterEpicCsn") == 13).height == 3
    assert (
        result.filter(
            (pl.col("EncounterEpicCsn") == 13)
            & (pl.col("criterion") == "culture_dt")
        ).height
        == 2
    )


def test_code_sepsis_and_yes_flowsheet_emit_old_long_frame_format() -> None:
    rows = [
        event(20, BASE_TIME, grouper="Code Sepsis Page", name="page"),
        event(
            21,
            BASE_TIME + timedelta(minutes=1),
            grouper="Suspected Infection",
            name="flowsheet",
            value="Yes",
        ),
        event(
            22,
            BASE_TIME + timedelta(minutes=2),
            grouper="Suspected Infection",
            name="flowsheet",
            value="No",
        ),
    ]

    result = build_suspected_infection_pipeline().process(
        make_event_frame(rows)
    )

    assert result.columns == [
        "EncounterEpicCsn",
        "criterion",
        "infect_dt",
        "suspicion_infection_type",
    ]
    assert result["EncounterEpicCsn"].to_list() == [20, 21]
    assert result["criterion"].to_list() == [
        "first_ev_time_codesepsis",
        "first_ev_time_flowsheet",
    ]
    assert result["suspicion_infection_type"].to_list() == [
        "CODE_SEPSIS_ORDER",
        "FLOWSHEET_SUSPECTED_INFECTION",
    ]


def test_antibiotic_pair_reduction_keeps_earliest_episode_per_encounter() -> None:
    rows = [
        event(
            30,
            BASE_TIME,
            event_type="IV Antibiotics - First",
            name="first antibiotic",
        ),
        event(
            30,
            BASE_TIME + timedelta(hours=1),
            grouper="Blood Culture Order",
            name="first culture",
        ),
        event(
            30,
            BASE_TIME + timedelta(days=1),
            event_type="IV Antibiotics - Last",
            name="later antibiotic",
        ),
        event(
            30,
            BASE_TIME + timedelta(days=1, hours=1),
            grouper="Blood Culture Order",
            name="later culture",
        ),
    ]
    config = SuspectedInfectionConfig(
        selected=[SuspectedInfectionCriterionName.ANTIBIOTIC_CULTURE]
    )

    result = build_suspected_infection_pipeline(config).process(
        make_event_frame(rows)
    )

    assert result.height == 2
    assert result["infect_dt"].to_list() == [
        BASE_TIME,
        BASE_TIME + timedelta(hours=1),
    ]


def test_registry_selection_limits_output_to_selected_criterion() -> None:
    rows = [
        event(40, BASE_TIME, grouper="Code Sepsis Page", name="page"),
        event(
            40,
            BASE_TIME,
            grouper="Suspected Infection",
            name="flowsheet",
            value="Yes",
        ),
    ]
    config = SuspectedInfectionConfig(
        selected=[SuspectedInfectionCriterionName.CODE_SEPSIS]
    )

    result = build_suspected_infection_pipeline(config).process(
        make_event_frame(rows)
    )

    assert result.height == 1
    assert result["suspicion_infection_type"].to_list() == [
        "CODE_SEPSIS_ORDER"
    ]
