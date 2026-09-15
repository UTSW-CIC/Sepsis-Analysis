from datetime import datetime, timedelta

import polars as pl
import pytest
from pydantic import ValidationError

from src_strategy.configs.septicshock import (
    SepticShockConfig,
    SepticShockCriterionName,
    VasopressorCriteria,
)
from src_strategy.events.septicshock import (
    attach_vasopressor_evidence,
    build_septic_shock_pipeline,
    build_vasopressor_evidence,
    prepare_septic_shock_input,
)
from src_strategy.events.septicshock.pipeline import (
    SEPTIC_SHOCK_CRITERION_REGISTRY,
)


START = datetime(2026, 1, 1)


def _shock_frame() -> pl.DataFrame:
    times = [START + timedelta(hours=hour) for hour in range(8)]
    source_times = [None, *times[1:]]
    return pl.DataFrame(
        {
            "EncounterEpicCsn": [1] * 8,
            "Event_DateTime": times,
            "last_sbp_8h": [None, 89.0, 90.0, 90.0, 120.0, 120.0, 120.0, 120.0],
            "last_sbp_8h_source_ts": source_times,
            "Baseline_SBP": [None, None, 131.0, 130.0, 120.0, 120.0, 120.0, 120.0],
            "last_map_8h": [None, 70.0, 70.0, 70.0, 64.0, 65.0, 70.0, 70.0],
            "last_map_8h_source_ts": source_times,
            "last_lactate_6h": [None, 2.0, 2.0, 2.0, 2.0, 4.0, 4.1, 2.0],
            "last_lactate_6h_source_ts": source_times,
            "vasopressor_administered_flag": [0, 0, 0, 0, 0, 0, 0, 1],
            "audit_marker": [
                "missing",
                "sbp-below-90",
                "sbp-decline",
                "sbp-decline-boundary",
                "map-below-65",
                "map-and-lactate-boundaries",
                "lactate-above-4",
                "vasopressor",
            ],
        },
        schema_overrides={
            "last_sbp_8h": pl.Float64,
            "last_sbp_8h_source_ts": pl.Datetime,
            "Baseline_SBP": pl.Float64,
            "last_map_8h": pl.Float64,
            "last_map_8h_source_ts": pl.Datetime,
            "last_lactate_6h": pl.Float64,
            "last_lactate_6h_source_ts": pl.Datetime,
            "vasopressor_administered_flag": pl.Int8,
        },
    )


def test_default_registry_contains_all_five_shock_criteria() -> None:
    assert list(SEPTIC_SHOCK_CRITERION_REGISTRY) == list(
        SepticShockCriterionName
    )
    assert SepticShockConfig().selected == list(SepticShockCriterionName)


def test_config_rejects_duplicate_or_empty_selections() -> None:
    with pytest.raises(ValidationError, match="must be unique"):
        SepticShockConfig(
            selected=[
                SepticShockCriterionName.SBP_90,
                SepticShockCriterionName.SBP_90,
            ]
        )
    with pytest.raises(ValidationError, match="at least one"):
        SepticShockConfig(selected=[])
    with pytest.raises(ValidationError, match="groupers must be unique"):
        SepticShockConfig(
            vasopressor_criteria=VasopressorCriteria(
                grouper_values=["Norepinephrine", "Norepinephrine"]
            )
        )


def test_all_shock_criteria_use_strict_thresholds_and_nullable_evidence() -> None:
    result = build_septic_shock_pipeline().process(_shock_frame())

    assert result["sbp90_flag"].to_list() == [None, 1, 0, 0, 0, 0, 0, 0]
    assert result["sbpdelta40_flag"].to_list() == [
        None,
        None,
        1,
        0,
        0,
        0,
        0,
        0,
    ]
    assert result["map65_flag"].to_list() == [None, 0, 0, 0, 1, 0, 0, 0]
    assert result["lactate4_flag"].to_list() == [
        None,
        0,
        0,
        0,
        0,
        0,
        1,
        0,
    ]
    assert result["vasopressor_flag"].to_list() == [0, 0, 0, 0, 0, 0, 0, 1]
    assert result["septic_shock_flag"].to_list() == [0, 1, 1, 0, 1, 0, 1, 1]
    assert result["audit_marker"].to_list() == _shock_frame()[
        "audit_marker"
    ].to_list()


def test_sbp_below_90_does_not_depend_on_baseline_availability() -> None:
    frame = _shock_frame().slice(1, 1).with_columns(
        pl.lit(120.0).alias("Baseline_SBP")
    )
    result = build_septic_shock_pipeline(
        SepticShockConfig(selected=[SepticShockCriterionName.SBP_90])
    ).process(frame)

    assert result["sbp90_flag"].to_list() == [1]
    assert result["septic_shock_flag"].to_list() == [1]


def test_enabled_hypotension_filter_controls_bp_shock_contribution() -> None:
    frame = _shock_frame().slice(1, 1).with_columns(
        pl.lit(0, dtype=pl.Int8).alias("effective_hypotension_flag")
    )

    filtered = build_septic_shock_pipeline(
        use_filtered_hypotension=True
    ).process(frame)
    unfiltered = build_septic_shock_pipeline().process(
        frame.drop("effective_hypotension_flag")
    )

    assert filtered["sbp90_flag"].to_list() == [1]
    assert filtered["effective_hypotension_flag"].to_list() == [0]
    assert filtered["septic_shock_flag"].to_list() == [0]
    assert unfiltered["septic_shock_flag"].to_list() == [1]


def test_retained_filtered_hypotension_contributes_to_shock() -> None:
    frame = _shock_frame().slice(3, 1).with_columns(
        pl.lit(1, dtype=pl.Int8).alias("effective_hypotension_flag")
    )

    result = build_septic_shock_pipeline(
        use_filtered_hypotension=True
    ).process(frame)

    assert result.select("sbp90_flag", "sbpdelta40_flag", "map65_flag").row(
        0
    ) == (0, 0, 0)
    assert result["septic_shock_flag"].to_list() == [1]


def test_selected_registry_slice_requires_only_its_input() -> None:
    frame = pl.DataFrame(
        {
            "Event_DateTime": [START],
            "last_lactate_6h": [4.1],
            "last_lactate_6h_source_ts": [START],
        }
    )
    result = build_septic_shock_pipeline(
        SepticShockConfig(selected=[SepticShockCriterionName.LACTATE_4])
    ).process(frame)

    assert result["lactate4_flag"].to_list() == [1]
    assert result["septic_shock_flag"].to_list() == [1]


def test_missing_required_criterion_column_raises() -> None:
    with pytest.raises(ValueError, match="last_map_8h"):
        build_septic_shock_pipeline(
            SepticShockConfig(selected=[SepticShockCriterionName.MAP_65])
        ).process(pl.DataFrame({"unrelated": [1]}))


def test_numeric_shock_evidence_clears_at_exact_validity_boundary() -> None:
    frame = pl.DataFrame(
        {
            "Event_DateTime": [START + timedelta(hours=8)],
            "last_sbp_8h": [80.0],
            "last_sbp_8h_source_ts": [START],
            "last_map_8h": [50.0],
            "last_map_8h_source_ts": [START],
            "last_lactate_6h": [5.0],
            "last_lactate_6h_source_ts": [START + timedelta(hours=2)],
        }
    )
    config = SepticShockConfig(
        selected=[
            SepticShockCriterionName.SBP_90,
            SepticShockCriterionName.MAP_65,
            SepticShockCriterionName.LACTATE_4,
        ]
    )

    result = build_septic_shock_pipeline(config).process(frame)

    assert result.select("sbp90_flag", "map65_flag", "lactate4_flag").row(0) == (
        None,
        None,
        None,
    )
    assert result["septic_shock_flag"].to_list() == [0]


def _event(
    hour: int,
    *,
    event_type: str,
    grouper: str,
    name: str,
    dose: float | None,
) -> dict:
    return {
        "EncounterEpicCsn": 1,
        "Event_DateTime": START + timedelta(hours=hour),
        "Type": event_type,
        "Event_Grouper": grouper,
        "Event_Name": name,
        "NumericValue": dose,
    }


def test_vasopressor_evidence_requires_positive_administered_dose() -> None:
    events = pl.DataFrame(
        [
            _event(
                0,
                event_type="Medication Order",
                grouper="Norepinephrine",
                name="ordered",
                dose=5.0,
            ),
            _event(
                0,
                event_type="Medication Administration",
                grouper="Epinephrine",
                name="zero dose",
                dose=0.0,
            ),
            _event(
                0,
                event_type="Medication Administration",
                grouper="Phenylephrine",
                name="missing dose",
                dose=None,
            ),
            _event(
                0,
                event_type="Medication Administration",
                grouper="Norepinephrine",
                name="administered",
                dose=1.0,
            ),
            _event(
                1,
                event_type="Medication Administration",
                grouper="Unrelated",
                name="not a vasopressor",
                dose=2.0,
            ),
            _event(
                2,
                event_type="Medication Administration",
                grouper="Vasopressin",
                name="later administered",
                dose=2.0,
            ),
        ],
        schema_overrides={"NumericValue": pl.Float64},
    )
    timeline = pl.DataFrame(
        {
            "EncounterEpicCsn": [1, 1, 1],
            "Event_DateTime": [
                START,
                START + timedelta(hours=1),
                START + timedelta(hours=2),
            ],
            "existing": ["a", "b", "c"],
        }
    )

    evidence = build_vasopressor_evidence(events)
    attached = attach_vasopressor_evidence(timeline, evidence)

    assert evidence.height == 5
    assert evidence["vasopressor_qualifying_dose_flag"].to_list() == [
        0,
        1,
        0,
        0,
        1,
    ]
    assert attached["vasopressor_evidence_event_count"].to_list() == [4, 0, 1]
    assert attached["vasopressor_qualifying_dose_count"].to_list() == [1, 0, 1]
    assert attached["vasopressor_administered_flag"].to_list() == [1, 0, 1]
    assert attached["existing"].to_list() == ["a", "b", "c"]


def test_vasopressor_attachment_rejects_evidence_outside_timeline() -> None:
    events = pl.DataFrame(
        [
            _event(
                1,
                event_type="Medication Administration",
                grouper="Norepinephrine",
                name="administered",
                dose=1.0,
            )
        ]
    )
    timeline = pl.DataFrame(
        {
            "EncounterEpicCsn": [1],
            "Event_DateTime": [START],
        }
    )

    with pytest.raises(ValueError, match="absent from"):
        attach_vasopressor_evidence(
            timeline,
            build_vasopressor_evidence(events),
        )


def test_septic_shock_preparation_adds_baseline_and_preserves_missing_row() -> None:
    events = pl.DataFrame(
        [
            _event(
                0,
                event_type="Medication Administration",
                grouper="Norepinephrine",
                name="administered",
                dose=1.0,
            )
        ]
    )
    timeline = pl.DataFrame(
        {
            "EncounterEpicCsn": [1, 2],
            "Event_DateTime": [START, START],
            "existing": ["a", "b"],
        }
    )
    encounters = pl.DataFrame(
        {"EncounterEpicCsn": [1], "Baseline_SBP": [130.0]}
    )

    result = prepare_septic_shock_input(
        timeline,
        encounters,
        build_vasopressor_evidence(events),
    )

    assert result["Baseline_SBP"].to_list() == [130.0, None]
    assert result[
        "septic_shock_baseline_encounter_row_available"
    ].to_list() == [True, False]
    assert result["vasopressor_administered_flag"].to_list() == [1, 0]
    assert result["existing"].to_list() == ["a", "b"]
