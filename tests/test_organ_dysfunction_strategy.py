from datetime import datetime, timedelta

import polars as pl
import pytest
from pydantic import ValidationError

from src_strategy.configs.organdysfunction import (
    CardiovascularConfig,
    CoagulationConfig,
    HepaticConfig,
    NeurologicalConfig,
    OrganDysfunctionConfig,
    OrganDysfunctionCriterionName,
    RenalConfig,
)
from src_strategy.events.organdysfunction import (
    build_organ_dysfunction_pipeline,
    prepare_organ_dysfunction_input,
)
from src_strategy.events.organdysfunction.pipeline import (
    ORGAN_DYSFUNCTION_CRITERION_REGISTRY,
)


def _cardiovascular_frame() -> pl.DataFrame:
    start = datetime(2026, 1, 1)
    return pl.DataFrame(
        {
            "EncounterEpicCsn": [1, 1, 1],
            "Event_DateTime": [
                start,
                start + timedelta(hours=1),
                start + timedelta(hours=2),
            ],
            "last_lactate_6h": [None, 2.0, 2.1],
            "last_lactate_6h_source_ts": [
                None,
                start + timedelta(hours=1),
                start + timedelta(hours=2),
            ],
            "audit_marker": ["missing", "boundary", "abnormal"],
        },
        schema_overrides={
            "last_lactate_6h": pl.Float64,
            "last_lactate_6h_source_ts": pl.Datetime,
        },
    )


def _cardiovascular_only_config(
    *,
    cardiovascular: CardiovascularConfig | None = None,
) -> OrganDysfunctionConfig:
    return OrganDysfunctionConfig(
        cardiovascular=cardiovascular or CardiovascularConfig(),
        selected=[OrganDysfunctionCriterionName.CARDIOVASCULAR],
    )


def _neurological_frame() -> pl.DataFrame:
    start = datetime(2026, 1, 1)
    return pl.DataFrame(
        {
            "EncounterEpicCsn": [1, 1, 1],
            "Event_DateTime": [
                start,
                start + timedelta(hours=1),
                start + timedelta(hours=2),
            ],
            "last_lactate_6h": [2.0, 2.0, 2.0],
            "last_gcs_12h": [None, 14.0, 15.0],
            "last_gcs_12h_source_ts": [
                None,
                start + timedelta(hours=1),
                start + timedelta(hours=2),
            ],
            "audit_marker": ["missing", "abnormal", "boundary"],
        },
        schema_overrides={
            "last_lactate_6h": pl.Float64,
            "last_gcs_12h": pl.Float64,
            "last_gcs_12h_source_ts": pl.Datetime,
        },
    )


def _renal_frame() -> pl.DataFrame:
    start = datetime(2026, 1, 1)
    return pl.DataFrame(
        {
            "EncounterEpicCsn": [1] * 7,
            "Event_DateTime": [
                start + timedelta(hours=hour) for hour in range(7)
            ],
            "last_creatinine_12h": [None, 2.1, 2.0, 2.1, 2.5, 1.0, None],
            "last_creatinine_12h_source_ts": [
                None,
                start + timedelta(hours=1),
                start + timedelta(hours=2),
                start + timedelta(hours=3),
                start + timedelta(hours=4),
                start + timedelta(hours=5),
                None,
            ],
            "Baseline_Creatinine": [None, None, None, 1.0, 1.5, 1.0, 1.0],
            "last_egfr_12h": [None, None, None, 80.0, 50.0, 49.0, 60.0],
            "last_egfr_12h_source_ts": [
                None,
                None,
                None,
                start + timedelta(hours=3),
                start + timedelta(hours=4),
                start + timedelta(hours=5),
                start + timedelta(hours=6),
            ],
            "Baseline_eGFR": [None, None, None, 100.0, 100.0, 100.0, 100.0],
            "audit_marker": [
                "missing",
                "creatinine-no-baseline",
                "creatinine-boundary",
                "creatinine-double",
                "baseline-present-no-rule",
                "egfr-decline",
                "creatinine-missing-egfr-normal",
            ],
        },
        schema_overrides={
            "last_creatinine_12h": pl.Float64,
            "last_creatinine_12h_source_ts": pl.Datetime,
            "Baseline_Creatinine": pl.Float64,
            "last_egfr_12h": pl.Float64,
            "last_egfr_12h_source_ts": pl.Datetime,
            "Baseline_eGFR": pl.Float64,
        },
    )


def _hepatic_frame() -> pl.DataFrame:
    start = datetime(2026, 1, 1)
    return pl.DataFrame(
        {
            "EncounterEpicCsn": [1] * 7,
            "Event_DateTime": [
                start + timedelta(hours=hour) for hour in range(7)
            ],
            "last_bilirubin_12h": [None, 2.1, 2.0, 3.0, 2.0, 3.0, 4.0],
            "last_bilirubin_12h_source_ts": [
                None,
                start + timedelta(hours=1),
                start + timedelta(hours=2),
                start + timedelta(hours=3),
                start + timedelta(hours=4),
                start + timedelta(hours=5),
                start + timedelta(hours=6),
            ],
            "Baseline_Bilirubin": [None, None, None, 1.0, 1.0, 2.0, 2.0],
            "audit_marker": [
                "missing",
                "no-baseline-positive",
                "absolute-boundary",
                "baseline-positive",
                "both-boundaries",
                "baseline-not-double",
                "double-boundary",
            ],
        },
        schema_overrides={
            "last_bilirubin_12h": pl.Float64,
            "last_bilirubin_12h_source_ts": pl.Datetime,
            "Baseline_Bilirubin": pl.Float64,
        },
    )


def _coagulation_frame() -> pl.DataFrame:
    start = datetime(2026, 1, 1)
    hours = list(range(9))
    return pl.DataFrame(
        {
            "EncounterEpicCsn": [1] * 9,
            "Event_DateTime": [
                start + timedelta(hours=hour) for hour in hours
            ],
            "last_platelets_24h": [
                None,
                49.0,
                50.5,
                99.0,
                99.0,
                100.0,
                150.0,
                150.0,
                None,
            ],
            "last_platelets_24h_source_ts": [
                None if hour in (0, 8) else start + timedelta(hours=hour)
                for hour in hours
            ],
            "Baseline_Platelets": [
                None,
                101.0,
                101.0,
                100.0,
                None,
                None,
                None,
                200.0,
                None,
            ],
            "last_inr_12h": [None, 1.0, 1.0, 1.0, 1.5, 1.6, 1.5, 2.0, 1.6],
            "last_inr_12h_source_ts": [
                None if hour == 0 else start + timedelta(hours=hour)
                for hour in hours
            ],
            "last_aptt_24h": [None, 40.0, 40.0, 40.0, 60.0, 60.0, 61.0, 70.0, None],
            "last_aptt_24h_source_ts": [
                None if hour in (0, 8) else start + timedelta(hours=hour)
                for hour in hours
            ],
            "audit_marker": [
                "missing",
                "platelet-drop",
                "half-baseline-boundary",
                "baseline-threshold-boundary",
                "platelets-no-baseline",
                "inr-no-baseline",
                "aptt-no-baseline",
                "baseline-blocks-inr-aptt",
                "inr-with-platelets-missing",
            ],
        },
        schema_overrides={
            "last_platelets_24h": pl.Float64,
            "last_platelets_24h_source_ts": pl.Datetime,
            "Baseline_Platelets": pl.Float64,
            "last_inr_12h": pl.Float64,
            "last_inr_12h_source_ts": pl.Datetime,
            "last_aptt_24h": pl.Float64,
            "last_aptt_24h_source_ts": pl.Datetime,
        },
    )


def test_cardiovascular_flag_distinguishes_missing_normal_and_abnormal() -> None:
    source = _cardiovascular_frame()

    result = build_organ_dysfunction_pipeline(
        _cardiovascular_only_config()
    ).process(source)

    assert result["cardiovascular_failure_flag"].to_list() == [None, 0, 1]
    assert result["organ_dysfunction_total"].to_list() == [0, 0, 1]
    assert result.schema["cardiovascular_failure_flag"] == pl.Int8
    assert result.schema["organ_dysfunction_total"] == pl.Int64


def test_cardiovascular_pipeline_preserves_input_and_provenance() -> None:
    source = _cardiovascular_frame()

    result = build_organ_dysfunction_pipeline(
        _cardiovascular_only_config()
    ).process(source)

    assert result.select(source.columns).equals(source)


def test_cardiovascular_threshold_is_configurable_and_strict() -> None:
    config = _cardiovascular_only_config(
        cardiovascular=CardiovascularConfig(lactate_threshold=2.1)
    )

    result = build_organ_dysfunction_pipeline(config).process(
        _cardiovascular_frame()
    )

    assert result["cardiovascular_failure_flag"].to_list() == [None, 0, 0]


def test_cardiovascular_pipeline_rejects_missing_feature_column() -> None:
    source = _cardiovascular_frame().drop("last_lactate_6h")

    with pytest.raises(ValueError, match="last_lactate_6h"):
        build_organ_dysfunction_pipeline(
            _cardiovascular_only_config()
        ).process(source)


def test_neurological_flag_distinguishes_missing_abnormal_and_boundary() -> None:
    source = _neurological_frame()
    config = OrganDysfunctionConfig(
        selected=[OrganDysfunctionCriterionName.NEUROLOGICAL]
    )

    result = build_organ_dysfunction_pipeline(config).process(source)

    assert result["neurological_failure_flag"].to_list() == [None, 1, 0]
    assert result["organ_dysfunction_total"].to_list() == [0, 1, 0]
    assert result.schema["neurological_failure_flag"] == pl.Int8
    assert result.select(source.columns).equals(source)


def test_neurological_threshold_is_configurable_and_strict() -> None:
    config = OrganDysfunctionConfig(
        neurological=NeurologicalConfig(gcs_threshold=14.0),
        selected=[OrganDysfunctionCriterionName.NEUROLOGICAL],
    )

    result = build_organ_dysfunction_pipeline(config).process(
        _neurological_frame()
    )

    assert result["neurological_failure_flag"].to_list() == [None, 0, 0]


def test_neurological_pipeline_rejects_missing_feature_column() -> None:
    source = _neurological_frame().drop("last_gcs_12h")
    config = OrganDysfunctionConfig(
        selected=[OrganDysfunctionCriterionName.NEUROLOGICAL]
    )

    with pytest.raises(ValueError, match="last_gcs_12h"):
        build_organ_dysfunction_pipeline(config).process(source)


def test_renal_subflags_and_combined_flag_follow_clinical_rules() -> None:
    source = _renal_frame()
    config = OrganDysfunctionConfig(
        selected=[OrganDysfunctionCriterionName.RENAL]
    )

    result = build_organ_dysfunction_pipeline(config).process(source)

    assert result["creatinine2x_criteria_flag"].to_list() == [
        None,
        None,
        None,
        1,
        0,
        0,
        None,
    ]
    assert result["creatinine_gt2_no_baseline_criteria_flag"].to_list() == [
        None,
        1,
        0,
        0,
        0,
        0,
        None,
    ]
    assert result["egfr50_criteria_flag"].to_list() == [
        None,
        None,
        None,
        0,
        0,
        1,
        0,
    ]
    assert result["renal_failure_flag"].to_list() == [0, 1, 0, 1, 0, 1, 0]
    assert result["organ_dysfunction_total"].to_list() == [
        0,
        1,
        0,
        1,
        0,
        1,
        0,
    ]
    assert result.select(source.columns).equals(source)


def test_renal_thresholds_are_configurable_and_strict() -> None:
    config = OrganDysfunctionConfig(
        renal=RenalConfig(
            creatinine_threshold=2.1,
            creatinine_multiplier=2.1,
            egfr_multiplier=0.49,
        ),
        selected=[OrganDysfunctionCriterionName.RENAL],
    )

    result = build_organ_dysfunction_pipeline(config).process(_renal_frame())

    assert result["renal_failure_flag"].to_list() == [0, 0, 0, 0, 0, 0, 0]


def test_renal_pipeline_rejects_missing_feature_or_baseline_columns() -> None:
    source = _renal_frame().drop("last_egfr_12h", "Baseline_Creatinine")
    config = OrganDysfunctionConfig(
        selected=[OrganDysfunctionCriterionName.RENAL]
    )

    with pytest.raises(ValueError, match="Baseline_Creatinine") as error:
        build_organ_dysfunction_pipeline(config).process(source)

    assert "last_egfr_12h" in str(error.value)


def test_hepatic_subflags_and_combined_flag_follow_clinical_rules() -> None:
    source = _hepatic_frame()
    config = OrganDysfunctionConfig(
        selected=[OrganDysfunctionCriterionName.HEPATIC]
    )

    result = build_organ_dysfunction_pipeline(config).process(source)

    assert result["bilirubin2x_criteria_flag"].to_list() == [
        None,
        None,
        None,
        1,
        0,
        0,
        0,
    ]
    assert result["bilirubin_gt2_no_baseline_criteria_flag"].to_list() == [
        None,
        1,
        0,
        0,
        0,
        0,
        0,
    ]
    assert result["hepatic_failure_flag"].to_list() == [0, 1, 0, 1, 0, 0, 0]
    assert result["organ_dysfunction_total"].to_list() == [
        0,
        1,
        0,
        1,
        0,
        0,
        0,
    ]
    assert result.select(source.columns).equals(source)


def test_hepatic_thresholds_are_configurable_and_strict() -> None:
    config = OrganDysfunctionConfig(
        hepatic=HepaticConfig(
            bilirubin_threshold=3.0,
            bilirubin_multiplier=3.0,
        ),
        selected=[OrganDysfunctionCriterionName.HEPATIC],
    )

    result = build_organ_dysfunction_pipeline(config).process(_hepatic_frame())

    assert result["hepatic_failure_flag"].to_list() == [0, 0, 0, 0, 0, 0, 0]


def test_hepatic_pipeline_rejects_missing_feature_or_baseline_columns() -> None:
    source = _hepatic_frame().drop(
        "last_bilirubin_12h",
        "Baseline_Bilirubin",
    )
    config = OrganDysfunctionConfig(
        selected=[OrganDysfunctionCriterionName.HEPATIC]
    )

    with pytest.raises(ValueError, match="Baseline_Bilirubin") as error:
        build_organ_dysfunction_pipeline(config).process(source)

    assert "last_bilirubin_12h" in str(error.value)


def test_coagulation_subflags_and_combined_flag_follow_clinical_rules() -> None:
    source = _coagulation_frame()
    config = OrganDysfunctionConfig(
        selected=[OrganDysfunctionCriterionName.COAGULATION]
    )

    result = build_organ_dysfunction_pipeline(config).process(source)

    assert result["platelets50_criteria_flag"].to_list() == [
        None,
        1,
        0,
        0,
        None,
        None,
        None,
        0,
        None,
    ]
    assert result["platelets100_criteria_flag"].to_list() == [
        None,
        0,
        0,
        0,
        1,
        0,
        0,
        0,
        None,
    ]
    assert result["inr_criteria_flag"].to_list() == [
        None,
        0,
        0,
        0,
        0,
        1,
        0,
        0,
        1,
    ]
    assert result["aptt_criteria_flag"].to_list() == [
        None,
        0,
        0,
        0,
        0,
        0,
        1,
        0,
        None,
    ]
    assert result["coagulation_failure_flag"].to_list() == [
        0,
        1,
        0,
        0,
        1,
        1,
        1,
        0,
        1,
    ]
    assert result.select(source.columns).equals(source)


def test_coagulation_thresholds_are_configurable_and_strict() -> None:
    config = OrganDysfunctionConfig(
        coagulation=CoagulationConfig(
            platelets_threshold=99.0,
            platelets_multiplier=0.48,
            inr_threshold=1.6,
            aptt_threshold=61.0,
        ),
        selected=[OrganDysfunctionCriterionName.COAGULATION],
    )

    result = build_organ_dysfunction_pipeline(config).process(
        _coagulation_frame()
    )

    assert result["coagulation_failure_flag"].to_list() == [0] * 9


def test_coagulation_pipeline_rejects_missing_feature_or_baseline_columns() -> None:
    source = _coagulation_frame().drop("last_inr_12h", "Baseline_Platelets")
    config = OrganDysfunctionConfig(
        selected=[OrganDysfunctionCriterionName.COAGULATION]
    )

    with pytest.raises(ValueError, match="Baseline_Platelets") as error:
        build_organ_dysfunction_pipeline(config).process(source)

    assert "last_inr_12h" in str(error.value)


def test_organ_total_counts_both_registered_dysfunctions() -> None:
    source = pl.DataFrame(
        {
            "last_lactate_6h": [2.1],
            "last_gcs_12h": [14.0],
        }
    )

    config = OrganDysfunctionConfig(
        selected=[
            OrganDysfunctionCriterionName.CARDIOVASCULAR,
            OrganDysfunctionCriterionName.NEUROLOGICAL,
        ]
    )
    result = build_organ_dysfunction_pipeline(config).process(source)

    assert result["cardiovascular_failure_flag"].to_list() == [1]
    assert result["neurological_failure_flag"].to_list() == [1]
    assert result["organ_dysfunction_total"].to_list() == [2]


def test_pulmonary_strategy_preserves_reconstructed_nullable_state() -> None:
    source = pl.DataFrame(
        {"pulmonary_dysfunction_flag": [None, 0, 1]},
        schema_overrides={"pulmonary_dysfunction_flag": pl.Int8},
    )
    config = OrganDysfunctionConfig(
        selected=[OrganDysfunctionCriterionName.PULMONARY]
    )

    result = build_organ_dysfunction_pipeline(config).process(source)

    assert result["pulmonary_failure_flag"].to_list() == [None, 0, 1]
    assert result["organ_dysfunction_total"].to_list() == [0, 0, 1]


def test_default_pipeline_combines_all_six_organs_after_baseline_join() -> None:
    start = datetime(2026, 1, 1)
    aggregated = pl.DataFrame(
        {
            "EncounterEpicCsn": [1, 2, 3],
            "Event_DateTime": [start] * 3,
            "last_lactate_6h": [2.1, 2.0, None],
            "last_gcs_12h": [14.0, 15.0, None],
            "last_creatinine_12h": [2.1, 1.0, None],
            "last_egfr_12h": [49.0, 100.0, None],
            "last_bilirubin_12h": [3.0, 1.0, None],
            "last_platelets_24h": [49.0, 150.0, None],
            "last_inr_12h": [1.0, 1.0, None],
            "last_aptt_24h": [40.0, 40.0, None],
            "pulmonary_dysfunction_flag": [1, 0, None],
            "audit_marker": ["all-positive", "all-negative", "missing"],
        },
        schema_overrides={
            "last_lactate_6h": pl.Float64,
            "last_gcs_12h": pl.Float64,
            "last_creatinine_12h": pl.Float64,
            "last_egfr_12h": pl.Float64,
            "last_bilirubin_12h": pl.Float64,
            "last_platelets_24h": pl.Float64,
            "last_inr_12h": pl.Float64,
            "last_aptt_24h": pl.Float64,
            "pulmonary_dysfunction_flag": pl.Int8,
        },
    )
    encounters = pl.DataFrame(
        {
            "EncounterEpicCsn": [1, 2],
            "Baseline_Creatinine": [1.0, 1.0],
            "Baseline_eGFR": [100.0, 100.0],
            "Baseline_Bilirubin": [1.0, 1.0],
            "Baseline_Platelets": [101.0, 150.0],
        }
    )

    prepared = prepare_organ_dysfunction_input(aggregated, encounters)
    result = build_organ_dysfunction_pipeline().process(prepared)

    assert result["cardiovascular_failure_flag"].to_list() == [1, 0, None]
    assert result["pulmonary_failure_flag"].to_list() == [1, 0, None]
    assert result["neurological_failure_flag"].to_list() == [1, 0, None]
    assert result["renal_failure_flag"].to_list() == [1, 0, 0]
    assert result["hepatic_failure_flag"].to_list() == [1, 0, 0]
    assert result["coagulation_failure_flag"].to_list() == [1, 0, 0]
    assert result["organ_dysfunction_total"].to_list() == [6, 0, 0]
    assert result.select(prepared.columns).equals(prepared)


def test_registry_contains_each_implemented_organ_strategy() -> None:
    assert set(ORGAN_DYSFUNCTION_CRITERION_REGISTRY) == {
        OrganDysfunctionCriterionName.CARDIOVASCULAR,
        OrganDysfunctionCriterionName.PULMONARY,
        OrganDysfunctionCriterionName.RENAL,
        OrganDysfunctionCriterionName.HEPATIC,
        OrganDysfunctionCriterionName.COAGULATION,
        OrganDysfunctionCriterionName.NEUROLOGICAL,
    }


@pytest.mark.parametrize(
    "selected",
    [[], [OrganDysfunctionCriterionName.CARDIOVASCULAR] * 2],
)
def test_organ_dysfunction_config_rejects_invalid_selection(
    selected: list[OrganDysfunctionCriterionName],
) -> None:
    with pytest.raises(ValidationError):
        OrganDysfunctionConfig(selected=selected)
