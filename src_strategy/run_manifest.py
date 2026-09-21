"""Strict, patient-neutral provenance manifest for one clinical run."""

import hashlib
import json
from pathlib import Path
import platform
from typing import Any, Literal

import duckdb
import polars as pl
import pydantic
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


MANIFEST_FILENAME = "manifest.json"
_SHA256_PATTERN = r"^[0-9a-f]{64}$"
_GIT_COMMIT_PATTERN = r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$"
_RUN_TIMESTAMP_PATTERN = r"^\d{8}T\d{6}Z$"
_SEMANTIC_LABEL_PATTERN = r"^[a-z0-9][a-z0-9._-]*$"


class StrictManifestModel(BaseModel):
    """Reject unreviewed manifest fields instead of silently accepting them."""

    model_config = ConfigDict(extra="forbid")


class CachedInputArtifact(StrictManifestModel):
    filename: str
    size_bytes: int = Field(ge=0)
    sha256: str = Field(pattern=_SHA256_PATTERN)

    @field_validator("filename")
    @classmethod
    def validate_filename(cls, value: str) -> str:
        if not value or Path(value).name != value:
            raise ValueError("Artifact filename must be a basename")
        return value


class OutputTableArtifact(CachedInputArtifact):
    row_count: int = Field(ge=0)
    table_schema: dict[str, str]


class SoftwareVersions(StrictManifestModel):
    python: str
    polars: str
    duckdb: str
    pydantic: str


class ValidationResult(StrictManifestModel):
    name: str = Field(min_length=1)
    passed: bool


class ClinicalRunManifest(StrictManifestModel):
    manifest_schema_version: str = "1"
    status: Literal["complete"] = "complete"
    dataset_version: str = Field(pattern=_SEMANTIC_LABEL_PATTERN)
    algorithm_variant: str = Field(pattern=_SEMANTIC_LABEL_PATTERN)
    run_timestamp_utc: str = Field(pattern=_RUN_TIMESTAMP_PATTERN)
    git_commit: str = Field(pattern=_GIT_COMMIT_PATTERN)
    git_branch: str | None
    git_worktree_clean: bool
    configuration_sha256: str = Field(pattern=_SHA256_PATTERN)
    configuration_snapshot: dict[str, Any]
    clinical_definition_version: str = Field(min_length=1)
    cached_inputs: list[CachedInputArtifact] = Field(min_length=1)
    output_tables: list[OutputTableArtifact] = Field(min_length=1)
    software_versions: SoftwareVersions
    validations: list[ValidationResult] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_completed_run(self) -> "ClinicalRunManifest":
        if not self.git_worktree_clean:
            raise ValueError("Completed versioned runs require clean Git state")
        failed = [result.name for result in self.validations if not result.passed]
        if failed:
            raise ValueError(
                "Completed run manifest cannot contain failed validations"
            )
        return self


def file_sha256(path: str | Path) -> str:
    """Hash a file without loading the complete artifact into memory."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as artifact:
        for chunk in iter(lambda: artifact.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def describe_cached_input(path: str | Path) -> CachedInputArtifact:
    """Return patient-neutral identity metadata for one cached input."""
    artifact = Path(path)
    if not artifact.is_file():
        raise FileNotFoundError(f"Cached input does not exist: {artifact}")
    return CachedInputArtifact(
        filename=artifact.name,
        size_bytes=artifact.stat().st_size,
        sha256=file_sha256(artifact),
    )


def describe_output_table(
    path: str | Path,
    dataframe: pl.DataFrame,
) -> OutputTableArtifact:
    """Return file and dataframe metadata without including row-level data."""
    artifact = Path(path)
    if not artifact.is_file():
        raise FileNotFoundError(f"Output table does not exist: {artifact}")
    return OutputTableArtifact(
        filename=artifact.name,
        size_bytes=artifact.stat().st_size,
        sha256=file_sha256(artifact),
        row_count=dataframe.height,
        table_schema={
            name: str(dtype) for name, dtype in dataframe.schema.items()
        },
    )


def current_software_versions() -> SoftwareVersions:
    """Capture the runtime versions needed to investigate reproducibility."""
    return SoftwareVersions(
        python=platform.python_version(),
        polars=pl.__version__,
        duckdb=duckdb.__version__,
        pydantic=pydantic.__version__,
    )


def write_run_manifest(
    manifest: ClinicalRunManifest,
    incomplete_run_directory: str | Path,
) -> Path:
    """Write a deterministic manifest without replacing an existing one."""
    directory = Path(incomplete_run_directory)
    if not directory.is_dir():
        raise FileNotFoundError(
            f"Incomplete run directory does not exist: {directory}"
        )
    target = directory / MANIFEST_FILENAME
    if target.exists():
        raise FileExistsError(f"Run manifest already exists: {target}")

    serialized = json.dumps(
        manifest.model_dump(mode="json"),
        sort_keys=True,
        indent=2,
        ensure_ascii=False,
        allow_nan=False,
    )
    target.write_text(f"{serialized}\n", encoding="utf-8")
    return target
