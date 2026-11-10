from datetime import datetime

import polars as pl

from src_strategy.configs.aggregator import (
    AggregatorConfig,
    FeatureColumn,
    FeatureConfig,
)
from src_strategy.configs.collision import collision_config
from src_strategy.data_preparation.aggregator import Aggregator
from src_strategy.data_preparation.resolvecollision import ResolveCollision


EVENT_TIME = datetime(2026, 1, 1, 12)


def _events(rows: list[dict]) -> pl.DataFrame:
    return pl.DataFrame(
        rows,
        schema_overrides={
            "NumericValue": pl.Float64,
            "sys": pl.Float64,
            "dia": pl.Float64,
            "map": pl.Float64,
        },
    )


def test_same_time_systolic_and_measured_map_are_not_collisions() -> None:
    source = _events(
        [
            {
                "EncounterEpicCsn": 1,
                "Event_DateTime": EVENT_TIME,
                "Event_ID": 10,
                "Type": "Flowsheet",
                "Event_Grouper": "Blood Pressure",
                "Event_Name": "Blood Pressure",
                "NumericValue": None,
                "Value": "120/80",
                "sys": 120.0,
                "dia": 80.0,
                "map": None,
            },
            {
                "EncounterEpicCsn": 1,
                "Event_DateTime": EVENT_TIME,
                "Event_ID": 11,
                "Type": "Flowsheet",
                "Event_Grouper": "Arterial Blood Pressure Mean",
                "Event_Name": "Measured MAP",
                "NumericValue": 60.0,
                "Value": "60",
                "sys": None,
                "dia": None,
                "map": 60.0,
            },
        ]
    )

    result = ResolveCollision(collision_config).resolve(source)

    assert result.sort("Event_ID").equals(source.sort("Event_ID"))


def test_systolic_and_measured_map_collisions_resolve_independently() -> None:
    source = _events(
        [
            {
                "EncounterEpicCsn": 1,
                "Event_DateTime": EVENT_TIME,
                "Event_ID": 10,
                "Type": "Flowsheet",
                "Event_Grouper": "Blood Pressure",
                "Event_Name": "Blood Pressure A",
                "NumericValue": None,
                "Value": "120/80",
                "sys": 120.0,
                "dia": 80.0,
                "map": None,
            },
            {
                "EncounterEpicCsn": 1,
                "Event_DateTime": EVENT_TIME,
                "Event_ID": 12,
                "Type": "Flowsheet",
                "Event_Grouper": "Blood Pressure",
                "Event_Name": "Blood Pressure B",
                "NumericValue": None,
                "Value": "90/50",
                "sys": 90.0,
                "dia": 50.0,
                "map": None,
            },
            {
                "EncounterEpicCsn": 1,
                "Event_DateTime": EVENT_TIME,
                "Event_ID": 11,
                "Type": "Flowsheet",
                "Event_Grouper": "Arterial Blood Pressure Mean",
                "Event_Name": "Measured MAP A",
                "NumericValue": 70.0,
                "Value": "70",
                "sys": None,
                "dia": None,
                "map": 70.0,
            },
            {
                "EncounterEpicCsn": 1,
                "Event_DateTime": EVENT_TIME,
                "Event_ID": 13,
                "Type": "Flowsheet",
                "Event_Grouper": "Arterial Blood Pressure Mean",
                "Event_Name": "Measured MAP B",
                "NumericValue": 60.0,
                "Value": "60",
                "sys": None,
                "dia": None,
                "map": 60.0,
            },
        ]
    )

    result = ResolveCollision(collision_config).resolve(source)

    assert result.height == 2
    systolic = result.filter(pl.col("Event_Grouper") == "Blood Pressure")
    measured_map = result.filter(
        pl.col("Event_Grouper") == "Arterial Blood Pressure Mean"
    )
    assert systolic["Event_ID"].to_list() == [12]
    assert systolic["sys"].to_list() == [90.0]
    assert measured_map["Event_ID"].to_list() == [13]
    assert measured_map["map"].to_list() == [60.0]


def test_aggregation_combines_separate_systolic_and_map_events() -> None:
    source = _events(
        [
            {
                "EncounterEpicCsn": 1,
                "Event_DateTime": EVENT_TIME,
                "Event_ID": 10,
                "Type": "Flowsheet",
                "Event_Grouper": "Blood Pressure",
                "Event_Name": "Blood Pressure",
                "NumericValue": None,
                "Value": "120/80",
                "sys": 120.0,
                "dia": 80.0,
                "map": None,
            },
            {
                "EncounterEpicCsn": 1,
                "Event_DateTime": EVENT_TIME,
                "Event_ID": 11,
                "Type": "Flowsheet",
                "Event_Grouper": "Arterial Blood Pressure Mean",
                "Event_Name": "Measured MAP",
                "NumericValue": 60.0,
                "Value": "60",
                "sys": None,
                "dia": None,
                "map": 60.0,
            },
        ]
    )
    features = FeatureConfig(
        selected=[FeatureColumn.LAST_SBP_8h, FeatureColumn.LAST_MAP_8h]
    )
    backbone = source.select("EncounterEpicCsn", "Event_DateTime").unique()

    result = Aggregator(AggregatorConfig(), features).aggregate(source, backbone)

    assert result[FeatureColumn.LAST_SBP_8h.value].to_list() == [120.0]
    assert result[FeatureColumn.LAST_MAP_8h.value].to_list() == [60.0]


def test_null_map_collision_retains_one_source_row() -> None:
    source = _events(
        [
            {
                "EncounterEpicCsn": 1,
                "Event_DateTime": EVENT_TIME,
                "Event_ID": 20,
                "Type": "Flowsheet",
                "Event_Grouper": "Arterial Blood Pressure Mean",
                "Event_Name": "Measured MAP A",
                "NumericValue": 400.0,
                "Value": "400",
                "sys": None,
                "dia": None,
                "map": None,
            },
            {
                "EncounterEpicCsn": 1,
                "Event_DateTime": EVENT_TIME,
                "Event_ID": 21,
                "Type": "Flowsheet",
                "Event_Grouper": "Arterial Blood Pressure Mean",
                "Event_Name": "Measured MAP B",
                "NumericValue": 500.0,
                "Value": "500",
                "sys": None,
                "dia": None,
                "map": None,
            },
        ]
    )

    result = ResolveCollision(collision_config).resolve(source)

    assert result.height == 1
    assert result["Event_ID"].to_list() == [20]
    assert result["map"].to_list() == [None]
