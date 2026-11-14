from datetime import date
import json

import pytest
from pydantic import ValidationError

from src_strategy.configs.run_configuration import (
    RunIdentityConfig,
    active_run_configuration_sections,
    run_identity_config,
)
from src_strategy.run_versioning import (
    abbreviated_configuration_hash,
    canonical_configuration_json,
    configuration_sha256,
)


EXPECTED_ACTIVE_SECTIONS = {
    "blood_pressure_input",
    "encounter_exclusions",
    "pf_ratio_builder",
    "pulmonary_dysfunction",
    "organ_dysfunction",
    "suspected_infection",
    "sirs",
    "septic_shock",
    "sepsis_composition",
    "sirs_episode_filter",
    "bp_episode_filter",
}


def test_active_run_configuration_registry_is_explicit() -> None:
    sections = active_run_configuration_sections()

    assert set(sections) == EXPECTED_ACTIVE_SECTIONS


def test_sepsis_composition_does_not_duplicate_nested_configs() -> None:
    composition = active_run_configuration_sections()["sepsis_composition"]

    assert "suspected_infection_config" not in composition
    assert "sirs_config" not in composition
    assert "organdysfunction_config" not in composition
    assert "pulmonarydysfunction_config" not in composition
    assert "septicshock_config" not in composition


def test_encounter_exclusions_are_in_active_run_configuration() -> None:
    exclusions = active_run_configuration_sections()["encounter_exclusions"]

    assert exclusions.enabled
    assert [rule.name for rule in exclusions.rules] == [
        "discharge_after_2026_09_30",
        "cancer_registry_positive",
    ]


def test_encounter_exclusion_change_changes_configuration_hash() -> None:
    sections = active_run_configuration_sections()
    exclusions = sections["encounter_exclusions"]
    changed_rule = exclusions.rules[0].model_copy(
        update={"value": date(2026, 9, 29)}
    )
    changed_exclusions = exclusions.model_copy(
        update={"rules": (changed_rule, *exclusions.rules[1:])}
    )
    changed_sections = dict(sections)
    changed_sections["encounter_exclusions"] = changed_exclusions

    assert configuration_sha256(sections) != configuration_sha256(
        changed_sections
    )


def test_active_snapshot_excludes_operational_run_settings() -> None:
    snapshot = json.loads(
        canonical_configuration_json(active_run_configuration_sections())
    )

    assert "output_path" not in snapshot
    assert "logger_dir" not in snapshot
    assert "run_mode" not in snapshot


def test_active_configuration_produces_full_and_directory_hashes() -> None:
    full_hash = configuration_sha256(active_run_configuration_sections())

    assert len(full_hash) == 64
    assert len(abbreviated_configuration_hash(full_hash)) == 12


def test_branch_run_identity_uses_approved_semantic_labels() -> None:
    assert run_identity_config.dataset_version == "phase3_2026-06-05"
    assert run_identity_config.algorithm_variant == "first_per_organ_type"
    assert run_identity_config.clinical_definition_version == "3_1"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("dataset_version", "../phase3"),
        ("algorithm_variant", "first/per/organ"),
        ("algorithm_variant", "First Per Organ"),
    ],
)
def test_run_identity_rejects_unsafe_path_components(
    field: str,
    value: str,
) -> None:
    values = {
        "dataset_version": "phase3_2026-06-05",
        "algorithm_variant": "first_per_organ_type",
        "clinical_definition_version": "3_1",
    }
    values[field] = value

    with pytest.raises(ValidationError):
        RunIdentityConfig(**values)
