from src_strategy.configs.aggregator import FEATURE_REGISTRY, FeatureColumn
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


def test_non_pulmonary_organ_features_have_explicit_source_types() -> None:
    lab_features = [
        FeatureColumn.LAST_LACTATE_6H,
        FeatureColumn.LAST_CREATININE_12H,
        FeatureColumn.LAST_EGFR_12H,
        FeatureColumn.LAST_BILIRUBIN_12H,
        FeatureColumn.LAST_PLATELETS_24H,
        FeatureColumn.LAST_INR_12H,
        FeatureColumn.LAST_APTT_24H,
    ]
    assert all(
        FEATURE_REGISTRY[feature].event_type_value == "Lab Results"
        for feature in lab_features
    )
    assert all(
        FEATURE_REGISTRY[feature].preserve_source_provenance
        for feature in lab_features
    )
    assert (
        FEATURE_REGISTRY[FeatureColumn.LAST_GCS_12H].event_type_value
        == "Flowsheet"
    )
    assert FEATURE_REGISTRY[
        FeatureColumn.LAST_GCS_12H
    ].preserve_source_provenance
