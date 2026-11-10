from datetime import datetime, timedelta

import polars as pl

from src_strategy.configs.suspected_infection import (
    SuspectedInfectionConfig,
    SuspectedInfectionCriterionName,
)
from src_strategy.events.suspected_infection import (
    build_suspected_infection_pipeline,
)


def test_both_paired_criteria_use_the_shared_culture_groupers() -> None:
    event_time = datetime(2026, 1, 1, 12)
    shared_culture_grouper = "Shared Culture Test Grouper"
    events = pl.DataFrame(
        {
            "EncounterEpicCsn": [1, 1, 1, 2, 2, 2, 2],
            "Event_DateTime": [event_time] * 7,
            "Event_ID": [1, 1, 2, 3, 3, 4, 5],
            "Type": [
                "Medication Administration",
                "Medication Order",
                "Procedure Order",
                "Procedure Order",
                "Lab Results",
                "Procedure Order",
                "Procedure Order",
            ],
            "Event_Grouper": [
                "IV Antibiotics",
                "IV Antibiotics",
                shared_culture_grouper,
                "Lab",
                "Lactate",
                shared_culture_grouper,
                shared_culture_grouper,
            ],
            "Event_Name": [
                "antibiotic administration",
                "antibiotic order",
                "culture 1",
                "LACTATE (LACTIC ACID) SERUM",
                "LACTATE",
                "culture 1",
                "culture 2",
            ],
            "NumericValue": [None, None, None, None, 2.0, None, None],
            "Value": [None, None, None, None, "2.0", None, None],
        }
    )
    config = SuspectedInfectionConfig(
        blood_culture_groupers=[shared_culture_grouper],
        selected=[
            SuspectedInfectionCriterionName.ANTIBIOTIC_CULTURE,
            SuspectedInfectionCriterionName.LACTATE_CULTURE,
        ],
    )

    result = build_suspected_infection_pipeline(config).process(events)

    assert set(result["suspicion_infection_type"].to_list()) == {
        "IV+Culture",
        "LACTATE+CULTURE",
    }


def test_antibiotic_order_is_anchor_and_administration_controls_pairing() -> None:
    order_time = datetime(2026, 1, 1, 8)
    administration_time = order_time + timedelta(days=4)
    culture_time = administration_time + timedelta(hours=1)
    events = pl.DataFrame(
        {
            "EncounterEpicCsn": [1, 1, 1],
            "Event_DateTime": [order_time, administration_time, culture_time],
            "Event_ID": [10, 10, 20],
            "Type": [
                "Medication Order",
                "Medication Administration",
                "Procedure Order",
            ],
            "Event_Grouper": [
                "IV Antibiotics",
                "IV Antibiotics",
                "Blood Culture Order",
            ],
            "Event_Name": [
                "antibiotic order",
                "antibiotic administration",
                "culture order",
            ],
            "Value": [None, None, None],
        }
    )
    config = SuspectedInfectionConfig(
        selected=[SuspectedInfectionCriterionName.ANTIBIOTIC_CULTURE]
    )

    result = build_suspected_infection_pipeline(config).process(events)

    antibiotic_row = result.filter(pl.col("criterion") == "iv_dt").row(
        0, named=True
    )
    assert antibiotic_row["infect_dt"] == order_time
    assert antibiotic_row["admin_dt"] == administration_time
    assert antibiotic_row["infect_dt_source"] == "medication_order"
    assert result["admin_dt"].to_list() == [
        administration_time,
        administration_time,
    ]


def test_culture_before_antibiotic_and_multiple_cultures_form_one_episode() -> None:
    administration_time = datetime(2026, 1, 4, 12)
    order_time = administration_time - timedelta(hours=1)
    earlier_culture_time = administration_time - timedelta(hours=72)
    later_culture_time = administration_time + timedelta(hours=24)
    events = pl.DataFrame(
        {
            "EncounterEpicCsn": [1, 1, 1, 1],
            "Event_DateTime": [
                order_time,
                administration_time,
                earlier_culture_time,
                later_culture_time,
            ],
            "Event_ID": [10, 10, 20, 21],
            "Type": [
                "Medication Order",
                "Medication Administration",
                "Procedure Order",
                "Procedure Order",
            ],
            "Event_Grouper": [
                "IV Antibiotics",
                "IV Antibiotics",
                "Blood Culture Order",
                "Blood Culture Order",
            ],
            "Event_Name": [
                "antibiotic order",
                "antibiotic administration",
                "culture before antibiotic",
                "culture after antibiotic",
            ],
            "Value": [None] * 4,
        }
    )
    config = SuspectedInfectionConfig(
        selected=[SuspectedInfectionCriterionName.ANTIBIOTIC_CULTURE]
    )

    result = build_suspected_infection_pipeline(config).process(events)

    assert result.height == 3
    assert result["infection_episode_id"].n_unique() == 1
    assert result.filter(pl.col("criterion") == "iv_dt").height == 1
    assert result.filter(pl.col("criterion") == "culture_dt").height == 2
    assert result["infect_dt"].unique().to_list() == [earlier_culture_time]
    assert result["criterion_met_dt"].unique().to_list() == [
        administration_time
    ]
    assert set(result["evidence_dt"].to_list()) == {
        order_time,
        earlier_culture_time,
        later_culture_time,
    }


def test_unlinked_order_does_not_qualify_but_administration_falls_back() -> None:
    event_time = datetime(2026, 1, 1, 12)
    events = pl.DataFrame(
        {
            "EncounterEpicCsn": [1, 1, 2, 2],
            "Event_DateTime": [event_time] * 4,
            "Event_ID": [10, 11, 20, 21],
            "Type": [
                "Medication Order",
                "Procedure Order",
                "Medication Administration",
                "Procedure Order",
            ],
            "Event_Grouper": [
                "IV Antibiotics",
                "Blood Culture Order",
                "IV Antibiotics",
                "Blood Culture Order",
            ],
            "Event_Name": [
                "unlinked antibiotic order",
                "culture order",
                "unlinked antibiotic administration",
                "culture order",
            ],
            "Value": [None] * 4,
        }
    )
    config = SuspectedInfectionConfig(
        selected=[SuspectedInfectionCriterionName.ANTIBIOTIC_CULTURE]
    )

    result = build_suspected_infection_pipeline(config).process(events)

    assert result["EncounterEpicCsn"].unique().to_list() == [2]
    assert result["infect_dt"].to_list() == [event_time, event_time]
    assert result["admin_dt"].to_list() == [event_time, event_time]
    assert result["infect_dt_source"].to_list() == [
        "administration_fallback",
        "administration_fallback",
    ]


def test_unlinked_administration_uses_first_event_id_timestamp() -> None:
    first_event_time = datetime(2026, 1, 1, 8)
    administration_time = first_event_time + timedelta(hours=2)
    culture_time = administration_time + timedelta(hours=1)
    events = pl.DataFrame(
        {
            "EncounterEpicCsn": [1, 1, 1],
            "Event_DateTime": [
                first_event_time,
                administration_time,
                culture_time,
            ],
            "Event_ID": [10, 10, 20],
            "Type": [
                "Medication Order Questions",
                "Medication Administration",
                "Procedure Order",
            ],
            "Event_Grouper": [
                "IV Antibiotics",
                "IV Antibiotics",
                "Blood Culture Order",
            ],
            "Event_Name": [
                "linked order question",
                "antibiotic administration",
                "culture order",
            ],
            "Value": [None] * 3,
        }
    )
    config = SuspectedInfectionConfig(
        selected=[SuspectedInfectionCriterionName.ANTIBIOTIC_CULTURE]
    )

    result = build_suspected_infection_pipeline(config).process(events)

    assert result["infect_dt"].to_list() == [first_event_time] * 2
    assert result["evidence_dt"].to_list() == [
        first_event_time,
        culture_time,
    ]
    assert result["criterion_met_dt"].to_list() == [culture_time] * 2
    assert result["infection_episode_id"].n_unique() == 1
    assert result["admin_dt"].to_list() == [
        administration_time,
        administration_time,
    ]
    assert result["infect_dt_source"].to_list() == [
        "event_id_first_event",
        "event_id_first_event",
    ]


def test_null_event_id_administration_uses_its_own_timestamp() -> None:
    administration_time = datetime(2026, 1, 1, 12)
    culture_time = administration_time + timedelta(hours=1)
    events = pl.DataFrame(
        {
            "EncounterEpicCsn": [1, 1],
            "Event_DateTime": [administration_time, culture_time],
            "Event_ID": [None, 20],
            "Type": ["Medication Administration", "Procedure Order"],
            "Event_Grouper": ["IV Antibiotics", "Blood Culture Order"],
            "Event_Name": ["antibiotic administration", "culture order"],
            "Value": [None, None],
        },
        schema_overrides={"Event_ID": pl.Int64},
    )
    config = SuspectedInfectionConfig(
        selected=[SuspectedInfectionCriterionName.ANTIBIOTIC_CULTURE]
    )

    result = build_suspected_infection_pipeline(config).process(events)

    assert result["infect_dt"].to_list() == [administration_time] * 2
    assert result["evidence_dt"].to_list() == [
        administration_time,
        culture_time,
    ]
    assert result["criterion_met_dt"].to_list() == [culture_time] * 2
    assert result["infect_dt_source"].to_list() == [
        "administration_fallback",
        "administration_fallback",
    ]


def test_culture_order_time_qualifies_and_result_is_audit_metadata() -> None:
    administration_time = datetime(2026, 1, 1, 12)
    order_time = administration_time - timedelta(hours=1)
    result_time = administration_time + timedelta(days=2)
    rows = [
        # Positive result: the earlier order still supplies culture_dt.
        (1, administration_time, 10, "Medication Administration", "IV Antibiotics", "admin", None),
        (1, order_time, 20, "Procedure Order", "Blood Culture Order", "CULTURE BLOOD", None),
        (1, result_time, 20, "Lab Results", "Blood Culture Results", "ESCHERICHIA COLI BCID", "DETECTED"),
        # Negative result does not remove the qualifying order.
        (2, administration_time, 30, "Medication Administration", "IV Antibiotics", "admin", None),
        (2, order_time, 40, "Procedure Order", "Blood Culture Order", "CULTURE BLOOD", None),
        (2, result_time, 40, "Lab Results", "Blood Culture Results", "CULTURE", "No growth at 5 days"),
        # An unrelated POSITIVE component is not a positive culture result.
        (3, administration_time, 50, "Medication Administration", "IV Antibiotics", "admin", None),
        (3, order_time, 60, "Procedure Order", "Other Body Fluid Culture Order", "UA + MICROSCOPIC", None),
        (3, result_time, 60, "Lab Results", "Other Body Fluid Culture Orders", "NITRITE UA", "POSITIVE"),
        # Explicit contamination takes precedence over another positive component.
        (4, administration_time, 70, "Medication Administration", "IV Antibiotics", "admin", None),
        (4, order_time, 80, "Procedure Order", "Blood Culture Order", "CULTURE BLOOD", None),
        (4, result_time, 80, "Lab Results", "Blood Culture Results", "GRAM ST", "Bottle positive; probable contaminant"),
        # An order with no result remains eligible and is marked pending.
        (5, administration_time, 90, "Medication Administration", "IV Antibiotics", "admin", None),
        (5, order_time, 100, "Procedure Order", "Blood Culture Order", "CULTURE BLOOD", None),
        # A result without a procedure order cannot qualify on its own.
        (6, administration_time, 110, "Medication Administration", "IV Antibiotics", "admin", None),
        (6, result_time, 120, "Lab Results", "Blood Culture Results", "CULTURE", "Bottle positive"),
        # A result inside the window cannot rescue an order outside the window.
        (7, administration_time, 130, "Medication Administration", "IV Antibiotics", "admin", None),
        (7, administration_time - timedelta(days=4), 140, "Procedure Order", "Blood Culture Order", "CULTURE BLOOD", None),
        (7, administration_time, 140, "Lab Results", "Blood Culture Results", "CULTURE", "Bottle positive"),
    ]
    events = pl.DataFrame(
        rows,
        schema=[
            "EncounterEpicCsn",
            "Event_DateTime",
            "Event_ID",
            "Type",
            "Event_Grouper",
            "Event_Name",
            "Value",
        ],
        orient="row",
    )
    config = SuspectedInfectionConfig(
        selected=[SuspectedInfectionCriterionName.ANTIBIOTIC_CULTURE]
    )

    result = build_suspected_infection_pipeline(config).process(events)
    culture_rows = result.filter(pl.col("criterion") == "culture_dt").sort(
        "EncounterEpicCsn"
    )

    assert culture_rows["EncounterEpicCsn"].to_list() == [1, 2, 3, 4, 5]
    assert culture_rows["infect_dt"].to_list() == [order_time] * 5
    assert culture_rows["culture_result_status"].to_list() == [
        "positive",
        "negative",
        "indeterminate",
        "contaminant",
        "pending",
    ]
    assert culture_rows["culture_result_dt"].to_list() == [
        result_time,
        result_time,
        result_time,
        result_time,
        None,
    ]


def test_lactate_counts_orders_not_result_components() -> None:
    event_time = datetime(2026, 1, 1, 12)
    rows = [
        # One culture order with several result components is still one order.
        (1, event_time, 1, "Procedure Order", "Lab", "LACTATE (LACTIC ACID) SERUM", None, None),
        (1, event_time + timedelta(minutes=30), 1, "Lab Results", "Lactate", "LACTATE", 2.0, "2.0"),
        (1, event_time, 10, "Procedure Order", "Blood Culture Order", "CULTURE BLOOD", None, None),
        (1, event_time + timedelta(hours=1), 10, "Lab Results", "Blood Culture Results", "GRAM ST", None, "Bottle positive"),
        (1, event_time + timedelta(hours=2), 10, "Lab Results", "Blood Culture Results", "CULTURE", None, "Bottle positive"),
        # Two distinct culture orders qualify even without a lactate result.
        (2, event_time, 2, "Procedure Order", "Lab", "LACTATE (LACTIC ACID) SERUM", None, None),
        (2, event_time, 20, "Procedure Order", "Blood Culture Order", "CULTURE BLOOD A", None, None),
        (2, event_time, 21, "Procedure Order", "Blood Culture Order", "CULTURE BLOOD B", None, None),
    ]
    events = pl.DataFrame(
        rows,
        schema=[
            "EncounterEpicCsn",
            "Event_DateTime",
            "Event_ID",
            "Type",
            "Event_Grouper",
            "Event_Name",
            "NumericValue",
            "Value",
        ],
        orient="row",
    )
    config = SuspectedInfectionConfig(
        selected=[SuspectedInfectionCriterionName.LACTATE_CULTURE]
    )

    result = build_suspected_infection_pipeline(config).process(events)

    assert result["EncounterEpicCsn"].unique().to_list() == [2]
    assert result.filter(pl.col("criterion") == "culture_dt").height == 2
    lactate_row = result.filter(pl.col("criterion") == "lactate_dt").row(
        0, named=True
    )
    assert lactate_row["infect_dt"] == event_time
    assert lactate_row["lactate_result_dt"] is None
    assert lactate_row["lactate_result_value"] is None


def test_lactate_order_time_controls_pairing_and_result_is_metadata() -> None:
    order_time = datetime(2026, 1, 1, 12)
    result_time = order_time + timedelta(hours=7)
    rows = [
        # Result-time cultures cannot rescue a lactate order outside six hours.
        (1, order_time, 1, "Procedure Order", "Lab", "LACTATE (LACTIC ACID) SERUM", None, None),
        (1, result_time, 1, "Lab Results", "Lactate", "LACTATE", 3.1, "3.1"),
        (1, result_time, 10, "Procedure Order", "Blood Culture Order", "CULTURE A", None, None),
        (1, result_time, 11, "Procedure Order", "Blood Culture Order", "CULTURE B", None, None),
        # Order-time cultures qualify; the later result remains audit metadata.
        (2, order_time, 2, "Procedure Order", "Lab", "LACTATE (LACTIC ACID) POC ABL", None, None),
        (2, result_time, 2, "Lab Results", "Lactate", "LACTATE", 4.2, "4.2"),
        (2, order_time - timedelta(hours=1), 20, "Procedure Order", "Blood Culture Order", "CULTURE A", None, None),
        (2, order_time + timedelta(hours=1), 21, "Procedure Order", "Blood Culture Order", "CULTURE B", None, None),
        # An unlinked result is not a lactate order.
        (3, order_time, 3, "Lab Results", "Lactate", "LACTATE", 5.0, "5.0"),
        (3, order_time, 30, "Procedure Order", "Blood Culture Order", "CULTURE A", None, None),
        (3, order_time, 31, "Procedure Order", "Blood Culture Order", "CULTURE B", None, None),
    ]
    events = pl.DataFrame(
        rows,
        schema=[
            "EncounterEpicCsn",
            "Event_DateTime",
            "Event_ID",
            "Type",
            "Event_Grouper",
            "Event_Name",
            "NumericValue",
            "Value",
        ],
        orient="row",
    )
    config = SuspectedInfectionConfig(
        selected=[SuspectedInfectionCriterionName.LACTATE_CULTURE]
    )

    result = build_suspected_infection_pipeline(config).process(events)
    lactate_row = result.filter(pl.col("criterion") == "lactate_dt").row(
        0, named=True
    )

    assert result["EncounterEpicCsn"].unique().to_list() == [2]
    assert lactate_row["infect_dt"] == order_time - timedelta(hours=1)
    assert result["infect_dt"].n_unique() == 1
    assert result["criterion_met_dt"].unique().to_list() == [
        order_time + timedelta(hours=1)
    ]
    assert set(result["evidence_dt"].to_list()) == {
        order_time - timedelta(hours=1),
        order_time,
        order_time + timedelta(hours=1),
    }
    assert lactate_row["lactate_result_dt"] == result_time
    assert lactate_row["lactate_result_value"] == 4.2
