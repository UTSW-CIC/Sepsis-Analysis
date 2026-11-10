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


def make_event_frame(events: list[tuple[int, datetime, str, str]]) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "EncounterEpicCsn": [event[0] for event in events],
            "Event_DateTime": [event[1] for event in events],
            "Event_Grouper": [event[2] for event in events],
            "Event_Name": [event[3] for event in events],
        }
    )


def test_code_sepsis_requires_one_of_the_two_exact_event_pairs() -> None:
    events = make_event_frame(
        [
            (1, BASE_TIME, "Nursing", "UTSW CODE SEPSIS PAGE"),
            (
                2,
                BASE_TIME + timedelta(minutes=1),
                "Code Sepsis Event",
                "ED Code Sepsis Page",
            ),
            (3, BASE_TIME, "Nursing", "ED Code Sepsis Page"),
            (4, BASE_TIME, "Code Sepsis Event", "UTSW CODE SEPSIS PAGE"),
            (5, BASE_TIME, "Code Sepsis Event", "another event"),
            (6, BASE_TIME, "Code Sepsis Page", "page"),
        ]
    )
    config = SuspectedInfectionConfig(
        selected=[SuspectedInfectionCriterionName.CODE_SEPSIS]
    )

    result = build_suspected_infection_pipeline(config).process(events)

    assert result["EncounterEpicCsn"].to_list() == [1, 2]
    assert result["criterion"].to_list() == [
        "first_ev_time_codesepsis",
        "first_ev_time_codesepsis",
    ]
    assert result["suspicion_infection_type"].to_list() == [
        "CODE_SEPSIS_ORDER",
        "CODE_SEPSIS_ORDER",
    ]
    assert result["infect_dt"].to_list() == [
        BASE_TIME,
        BASE_TIME + timedelta(minutes=1),
    ]
    assert result["criterion_met_dt"].to_list() == result["infect_dt"].to_list()
    assert result["evidence_dt"].to_list() == result["infect_dt"].to_list()


def test_sepsis_documentation_event_is_an_enabled_exact_pair_criterion() -> None:
    events = make_event_frame(
        [
            (
                1,
                BASE_TIME,
                "Sepsis Documentation Event",
                "Sepsis Documentation Start",
            ),
            (
                2,
                BASE_TIME,
                "Sepsis Documentation Event",
                "another event",
            ),
            (
                3,
                BASE_TIME,
                "another grouper",
                "Sepsis Documentation Start",
            ),
        ]
    )
    default_config = SuspectedInfectionConfig()
    config = SuspectedInfectionConfig(
        selected=[SuspectedInfectionCriterionName.SEPSIS_DOC_EVENT]
    )

    result = build_suspected_infection_pipeline(config).process(events)

    assert SuspectedInfectionCriterionName.SEPSIS_DOC_EVENT in default_config.selected
    assert result["EncounterEpicCsn"].to_list() == [1]
    assert result["infection_episode_id"].to_list() == ["SEPSIS_DOC_EVENT:1"]
    assert result["criterion"].to_list() == [
        "first_ev_time_sepsis_doc_event"
    ]
    assert result["suspicion_infection_type"].to_list() == [
        "SEPSIS_DOC_EVENT"
    ]
    assert result["infect_dt"].to_list() == [BASE_TIME]
    assert result["criterion_met_dt"].to_list() == [BASE_TIME]
    assert result["evidence_dt"].to_list() == [BASE_TIME]
