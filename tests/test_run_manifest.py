import hashlib
import json

import polars as pl
import pytest
from pydantic import ValidationError

from src_strategy.run_manifest import (
    MANIFEST_FILENAME,
    CachedInputArtifact,
    ClinicalRunManifest,
    OutputTableArtifact,
    SoftwareVersions,
    ValidationResult,
    current_software_versions,
    describe_cached_input,
    describe_output_table,
    write_run_manifest,
)


def _manifest() -> ClinicalRunManifest:
    return ClinicalRunManifest(
        dataset_version="phase3_2026-06-05",
        algorithm_variant="first_per_organ_type",
        run_timestamp_utc="20260921T153012Z",
        git_commit="a" * 40,
        git_branch="StrategySepsis2FirstOrganDysfunction",
        git_worktree_clean=True,
        configuration_sha256="b" * 64,
        configuration_snapshot={"sirs": {"hr_upper_threshold": 90.0}},
        clinical_definition_version="3_1",
        cached_inputs=[
            CachedInputArtifact(
                filename="df_aggregated.parquet",
                size_bytes=100,
                sha256="c" * 64,
            )
        ],
        output_tables=[
            OutputTableArtifact(
                filename="df_sepsis1_encounters.parquet",
                size_bytes=200,
                sha256="d" * 64,
                row_count=10,
                table_schema={"EncounterEpicCsn": "Int64"},
            )
        ],
        software_versions=SoftwareVersions(
            python="3.10.0",
            polars="1.0.0",
            duckdb="1.0.0",
            pydantic="2.0.0",
        ),
        validations=[ValidationResult(name="one_row_per_encounter", passed=True)],
    )


def test_cached_input_description_contains_only_file_identity(tmp_path) -> None:
    artifact = tmp_path / "cached.parquet"
    artifact.write_bytes(b"synthetic cached input")

    description = describe_cached_input(artifact)

    assert description.filename == "cached.parquet"
    assert description.size_bytes == artifact.stat().st_size
    assert description.sha256 == hashlib.sha256(
        b"synthetic cached input"
    ).hexdigest()


def test_output_description_records_schema_and_count(tmp_path) -> None:
    dataframe = pl.DataFrame({"encounter": [1, 2], "flag": [0, 1]})
    artifact = tmp_path / "output.parquet"
    dataframe.write_parquet(artifact)

    description = describe_output_table(artifact, dataframe)

    assert description.row_count == 2
    assert description.table_schema == {
        "encounter": "Int64",
        "flag": "Int64",
    }
    assert len(description.sha256) == 64


def test_completed_manifest_rejects_dirty_git_or_failed_validation() -> None:
    valid = _manifest().model_dump()

    with pytest.raises(ValidationError, match="clean Git state"):
        ClinicalRunManifest(**{**valid, "git_worktree_clean": False})

    failed = [ValidationResult(name="row_count", passed=False)]
    with pytest.raises(ValidationError, match="failed validations"):
        ClinicalRunManifest(**{**valid, "validations": failed})


def test_manifest_rejects_unreviewed_fields() -> None:
    values = _manifest().model_dump()
    values["patient_identifier"] = 12345

    with pytest.raises(ValidationError, match="Extra inputs"):
        ClinicalRunManifest(**values)


def test_manifest_write_is_deterministic_and_never_overwrites(tmp_path) -> None:
    incomplete = tmp_path / "run-id.incomplete"
    incomplete.mkdir()

    target = write_run_manifest(_manifest(), incomplete)
    content = json.loads(target.read_text(encoding="utf-8"))

    assert target.name == MANIFEST_FILENAME
    assert content["status"] == "complete"
    assert content["git_commit"] == "a" * 40
    assert "patient_identifier" not in content

    with pytest.raises(FileExistsError):
        write_run_manifest(_manifest(), incomplete)


def test_current_software_versions_are_populated() -> None:
    versions = current_software_versions()

    assert versions.python
    assert versions.polars
    assert versions.duckdb
    assert versions.pydantic
