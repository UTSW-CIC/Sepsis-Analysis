from datetime import datetime, timedelta
from types import SimpleNamespace

import polars as pl

from src_strategy.configs.aggregator import (
    AggregatorConfig,
    FeatureConfig,
    FeatureDefinition,
)
from src_strategy.data_preparation.aggregator import Aggregator


ENCOUNTER_COL = "EncounterEpicCsn"
REFERENCE_TIME_COL = "Event_DateTime"
EVENT_TIME_COL = "evt_dt"
EVENT_VALUE_COL = "evt_val"


def make_aggregator() -> Aggregator:
    return Aggregator(AggregatorConfig(), FeatureConfig(selected=[]))


def test_flag_definition_accepts_presence_only_events() -> None:
    feature = FeatureDefinition(
        event_grouper="Some Flag Grouper",
        alias="some_flag",
        agg_type="flag",
        agg="last",
    )

    assert feature.flag_true_values is None
    assert feature.flag_false_values is None
    assert feature.lookback_period is None


def test_prepare_event_table_keeps_null_values_for_flags() -> None:
    aggregator = make_aggregator()
    df = pl.DataFrame(
        {
            ENCOUNTER_COL: [1],
            REFERENCE_TIME_COL: [datetime(2026, 1, 1)],
            "Event_Grouper": ["Some Flag Grouper"],
            "NumericValue": [None],
        }
    )
    feature = FeatureDefinition(
        event_grouper="Some Flag Grouper",
        alias="some_flag",
        agg_type="flag",
        agg="last",
        lookback_period=60,
    )

    result = aggregator._prepare_event_table(df, feature)

    assert result.height == 1
    assert result[EVENT_VALUE_COL].null_count() == 1


def test_null_event_sets_flag_until_validity_expires() -> None:
    aggregator = make_aggregator()
    start = datetime(2026, 1, 1)
    reference = pl.DataFrame(
        {
            ENCOUNTER_COL: [1, 1, 1, 1],
            REFERENCE_TIME_COL: [
                start,
                start + timedelta(minutes=30),
                start + timedelta(minutes=60),
                start + timedelta(minutes=61),
            ],
        }
    )
    events = pl.DataFrame(
        {
            ENCOUNTER_COL: [1],
            EVENT_TIME_COL: [start],
            EVENT_VALUE_COL: [None],
        }
    )

    result = aggregator.rolling_flag_by_duckdb(
        reference=reference,
        events=events,
        agg_col_name="some_flag",
        lookback_period=60,
    ).sort(REFERENCE_TIME_COL)

    assert result["some_flag"].to_list() == [1, 1, 1, 0]
    assert result["some_flag_last_set_ts"].to_list() == [
        start,
        start,
        start,
        None,
    ]


def test_null_event_without_lookback_persists_to_encounter_end() -> None:
    aggregator = make_aggregator()
    start = datetime(2026, 1, 1)
    reference = pl.DataFrame(
        {
            ENCOUNTER_COL: [1, 1, 1],
            REFERENCE_TIME_COL: [
                start,
                start + timedelta(days=1),
                start + timedelta(days=10),
            ],
        }
    )
    events = pl.DataFrame(
        {
            ENCOUNTER_COL: [1],
            EVENT_TIME_COL: [start],
            EVENT_VALUE_COL: [None],
        }
    )

    result = aggregator.rolling_flag_by_duckdb(
        reference=reference,
        events=events,
        agg_col_name="some_flag",
    ).sort(REFERENCE_TIME_COL)

    assert result["some_flag"].to_list() == [1, 1, 1]
    assert result["some_flag_last_set_ts"].to_list() == [start, start, start]


def test_null_termination_grouper_event_clears_flag() -> None:
    aggregator = make_aggregator()
    start = datetime(2026, 1, 1)
    stop = start + timedelta(minutes=30)
    encounter_end = start + timedelta(days=10)
    reference = pl.DataFrame(
        {
            ENCOUNTER_COL: [1, 1, 1],
            REFERENCE_TIME_COL: [start, stop, encounter_end],
        }
    )
    events = pl.DataFrame(
        {
            ENCOUNTER_COL: [1],
            EVENT_TIME_COL: [start],
            EVENT_VALUE_COL: [None],
        }
    )
    termination_events = pl.DataFrame(
        {
            ENCOUNTER_COL: [1],
            EVENT_TIME_COL: [stop],
        }
    )

    result = aggregator.rolling_flag_by_duckdb(
        reference=reference,
        events=events,
        termination_events=termination_events,
        agg_col_name="some_flag",
    ).sort(REFERENCE_TIME_COL)

    assert result["some_flag"].to_list() == [1, 0, 0]


def test_aggregate_routes_null_main_and_termination_events() -> None:
    start = datetime(2026, 1, 1)
    stop = start + timedelta(minutes=30)
    feature = FeatureDefinition(
        event_grouper="Some Flag Grouper",
        alias="some_flag",
        agg_type="flag",
        agg="last",
        termination_event_grouper="Some Termination Grouper",
    )
    aggregator = Aggregator(
        AggregatorConfig(),
        SimpleNamespace(rolling_metrics=[feature]),
    )
    df = pl.DataFrame(
        {
            ENCOUNTER_COL: [1, 1],
            REFERENCE_TIME_COL: [start, stop],
            "Event_Grouper": [
                "Some Flag Grouper",
                "Some Termination Grouper",
            ],
            "NumericValue": [None, None],
        }
    )
    backbone = df.select(ENCOUNTER_COL, REFERENCE_TIME_COL)

    result = aggregator.aggregate(df, backbone).sort(REFERENCE_TIME_COL)

    assert result["some_flag"].to_list() == [1, 0]


def test_configured_values_and_null_presence_work_together() -> None:
    aggregator = make_aggregator()
    start = datetime(2026, 1, 1)
    event_times = [start + timedelta(minutes=offset) for offset in (0, 10, 20, 30)]
    reference = pl.DataFrame(
        {
            ENCOUNTER_COL: [1] * 4,
            REFERENCE_TIME_COL: event_times,
        }
    )
    events = pl.DataFrame(
        {
            ENCOUNTER_COL: [1] * 4,
            EVENT_TIME_COL: event_times,
            EVENT_VALUE_COL: ["ON", "UNKNOWN", None, "OFF"],
        }
    )

    result = aggregator.rolling_flag_by_duckdb(
        reference=reference,
        events=events,
        agg_col_name="some_flag",
        flag_true_values=["ON"],
        flag_false_values=["OFF"],
        lookback_period=60,
    ).sort(REFERENCE_TIME_COL)

    assert result["some_flag"].to_list() == [1, 1, 1, 0]


def test_non_false_value_sets_flag_when_true_values_are_absent() -> None:
    aggregator = make_aggregator()
    start = datetime(2026, 1, 1)
    stop = start + timedelta(minutes=10)
    reference = pl.DataFrame(
        {
            ENCOUNTER_COL: [1, 1],
            REFERENCE_TIME_COL: [start, stop],
        }
    )
    events = pl.DataFrame(
        {
            ENCOUNTER_COL: [1, 1],
            EVENT_TIME_COL: [start, stop],
            EVENT_VALUE_COL: ["ANY VALUE", "OFF"],
        }
    )

    result = aggregator.rolling_flag_by_duckdb(
        reference=reference,
        events=events,
        agg_col_name="some_flag",
        flag_false_values=["OFF"],
        lookback_period=60,
    ).sort(REFERENCE_TIME_COL)

    assert result["some_flag"].to_list() == [1, 0]
