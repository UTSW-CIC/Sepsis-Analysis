from datetime import datetime, timedelta
from types import SimpleNamespace

import polars as pl

from src_strategy.configs.aggregator import (
    AggregatorConfig,
    FeatureColumn,
    FeatureConfig,
    FeatureDefinition,
)
from src_strategy.data_preparation.aggregator import Aggregator


ENCOUNTER_COL = "EncounterEpicCsn"
REFERENCE_TIME_COL = "Event_DateTime"
EVENT_TIME_COL = "evt_dt"
EVENT_VALUE_COL = "evt_val"
EVENT_TYPE_COL = "evt_type"
EVENT_ID_COL = "evt_event_id"
EVENT_NAME_COL = "evt_event_name"


def make_aggregator() -> Aggregator:
    return Aggregator(AggregatorConfig(), SimpleNamespace(rolling_metrics=[]))


def test_numeric_feature_still_requires_lookback_period() -> None:
    try:
        FeatureDefinition(
            event_grouper="Some Numeric Grouper",
            alias="some_numeric_feature",
            agg="last",
        )
    except ValueError:
        return

    raise AssertionError("Numeric features must require a lookback period")


def make_tables(values: list[float]) -> tuple[pl.DataFrame, pl.DataFrame, list[datetime]]:
    start = datetime(2026, 1, 1)
    event_times = [start + timedelta(minutes=offset) for offset in range(len(values))]
    reference = pl.DataFrame(
        {
            ENCOUNTER_COL: [1],
            REFERENCE_TIME_COL: [event_times[-1]],
        }
    )
    events = pl.DataFrame(
        {
            ENCOUNTER_COL: [1] * len(values),
            EVENT_TIME_COL: event_times,
            EVENT_VALUE_COL: values,
            EVENT_TYPE_COL: ["Lab Results"] * len(values),
            EVENT_ID_COL: list(range(100, 100 + len(values))),
            EVENT_NAME_COL: [
                f"Measurement {index}" for index in range(len(values))
            ],
        }
    )
    return reference, events, event_times


def test_max_tie_selects_most_recent_source_timestamp() -> None:
    aggregator = make_aggregator()
    reference, events, event_times = make_tables([5.0, 10.0, 10.0])

    result = aggregator.rolling_agg_by_duckdb(
        reference=reference,
        events=events,
        agg_col_name="rolling_max",
        agg_func="max",
        lookback_period=60,
    )

    assert result["rolling_max"].to_list() == [10.0]
    assert result["rolling_max_source_ts"].to_list() == [event_times[-1]]
    assert result["rolling_max_source_event_id"].to_list() == [102]


def test_min_tie_selects_most_recent_source_timestamp() -> None:
    aggregator = make_aggregator()
    reference, events, event_times = make_tables([1.0, 5.0, 1.0])

    result = aggregator.rolling_agg_by_duckdb(
        reference=reference,
        events=events,
        agg_col_name="rolling_min",
        agg_func="min",
        lookback_period=60,
    )

    assert result["rolling_min"].to_list() == [1.0]
    assert result["rolling_min_source_ts"].to_list() == [event_times[-1]]
    assert result["rolling_min_source_event_name"].to_list() == [
        "Measurement 2"
    ]


def test_last_value_and_source_timestamp_come_from_same_event() -> None:
    aggregator = make_aggregator()
    reference, events, event_times = make_tables([5.0, 10.0, 7.0])

    result = aggregator.rolling_agg_by_duckdb(
        reference=reference,
        events=events,
        agg_col_name="rolling_last",
        agg_func="last",
        lookback_period=60,
    )

    assert result["rolling_last"].to_list() == [7.0]
    assert result["rolling_last_source_ts"].to_list() == [event_times[-1]]
    assert result["rolling_last_source_type"].to_list() == ["Lab Results"]


def test_mean_records_latest_contributor_and_contributor_count() -> None:
    aggregator = make_aggregator()
    reference, events, event_times = make_tables([2.0, 4.0, 6.0])

    result = aggregator.rolling_agg_by_duckdb(
        reference=reference,
        events=events,
        agg_col_name="rolling_mean",
        agg_func="mean",
        lookback_period=60,
    )

    assert result["rolling_mean"].to_list() == [4.0]
    assert result["rolling_mean_source_ts"].to_list() == [event_times[-1]]
    assert result["rolling_mean_contributor_count"].to_list() == [3]


def test_numeric_aggregation_route_keeps_source_timestamp() -> None:
    start = datetime(2026, 1, 1)
    latest = start + timedelta(minutes=10)
    feature = FeatureDefinition(
        event_grouper="Some Numeric Grouper",
        alias="some_numeric_feature",
        agg="last",
        lookback_period=60,
        preserve_source_provenance=True,
    )
    aggregator = Aggregator(
        AggregatorConfig(),
        SimpleNamespace(rolling_metrics=[feature]),
    )
    df = pl.DataFrame(
        {
            ENCOUNTER_COL: [1, 1],
            REFERENCE_TIME_COL: [start, latest],
            "Event_ID": [100, 101],
            "Type": ["Lab Results", "Lab Results"],
            "Event_Grouper": ["Some Numeric Grouper"] * 2,
            "Event_Name": ["Measurement A", "Measurement B"],
            "NumericValue": [5.0, 7.0],
        }
    )
    backbone = df.select(ENCOUNTER_COL, REFERENCE_TIME_COL)

    result = aggregator.aggregate(df, backbone).sort(REFERENCE_TIME_COL)

    assert result["some_numeric_feature"].to_list() == [5.0, 7.0]
    assert result["some_numeric_feature_source_ts"].to_list() == [start, latest]
    assert result["some_numeric_feature_source_event_id"].to_list() == [
        100,
        101,
    ]


def test_max_route_preserves_earlier_maximum_and_its_source() -> None:
    start = datetime(2026, 1, 1)
    latest = start + timedelta(minutes=10)
    feature = FeatureDefinition(
        event_grouper="Some Numeric Grouper",
        alias="some_numeric_feature",
        agg="max",
        lookback_period=60,
        preserve_source_provenance=True,
    )
    aggregator = Aggregator(
        AggregatorConfig(),
        SimpleNamespace(rolling_metrics=[feature]),
    )
    df = pl.DataFrame(
        {
            ENCOUNTER_COL: [1, 1],
            REFERENCE_TIME_COL: [start, latest],
            "Event_ID": [100, 101],
            "Type": ["Lab Results", "Lab Results"],
            "Event_Grouper": ["Some Numeric Grouper"] * 2,
            "Event_Name": ["Measurement A", "Measurement B"],
            "NumericValue": [10.0, 5.0],
        }
    )
    backbone = df.select(ENCOUNTER_COL, REFERENCE_TIME_COL)

    result = aggregator.aggregate(df, backbone).sort(REFERENCE_TIME_COL)

    assert result["some_numeric_feature"].to_list() == [10.0, 10.0]
    assert result["some_numeric_feature_source_ts"].to_list() == [start, start]
    assert result["some_numeric_feature_source_event_name"].to_list() == [
        "Measurement A",
        "Measurement A",
    ]


def test_organ_feature_ignores_same_grouper_from_wrong_source_type() -> None:
    start = datetime(2026, 1, 1)
    later = start + timedelta(minutes=10)
    df = pl.DataFrame(
        {
            ENCOUNTER_COL: [1, 1],
            REFERENCE_TIME_COL: [start, later],
            "Event_ID": [100, 101],
            "Type": ["Lab Results", "Procedure Order"],
            "Event_Grouper": ["Lactate", "Lactate"],
            "Event_Name": ["LACTATE", "LACTATE ORDER"],
            "NumericValue": [3.0, 99.0],
        }
    )
    backbone = pl.DataFrame(
        {
            ENCOUNTER_COL: [1, 1],
            REFERENCE_TIME_COL: [start, later],
        }
    )
    aggregator = Aggregator(
        AggregatorConfig(),
        FeatureConfig(selected=[FeatureColumn.LAST_LACTATE_6H]),
    )

    result = aggregator.aggregate(df, backbone).sort(REFERENCE_TIME_COL)

    assert result["last_lactate_6h"].to_list() == [3.0, 3.0]
    assert result["last_lactate_6h_source_event_id"].to_list() == [100, 100]
    assert result["last_lactate_6h_source_type"].to_list() == [
        "Lab Results",
        "Lab Results"
    ]
