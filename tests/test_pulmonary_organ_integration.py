from datetime import datetime, timedelta

import polars as pl

from src_strategy.configs.organdysfunction import (
    OrganDysfunctionConfig,
    OrganDysfunctionCriterionName,
)
from src_strategy.data_preparation import PFRatioBuilder
from src_strategy.events.organdysfunction import (
    build_organ_dysfunction_pipeline,
)
from src_strategy.events.pulmonarydysfunction import (
    attach_pulmonary_state,
    build_pulmonary_state_timeline,
)


def test_pf_evidence_flows_through_pulmonary_and_organ_state() -> None:
    start = datetime(2026, 1, 1)
    events = pl.DataFrame(
        {
            "EncounterEpicCsn": [1, 1, 1, 1, 1, 1],
            "Event_DateTime": [
                start,
                start + timedelta(hours=1),
                start + timedelta(hours=1),
                start + timedelta(hours=3),
                start + timedelta(hours=3),
                start + timedelta(hours=4),
            ],
            "Event_Grouper": [
                "Unrelated",
                "FIO2",
                "PAO2",
                "FIO2",
                "PAO2",
                "Unrelated",
            ],
            "NumericValue": [None, 50.0, 80.0, 40.0, 100.0, None],
            "Value": [None, "50", "80", "40", "100", None],
        },
        schema_overrides={"NumericValue": pl.Float64},
    )
    aggregated = pl.DataFrame(
        {
            "EncounterEpicCsn": [1, 1, 1, 1],
            "Event_DateTime": [
                start,
                start + timedelta(hours=1),
                start + timedelta(hours=2),
                start + timedelta(hours=3),
            ],
        }
    )

    pf_events = PFRatioBuilder().build(events)
    timeline = build_pulmonary_state_timeline(events, pf_events)
    attached = attach_pulmonary_state(aggregated, timeline)
    organ_config = OrganDysfunctionConfig(
        selected=[OrganDysfunctionCriterionName.PULMONARY]
    )
    result = build_organ_dysfunction_pipeline(organ_config).process(attached)

    assert pf_events["pf_ratio"].to_list() == [160.0, 250.0]
    assert result["pulmonary_dysfunction_flag"].to_list() == [None, 1, 1, 0]
    assert result["pulmonary_failure_flag"].to_list() == [None, 1, 1, 0]
    assert result["organ_dysfunction_total"].to_list() == [0, 1, 1, 0]
