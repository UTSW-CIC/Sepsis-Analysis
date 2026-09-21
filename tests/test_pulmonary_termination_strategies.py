import polars as pl

from src_strategy.configs.pulmonarydysfunction import (
    PulmonaryDysfunctionConfig,
    PulmonaryTerminationCriterionName,
)
from src_strategy.events.pulmonarydysfunction import (
    build_pulmonary_pf_termination_pipeline,
    build_pulmonary_raw_termination_pipeline,
)
from src_strategy.events.pulmonarydysfunction.pipeline import (
    PF_TERMINATION_CRITERION_REGISTRY,
    RAW_TERMINATION_CRITERION_REGISTRY,
)


def test_raw_termination_strategies_recognize_documented_signals() -> None:
    source = pl.DataFrame(
        {
            "Event_Grouper": [
                "Vent off Documentation",
                # "Vent On/Off",
                # "Vent On/Off",
                "O2 Delivery Nasal Cannula",
                "O2 Delivery Simple Face Mask",
                "O2 Delivery Room Air",
                "O2 Delivery High-Flow",
                "O2 Delivery Non-Rebreather Mask",
                "O2 Delivery High-Flow",
                "O2 Delivery Non-Rebreather Mask",
                "Unrelated",
            ],
            "Value": [
                None,
                # "Standby",
                # None,
                None,
                None,
                None,
                "high-flow nasal cannula",
                "nonrebreather mask",
                "unexpected support",
                "unexpected support",
                "Standby",
            ],
            "audit_marker": list(range(11)),
        }
    )

    result = build_pulmonary_raw_termination_pipeline().process(source)

    assert result["pulmonary_termination_flag"].to_list() == (
        [1] * 8 + [0] * 3
    )
    assert result.select(source.columns).equals(source)


def test_raw_termination_subflags_remain_auditable() -> None:
    source = pl.DataFrame(
        {
            "Event_Grouper": [
                "Vent off Documentation",
                "Vent On/Off",
                "O2 Delivery Room Air",
            ],
            "Value": [None, "Standby", None],
        }
    )

    result = build_pulmonary_raw_termination_pipeline().process(source)

    assert result["vent_documentation_termination_flag"].to_list() == [1, 0, 0]
    assert result["vent_onoff_termination_flag"].to_list() == [0, 1, 0]
    assert result["o2_delivery_termination_flag"].to_list() == [0, 0, 1]


def test_enabled_pf_termination_uses_strict_threshold_and_missingness() -> None:
    config = PulmonaryDysfunctionConfig(
        selected_termination=[PulmonaryTerminationCriterionName.PF_RATIO]
    )
    source = pl.DataFrame(
        {
            "pf_ratio": [199.9, 200.0, 200.1, None],
            "pf_pair_status": [
                "paired",
                "paired",
                "paired",
                "no_valid_fio2_within_window",
            ],
        },
        schema_overrides={"pf_ratio": pl.Float64},
    )

    result = build_pulmonary_pf_termination_pipeline(config).process(source)

    assert result["pf_ratio_termination_flag"].to_list() == [0, 0, 1, None]
    assert result["pulmonary_termination_flag"].to_list() == [0, 0, 1, None]


def test_termination_registries_cover_every_configured_strategy() -> None:
    assert set(RAW_TERMINATION_CRITERION_REGISTRY) | set(
        PF_TERMINATION_CRITERION_REGISTRY
    ) == set(PulmonaryTerminationCriterionName)
