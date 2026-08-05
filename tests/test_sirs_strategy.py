from datetime import datetime, timedelta

import polars as pl

from src.configs.sirscalculator import SIRSPostAggConfig as OldSIRSConfig
from src.events.sirs import SIRSCalculator as OldSIRSCalculator
from src_strategy.configs.sirscalculator import (
    SIRSConfig,
    SIRSCriterionName,
)
from src_strategy.events.sirs import build_sirs_pipeline


def make_sirs_frame() -> pl.DataFrame:
    start = datetime(2026, 1, 1)
    return pl.DataFrame(
        {
            "EncounterEpicCsn": [1, 1, 1, 1, 1, 1],
            "Event_DateTime": [
                start + timedelta(minutes=offset)
                for offset in range(6)
            ],
            "last_temp_8h": [100.4, 100.4001, 96.79, 96.8, None, 98.6],
            "last_pulse_8h": [90.0, 91.0, 80.0, 90.0, None, 80.0],
            "last_resp_8h": [20.0, 20.0, 21.0, 20.0, None, 18.0],
            "last_wbc_12h": [12.0, 4.0, 3.9, 4.0, None, 12.1],
            "audit_marker": ["a", "b", "c", "d", "e", "f"],
        }
    )


def test_sirs_score_matches_old_post_aggregation_calculator() -> None:
    df = make_sirs_frame()

    old_result = OldSIRSCalculator(
        df,
        OldSIRSConfig(),
    ).calculate_sirs_flags()
    new_result = build_sirs_pipeline().process(df)

    assert new_result["sirs_score"].to_list() == old_result[
        "sirs_score"
    ].to_list()
    assert new_result["sirs_score"].to_list() == [0, 2, 3, 0, 0, 1]

    for flag_col in (
        "Temp_Abnormal_Flag",
        "HR_High_Flag",
        "Resp_Rate_High_Flag",
        "WBC_Abnormal_Flag",
    ):
        assert new_result[flag_col].fill_null(0).to_list() == old_result[
            flag_col
        ].to_list()


def test_sirs_uses_strict_clinical_thresholds() -> None:
    result = build_sirs_pipeline().process(make_sirs_frame())

    assert result["Temp_Abnormal_Flag"].to_list() == [
        None,
        1,
        1,
        None,
        None,
        None,
    ]
    assert result["sirs_score"].to_list() == [0, 2, 3, 0, 0, 1]
    assert "sirs_flag" not in result.columns


def test_missing_feature_column_is_retained_as_missing_evidence() -> None:
    df = make_sirs_frame().drop("last_wbc_12h").head(2)

    result = build_sirs_pipeline().process(df)

    assert result["WBC_Abnormal_Flag"].to_list() == [None, None]
    assert result["sirs_score"].to_list() == [0, 2]


def test_registry_selection_controls_criteria_and_reduction() -> None:
    config = SIRSConfig(
        selected=[
            SIRSCriterionName.TEMPERATURE,
            SIRSCriterionName.WBC,
        ],
    )
    df = make_sirs_frame().slice(2, 1)

    result = build_sirs_pipeline(config).process(df)

    assert "Temp_Abnormal_Flag" in result.columns
    assert "WBC_Abnormal_Flag" in result.columns
    assert "HR_High_Flag" not in result.columns
    assert "Resp_Rate_High_Flag" not in result.columns
    assert result["sirs_score"].to_list() == [2]


def test_sirs_pipeline_preserves_input_rows_and_provenance_columns() -> None:
    df = make_sirs_frame()

    result = build_sirs_pipeline().process(df)

    assert result.height == df.height
    assert result.select(
        "EncounterEpicCsn",
        "Event_DateTime",
        "audit_marker",
    ).equals(
        df.select(
            "EncounterEpicCsn",
            "Event_DateTime",
            "audit_marker",
        )
    )
