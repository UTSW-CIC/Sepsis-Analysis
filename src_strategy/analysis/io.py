"""Clinical-run validation and aggregate analysis-bundle publication."""

import json
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

from src_strategy.run_manifest import (
    ClinicalRunManifest,
    describe_output_table,
    file_sha256,
)

from .config import (
    ENCOUNTER_COL,
    SEPSIS_ENCOUNTER_FILENAME,
    VASOPRESSOR_EVIDENCE_FILENAME,
    Phase4AnalysisConfig,
)


def validate_completed_clinical_run(
    clinical_run_dir: Path,
) -> ClinicalRunManifest:
    """Validate run completion, provenance, and the two required inputs."""
    if not clinical_run_dir.is_dir():
        raise FileNotFoundError(
            f"Clinical-run directory does not exist: {clinical_run_dir}"
        )
    if clinical_run_dir.name.endswith(".incomplete"):
        raise ValueError("Analysis cannot consume an incomplete clinical run")
    if not (clinical_run_dir / "_SUCCESS").is_file():
        raise FileNotFoundError("Clinical run is missing _SUCCESS")

    manifest_path = clinical_run_dir / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError("Clinical run is missing manifest.json")
    manifest = ClinicalRunManifest.model_validate_json(
        manifest_path.read_text(encoding="utf-8")
    )
    manifest_tables = {table.filename: table for table in manifest.output_tables}

    for filename in [SEPSIS_ENCOUNTER_FILENAME, VASOPRESSOR_EVIDENCE_FILENAME]:
        if filename not in manifest_tables:
            raise ValueError(
                f"Clinical-run manifest does not declare required table {filename!r}"
            )
        path = clinical_run_dir / filename
        if not path.is_file():
            raise FileNotFoundError(f"Clinical run is missing {filename}")
        artifact = manifest_tables[filename]
        if path.stat().st_size != artifact.size_bytes:
            raise ValueError(f"Clinical-run table size differs from manifest: {filename}")
        if file_sha256(path) != artifact.sha256:
            raise ValueError(f"Clinical-run table hash differs from manifest: {filename}")
        actual_schema = {
            name: str(dtype) for name, dtype in pl.read_parquet_schema(path).items()
        }
        if actual_schema != artifact.table_schema:
            raise ValueError(
                f"Clinical-run table schema differs from manifest: {filename}"
            )

    return manifest


def validate_aggregate_tables(
    tables: dict[str, pl.DataFrame],
    config: Phase4AnalysisConfig,
) -> None:
    """Require the approved table inventory and patient-neutral output grain."""
    if set(tables) != set(config.output_filenames):
        missing = sorted(set(config.output_filenames).difference(tables))
        unexpected = sorted(set(tables).difference(config.output_filenames))
        raise ValueError(
            "Analysis table inventory differs from configuration; "
            f"missing={missing}, unexpected={unexpected}"
        )
    containing_identifiers = [
        table_name
        for table_name, dataframe in tables.items()
        if ENCOUNTER_COL in dataframe.columns
    ]
    if containing_identifiers:
        raise ValueError(
            "Aggregate analysis tables contain encounter identifiers: "
            f"{containing_identifiers}"
        )


def write_analysis_bundle(
    tables: dict[str, pl.DataFrame],
    output_dir: Path,
    clinical_run_dir: Path,
    clinical_manifest: ClinicalRunManifest,
    config: Phase4AnalysisConfig,
) -> None:
    """Write aggregate tables and patient-neutral provenance without overwrite."""
    output_dir.mkdir(parents=True, exist_ok=True)
    if any(output_dir.iterdir()):
        raise FileExistsError(
            f"Analysis output directory must be empty: {output_dir}"
        )

    output_artifacts = []
    for table_name, dataframe in tables.items():
        filename = config.output_filenames[table_name]
        path = output_dir / filename
        dataframe.write_parquet(path)
        output_artifacts.append(
            describe_output_table(path, dataframe).model_dump(mode="json")
        )

    analysis_manifest = {
        "analysis_schema_version": "1",
        "status": "complete",
        "created_at_utc": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        "source_clinical_run": {
            "directory_name": clinical_run_dir.name,
            "dataset_version": clinical_manifest.dataset_version,
            "algorithm_variant": clinical_manifest.algorithm_variant,
            "run_timestamp_utc": clinical_manifest.run_timestamp_utc,
            "git_commit": clinical_manifest.git_commit,
            "configuration_sha256": clinical_manifest.configuration_sha256,
            "clinical_definition_version": (
                clinical_manifest.clinical_definition_version
            ),
        },
        "analysis_parameters": config.manifest_parameters(),
        "output_tables": output_artifacts,
    }
    manifest_path = output_dir / "analysis_manifest.json"
    manifest_path.write_text(
        json.dumps(analysis_manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "_SUCCESS").touch(exist_ok=False)
