import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import BaseModel

from src_strategy.run_versioning import (
    RunMode,
    RUN_SUCCESS_MARKER,
    abbreviated_configuration_hash,
    abbreviated_git_commit,
    build_run_relative_path,
    canonical_configuration_json,
    configuration_sha256,
    create_incomplete_run_bundle,
    enforce_run_mode_preconditions,
    git_branch_name,
    git_commit_sha,
    finalize_run_bundle,
    require_clean_git_worktree,
    utc_run_timestamp,
    validate_output_table_names,
)


class ExampleClinicalConfig(BaseModel):
    threshold: float
    enabled: bool = True


def test_clean_git_worktree_is_accepted(monkeypatch, tmp_path) -> None:
    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    require_clean_git_worktree(tmp_path)


def test_dirty_git_worktree_is_rejected_without_exposing_paths(
    monkeypatch,
    tmp_path,
) -> None:
    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=" M clinical_logic.py\n?? private_output.parquet\n",
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="2 pending entries") as error:
        require_clean_git_worktree(tmp_path)

    assert "clinical_logic.py" not in str(error.value)
    assert "private_output.parquet" not in str(error.value)


def test_git_status_failure_stops_the_run(monkeypatch, tmp_path) -> None:
    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(
            command,
            128,
            stdout="",
            stderr="not a Git repository",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="Unable to verify"):
        require_clean_git_worktree(tmp_path)


def test_development_mode_does_not_require_git_status(
    monkeypatch,
    tmp_path,
) -> None:
    def unexpected_run(*args, **kwargs):
        raise AssertionError("Development mode must not inspect Git status")

    monkeypatch.setattr(subprocess, "run", unexpected_run)

    enforce_run_mode_preconditions(RunMode.DEVELOPMENT, tmp_path)


def test_versioned_mode_requires_a_clean_worktree(
    monkeypatch,
    tmp_path,
) -> None:
    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=" M clinical_logic.py\n",
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="dirty Git working tree"):
        enforce_run_mode_preconditions(RunMode.VERSIONED, tmp_path)


def test_configuration_fingerprint_is_independent_of_mapping_order() -> None:
    first = {
        "organ": ExampleClinicalConfig(threshold=2.0),
        "sepsis": {"forward_hours": 48, "backward_hours": 48},
    }
    second = {
        "sepsis": {"backward_hours": 48, "forward_hours": 48},
        "organ": ExampleClinicalConfig(threshold=2.0),
    }

    assert canonical_configuration_json(first) == canonical_configuration_json(
        second
    )
    assert configuration_sha256(first) == configuration_sha256(second)


def test_result_affecting_change_produces_a_different_fingerprint() -> None:
    original = {"organ": ExampleClinicalConfig(threshold=2.0)}
    changed = {"organ": ExampleClinicalConfig(threshold=2.1)}

    assert configuration_sha256(original) != configuration_sha256(changed)


def test_configuration_hash_uses_twelve_characters_in_run_path() -> None:
    full_hash = configuration_sha256(
        {"organ": ExampleClinicalConfig(threshold=2.0)}
    )

    assert len(full_hash) == 64
    assert abbreviated_configuration_hash(full_hash) == full_hash[:12]


def test_non_json_configuration_is_rejected() -> None:
    with pytest.raises(ValueError, match="must be JSON serializable"):
        configuration_sha256({"invalid": {"values": {1, 2}}})


def test_git_commit_sha_returns_validated_full_commit(
    monkeypatch,
    tmp_path,
) -> None:
    full_commit = "a" * 40

    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=f"{full_commit}\n",
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert git_commit_sha(tmp_path) == full_commit
    assert abbreviated_git_commit(full_commit) == "a" * 12


def test_git_commit_lookup_failure_stops_identity_construction(
    monkeypatch,
    tmp_path,
) -> None:
    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(
            command,
            128,
            stdout="",
            stderr="not a Git repository",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="Unable to identify"):
        git_commit_sha(tmp_path)


def test_git_branch_name_returns_branch_or_none_for_detached_head(
    monkeypatch,
    tmp_path,
) -> None:
    def branch_run(command, **kwargs):
        return subprocess.CompletedProcess(
            command,
            0,
            stdout="StrategySepsis2FirstOrganDysfunction\n",
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", branch_run)
    assert git_branch_name(tmp_path) == "StrategySepsis2FirstOrganDysfunction"

    def detached_run(command, **kwargs):
        return subprocess.CompletedProcess(
            command,
            1,
            stdout="",
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", detached_run)
    assert git_branch_name(tmp_path) is None


def test_git_branch_lookup_failure_stops_identity_construction(
    monkeypatch,
    tmp_path,
) -> None:
    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(
            command,
            128,
            stdout="",
            stderr="not a Git repository",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="current Git branch"):
        git_branch_name(tmp_path)


def test_run_timestamp_is_converted_to_utc() -> None:
    central_time = datetime(
        2026,
        9,
        21,
        10,
        30,
        12,
        tzinfo=timezone(timedelta(hours=-5)),
    )

    assert utc_run_timestamp(central_time) == "20260921T153012Z"


def test_naive_run_timestamp_is_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        utc_run_timestamp(datetime(2026, 9, 21, 15, 30, 12))


def test_run_relative_path_uses_approved_identity_format() -> None:
    relative_path = build_run_relative_path(
        dataset_version="phase3_2026-06-05",
        algorithm_variant="first_per_organ_type",
        run_timestamp="20260921T153012Z",
        git_commit="a" * 40,
        configuration_hash="b" * 64,
    )

    assert relative_path == Path(
        "phase3_2026-06-05/first_per_organ_type/"
        "20260921T153012Z__aaaaaaaaaaaa__cfg-bbbbbbbbbbbb"
    )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"dataset_version": "../phase3"},
        {"algorithm_variant": "first/per/organ"},
        {"run_timestamp": "2026-09-21"},
        {"git_commit": "not-a-commit"},
        {"configuration_hash": "too-short"},
    ],
)
def test_run_relative_path_rejects_invalid_identity_components(kwargs) -> None:
    valid = {
        "dataset_version": "phase3_2026-06-05",
        "algorithm_variant": "first_per_organ_type",
        "run_timestamp": "20260921T153012Z",
        "git_commit": "a" * 40,
        "configuration_hash": "b" * 64,
    }
    valid.update(kwargs)

    with pytest.raises(ValueError):
        build_run_relative_path(**valid)


def test_incomplete_bundle_is_created_beside_reserved_final_path(
    tmp_path,
) -> None:
    relative = Path("dataset/variant/run-id")

    paths = create_incomplete_run_bundle(tmp_path, relative)

    assert paths.final == tmp_path / relative
    assert paths.incomplete == tmp_path / "dataset/variant/run-id.incomplete"
    assert paths.incomplete.is_dir()
    assert not paths.final.exists()


@pytest.mark.parametrize("existing_name", ["run-id", "run-id.incomplete"])
def test_bundle_creation_refuses_existing_run_paths(
    tmp_path,
    existing_name: str,
) -> None:
    existing = tmp_path / "dataset/variant" / existing_name
    existing.mkdir(parents=True)

    with pytest.raises(FileExistsError):
        create_incomplete_run_bundle(
            tmp_path,
            Path("dataset/variant/run-id"),
        )


@pytest.mark.parametrize(
    "unsafe_path",
    [Path("../outside"), Path("dataset/../../outside"), Path("/absolute")],
)
def test_bundle_creation_rejects_unsafe_relative_paths(
    tmp_path,
    unsafe_path: Path,
) -> None:
    with pytest.raises(ValueError):
        create_incomplete_run_bundle(tmp_path, unsafe_path)


def test_finalization_adds_success_marker_and_publishes_bundle(tmp_path) -> None:
    paths = create_incomplete_run_bundle(
        tmp_path,
        Path("dataset/variant/run-id"),
    )
    (paths.incomplete / "example.parquet").touch()

    final = finalize_run_bundle(paths)

    assert final == paths.final
    assert final.is_dir()
    assert (final / RUN_SUCCESS_MARKER).is_file()
    assert (final / "example.parquet").is_file()
    assert not paths.incomplete.exists()


def test_failed_bundle_is_retained_without_success_marker(tmp_path) -> None:
    paths = create_incomplete_run_bundle(
        tmp_path,
        Path("dataset/variant/run-id"),
    )
    (paths.incomplete / "partial.parquet").touch()

    assert paths.incomplete.is_dir()
    assert (paths.incomplete / "partial.parquet").is_file()
    assert not (paths.incomplete / RUN_SUCCESS_MARKER).exists()
    assert not paths.final.exists()


def test_stable_output_table_names_are_accepted() -> None:
    validate_output_table_names(
        [
            "df_sepsis1_encounters.parquet",
            "df_sepsis2_associations.parquet",
        ]
    )


@pytest.mark.parametrize(
    "filename",
    [
        "df_sepsis1_encounters_v1.parquet",
        "nested/df_sepsis1_encounters.parquet",
        "df-sepsis1.parquet",
        "df_sepsis1.csv",
    ],
)
def test_versioned_or_unsafe_output_table_names_are_rejected(
    filename: str,
) -> None:
    with pytest.raises(ValueError, match="stable parquet basenames"):
        validate_output_table_names([filename])
