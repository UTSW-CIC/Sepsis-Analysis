from datetime import datetime, timedelta

import polars as pl
import pytest

from src_strategy.events.pulmonarydysfunction import (
    attach_pulmonary_state,
    build_pulmonary_state_timeline,
)


START = datetime(2026, 1, 1)


def _events() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "EncounterEpicCsn": [1, 1, 1, 1],
            "Event_DateTime": [
                START,
                START + timedelta(hours=1),
                START + timedelta(hours=3),
                START + timedelta(hours=4),
            ],
            "Event_Grouper": [
                "Unrelated",
                "Vent on Documentation",
                "Vent off Documentation",
                "Unrelated",
            ],
            "Value": [None, None, None, None],
        }
    )


def _empty_pf() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "EncounterEpicCsn": pl.Int64,
            "pf_ratio": pl.Float64,
            "pf_ratio_time": pl.Datetime,
            "pf_pair_status": pl.String,
        }
    )


def _timeline() -> pl.DataFrame:
    return build_pulmonary_state_timeline(_events(), _empty_pf())


def test_attachment_carries_state_and_evidence_to_each_wide_row() -> None:
    aggregated = pl.DataFrame(
        {
            "EncounterEpicCsn": [1, 1, 1, 1, 1],
            "Event_DateTime": [
                START + timedelta(hours=4),
                START,
                START + timedelta(hours=2),
                START + timedelta(hours=1),
                START + timedelta(hours=3),
            ],
            "existing_feature": [40, 0, 20, 10, 30],
        }
    )

    result = attach_pulmonary_state(aggregated, _timeline())

    assert result.select(aggregated.columns).equals(aggregated)
    assert result["pulmonary_dysfunction_flag"].to_list() == [0, None, 1, 1, 0]
    assert result["pulmonary_transition_time"].to_list() == [
        START + timedelta(hours=3),
        None,
        START + timedelta(hours=1),
        START + timedelta(hours=1),
        START + timedelta(hours=3),
    ]
    assert result["pulmonary_exclusion_flag"].to_list() == [0, 0, 0, 0, 0]


def test_attachment_preserves_encounter_wide_exclusion_evidence() -> None:
    events = _events().with_columns(
        pl.when(pl.col("Event_DateTime") == START + timedelta(hours=3))
        .then(pl.lit("Z99.11"))
        .otherwise(pl.col("Value"))
        .alias("Value")
    )
    timeline = build_pulmonary_state_timeline(events, _empty_pf())
    aggregated = events.select("EncounterEpicCsn", "Event_DateTime")

    result = attach_pulmonary_state(aggregated, timeline)

    assert result["pulmonary_dysfunction_flag"].to_list() == [0, 0, 0, 0]
    assert result["pulmonary_exclusion_flag"].to_list() == [1, 1, 1, 1]
    assert result["pulmonary_exclusion_reason"].to_list() == [
        ["diagnosis_code:Z99.11"],
    ] * 4


def test_attachment_rejects_overwrite_and_duplicate_keys() -> None:
    timeline = _timeline()
    aggregated = _events().select("EncounterEpicCsn", "Event_DateTime")

    with pytest.raises(ValueError, match="overwrite"):
        attach_pulmonary_state(
            aggregated.with_columns(
                pl.lit(9).alias("pulmonary_dysfunction_flag")
            ),
            timeline,
        )

    with pytest.raises(ValueError, match="duplicate keys"):
        attach_pulmonary_state(pl.concat([aggregated, aggregated.head(1)]), timeline)

    with pytest.raises(ValueError, match="duplicate keys"):
        attach_pulmonary_state(aggregated, pl.concat([timeline, timeline.head(1)]))


def test_attachment_rejects_missing_columns_and_mismatched_types() -> None:
    timeline = _timeline()
    aggregated = _events().select("EncounterEpicCsn", "Event_DateTime")

    with pytest.raises(ValueError, match="Event_DateTime"):
        attach_pulmonary_state(aggregated.drop("Event_DateTime"), timeline)

    with pytest.raises(ValueError, match="pulmonary_transition_type"):
        attach_pulmonary_state(
            aggregated,
            timeline.drop("pulmonary_transition_type"),
        )

    with pytest.raises(ValueError, match="identifier types"):
        attach_pulmonary_state(
            aggregated.with_columns(pl.col("EncounterEpicCsn").cast(pl.String)),
            timeline,
        )
