from src_strategy.configs.organdysfunction import (
    OrganDysfunctionConfig,
    organdysfunction_config,
)


def test_organ_dysfunction_config_references_reconstructed_pulmonary_state() -> None:
    assert isinstance(organdysfunction_config, OrganDysfunctionConfig)
    assert organdysfunction_config.flag_col == "organ_dysfunction_total"
    assert (
        organdysfunction_config.pulmonary.input_flag_col
        == "pulmonary_dysfunction_flag"
    )
    assert organdysfunction_config.pulmonary.flag_col == "pulmonary_failure_flag"
