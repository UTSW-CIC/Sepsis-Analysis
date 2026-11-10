from datetime import datetime, timedelta

import polars as pl
import pytest

from src_strategy.events.septicshock import (
    build_lactate_gt2_evidence,
    build_septic_shock_point_evidence,
    build_vasopressor_evidence,
)


START = datetime(2026, 1, 1)


def test_vasopressor_admin_links_to_order_and_unlinked_admin_uses_admin_time() -> None:
    events = pl.DataFrame(
        {
            "EncounterEpicCsn": [1, 1, 1, 1, 1],
            "Event_DateTime": [
                START - timedelta(hours=5),
                START + timedelta(hours=10),
                START + timedelta(hours=20),
                START + timedelta(hours=1),
                START + timedelta(hours=2),
            ],
            "Type": [
                "Medication Order",
                "Medication Administration",
                "Medication Administration",
                "Medication Order",
                "Medication Administration",
            ],
            "Event_ID": [100, 100, 200, 300, 400],
            "Event_Grouper": [
                "Norepinephrine",
                "Norepinephrine",
                "Vasopressin",
                "Phenylephrine",
                "Epinephrine",
            ],
            "Event_Name": ["order", "linked", "unlinked", "order only", "zero"],
            "NumericValue": [None, 1.0, 2.0, None, 0.0],
        },
        schema_overrides={"NumericValue": pl.Float64},
    )

    evidence = build_vasopressor_evidence(events)
    points = build_septic_shock_point_evidence(evidence)

    assert points.height == 2
    linked = points.filter(pl.col("Event_ID") == 100).row(0, named=True)
    unlinked = points.filter(pl.col("Event_ID") == 200).row(0, named=True)
    assert linked["vasopressor_order_time"] == START - timedelta(hours=5)
    assert linked["vasopressor_anchor_time"] == START - timedelta(hours=5)
    assert linked["vasopressor_administration_time"] == START + timedelta(hours=10)
    assert unlinked["vasopressor_order_time"] is None
    assert unlinked["vasopressor_anchor_time"] == START + timedelta(hours=20)


def test_order_link_requires_matching_encounter_grouper_and_event_id() -> None:
    events = pl.DataFrame(
        {
            "EncounterEpicCsn": [1, 1],
            "Event_DateTime": [START, START + timedelta(hours=1)],
            "Type": ["Medication Order", "Medication Administration"],
            "Event_ID": [100, 100],
            "Event_Grouper": ["Norepinephrine", "Epinephrine"],
            "Event_Name": ["order", "administration"],
            "NumericValue": [None, 1.0],
        },
        schema_overrides={"NumericValue": pl.Float64},
    )

    evidence = build_vasopressor_evidence(events)
    administration = evidence.filter(
        pl.col("Type") == "Medication Administration"
    ).row(0, named=True)

    assert administration["vasopressor_order_time"] is None
    assert administration["vasopressor_anchor_time"] == START + timedelta(hours=1)


def test_order_link_rejects_multiple_distinct_order_times_for_one_key() -> None:
    events = pl.DataFrame(
        {
            "EncounterEpicCsn": [1, 1, 1],
            "Event_DateTime": [
                START,
                START + timedelta(minutes=1),
                START + timedelta(hours=1),
            ],
            "Type": [
                "Medication Order",
                "Medication Order",
                "Medication Administration",
            ],
            "Event_ID": [100, 100, 100],
            "Event_Grouper": ["Norepinephrine"] * 3,
            "Event_Name": ["order", "duplicate order", "administration"],
            "NumericValue": [None, None, 1.0],
        },
        schema_overrides={"NumericValue": pl.Float64},
    )

    with pytest.raises(ValueError, match="multiple distinct order timestamps"):
        build_vasopressor_evidence(events)


def test_lactate_gt2_is_strict_and_uses_result_events_only() -> None:
    events = pl.DataFrame(
        {
            "EncounterEpicCsn": [1, 1, 1, 1],
            "Event_DateTime": [
                START,
                START + timedelta(hours=1),
                START + timedelta(hours=2),
                START + timedelta(hours=3),
            ],
            "Type": [
                "Lab Results",
                "Lab Results",
                "Procedure Order",
                "Lab Results",
            ],
            "Event_ID": [1, 2, 3, 4],
            "Event_Grouper": ["Lactate", "Lactate", "Lactate", "Creatinine"],
            "Event_Name": ["boundary", "qualifies", "order", "wrong lab"],
            "NumericValue": [2.0, 2.1, 3.0, 4.0],
        }
    )

    evidence = build_lactate_gt2_evidence(events)

    assert evidence.height == 1
    assert evidence["lactate_gt2_dt"].to_list() == [START + timedelta(hours=1)]
    assert evidence["lactate_gt2_value"].to_list() == [2.1]
