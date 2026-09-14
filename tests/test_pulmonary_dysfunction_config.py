import pytest
from pydantic import ValidationError

from src_strategy.configs.pulmonarydysfunction import (
    PFConfig,
    PulmonaryDysfunctionConfig,
)


def test_pulmonary_config_matches_documented_event_contract() -> None:
    config = PulmonaryDysfunctionConfig()

    assert config.vent_documentation.start_grouper == (
        "Vent on Documentation"
    )
    assert config.vent_documentation.termination_grouper == (
        "Vent off Documentation"
    )
    assert config.vent_onoff.start_values == [
        "On Going Hospital Vent",
        "Initial",
        "$ On Going Hospital Vent",
    ]
    assert config.vent_onoff.termination_values == ["Standby"]
    assert config.vent_onoff.null_value_terminates is True


def test_mechanical_o2_config_includes_every_documented_start_value() -> None:
    values = PulmonaryDysfunctionConfig().o2_delivery.mechanical_start_values

    assert values == [
        "mechanical ventilator",
        "ventilator",
        "BiPAP",
        "CPAP",
        "NPPV/NIV",
    ]


def test_pulmonary_config_defines_termination_groupers_and_exclusions() -> None:
    config = PulmonaryDysfunctionConfig()

    assert config.o2_delivery.termination_groupers == [
        "O2 Delivery Nasal Cannula",
        "O2 Delivery Simple Face Mask",
        "O2 Delivery Room Air",
    ]
    assert config.exclusions.diagnosis_codes == ["Z99.11", "Z93.0"]
    assert config.exclusions.home_vent_value == "$ Home Vent Used"


def test_pulmonary_input_contract_is_explicit() -> None:
    config = PulmonaryDysfunctionConfig()

    assert config.required_event_columns == [
        "EncounterEpicCsn",
        "Event_DateTime",
        "Event_Grouper",
        "Value",
    ]
    assert config.required_pf_columns == [
        "EncounterEpicCsn",
        "pf_ratio",
        "pf_ratio_time",
        "pf_pair_status",
    ]


@pytest.mark.parametrize(
    "kwargs",
    [{"threshold": 0}, {"time_window_between_pao2_fio2_hrs": 0}],
)
def test_pf_config_rejects_nonpositive_thresholds(kwargs: dict) -> None:
    with pytest.raises(ValidationError):
        PFConfig(**kwargs)
