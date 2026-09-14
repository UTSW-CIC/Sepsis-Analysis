import polars as pl
import pytest

from src_strategy.configs.pulmonarydysfunction import (
    PulmonaryStartCriterionName,
)
from src_strategy.events.pulmonarydysfunction import (
    build_pulmonary_pf_start_pipeline,
    build_pulmonary_raw_start_pipeline,
)
from src_strategy.events.pulmonarydysfunction.pipeline import (
    PF_START_CRITERION_REGISTRY,
    RAW_START_CRITERION_REGISTRY,
)


def test_raw_start_strategies_recognize_all_documented_signals() -> None:
    mechanical_values = [
        "mechanical ventilator",
        "ventilator",
        "BiPAP",
        "CPAP",
        "NPPV/NIV",
    ]
    source = pl.DataFrame(
        {
            "Event_Grouper": [
                "Vent on Documentation",
                "Vent On/Off",
                "Vent On/Off",
                "Vent On/Off",
                *["O2 Delivery Mechanical Ventilation"] * 5,
                "Unrelated",
            ],
            "Value": [
                None,
                "On Going Hospital Vent",
                "Initial",
                "$ On Going Hospital Vent",
                *mechanical_values,
                "ventilator",
            ],
            "audit_marker": list(range(10)),
        }
    )

    result = build_pulmonary_raw_start_pipeline().process(source)

    assert result["pulmonary_start_flag"].to_list() == [1] * 9 + [0]
    assert result.select(source.columns).equals(source)


def test_raw_start_subflags_remain_auditable() -> None:
    source = pl.DataFrame(
        {
            "Event_Grouper": [
                "Vent on Documentation",
                "Vent On/Off",
                "O2 Delivery Mechanical Ventilation",
            ],
            "Value": [None, "Initial", "BiPAP"],
        }
    )

    result = build_pulmonary_raw_start_pipeline().process(source)

    assert result["vent_documentation_start_flag"].to_list() == [1, 0, 0]
    assert result["vent_onoff_start_flag"].to_list() == [0, 1, 0]
    assert result["mechanical_o2_start_flag"].to_list() == [0, 0, 1]


def test_pf_start_strategy_uses_strict_threshold_and_missingness() -> None:
    source = pl.DataFrame(
        {
            "pf_ratio": [199.9, 200.0, 200.1, None, 100.0],
            "pf_pair_status": [
                "paired",
                "paired",
                "paired",
                "no_valid_fio2_within_window",
                "invalid_pao2",
            ],
            "audit_marker": list(range(5)),
        },
        schema_overrides={"pf_ratio": pl.Float64},
    )

    result = build_pulmonary_pf_start_pipeline().process(source)

    assert result["pf_ratio_start_flag"].to_list() == [1, 0, 0, None, None]
    assert result["pulmonary_start_flag"].to_list() == [1, 0, 0, None, None]
    assert result.select(source.columns).equals(source)


def test_start_pipeline_rejects_missing_required_columns() -> None:
    with pytest.raises(ValueError, match="Value"):
        build_pulmonary_raw_start_pipeline().process(
            pl.DataFrame({"Event_Grouper": ["Vent On/Off"]})
        )

    with pytest.raises(ValueError, match="pf_pair_status"):
        build_pulmonary_pf_start_pipeline().process(
            pl.DataFrame({"pf_ratio": [100.0]})
        )


def test_start_registries_cover_every_configured_strategy() -> None:
    assert set(RAW_START_CRITERION_REGISTRY) | set(
        PF_START_CRITERION_REGISTRY
    ) == set(PulmonaryStartCriterionName)
