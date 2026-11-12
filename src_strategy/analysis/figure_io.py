"""Validate aggregate analysis bundles and publish figure bundles."""

import json
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

from src_strategy.run_manifest import file_sha256

from .config import Phase4AnalysisConfig
from .figure_config import Phase4FigureConfig


def load_completed_analysis_bundle(
    analysis_dir: Path,
    analysis_config: Phase4AnalysisConfig,
) -> tuple[dict[str, object], dict[str, pl.DataFrame]]:
    """Validate and load all aggregate tables required for figures."""
    if not analysis_dir.is_dir():
        raise FileNotFoundError(f"Analysis directory does not exist: {analysis_dir}")
    if not (analysis_dir / "_SUCCESS").is_file():
        raise FileNotFoundError("Analysis bundle is missing _SUCCESS")
    manifest_path = analysis_dir / "analysis_manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError("Analysis bundle is missing analysis_manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("status") != "complete":
        raise ValueError("Analysis manifest status must be 'complete'")

    declared = {
        artifact["filename"]: artifact
        for artifact in manifest.get("output_tables", [])
    }
    tables = {}
    for table_name, filename in analysis_config.output_filenames.items():
        if filename not in declared:
            raise ValueError(f"Analysis manifest does not declare {filename!r}")
        path = analysis_dir / filename
        if not path.is_file():
            raise FileNotFoundError(f"Analysis bundle is missing {filename}")
        artifact = declared[filename]
        if path.stat().st_size != artifact["size_bytes"]:
            raise ValueError(f"Analysis table size differs from manifest: {filename}")
        if file_sha256(path) != artifact["sha256"]:
            raise ValueError(f"Analysis table hash differs from manifest: {filename}")
        actual_schema = {
            name: str(dtype) for name, dtype in pl.read_parquet_schema(path).items()
        }
        if actual_schema != artifact["table_schema"]:
            raise ValueError(f"Analysis table schema differs from manifest: {filename}")
        dataframe = pl.read_parquet(path)
        if dataframe.height != artifact["row_count"]:
            raise ValueError(
                f"Analysis table row count differs from manifest: {filename}"
            )
        tables[table_name] = dataframe
    return manifest, tables


def prepare_figure_output_dir(output_dir: Path) -> None:
    """Require a new or empty directory so figures are never overwritten."""
    output_dir.mkdir(parents=True, exist_ok=True)
    if any(output_dir.iterdir()):
        raise FileExistsError(f"Figure output directory must be empty: {output_dir}")


def write_figure_manifest(
    *,
    analysis_dir: Path,
    analysis_manifest: dict[str, object],
    output_dir: Path,
    config: Phase4FigureConfig,
) -> None:
    """Record patient-neutral provenance after every configured figure exists."""
    artifacts = []
    for filename in config.figure_filenames:
        path = output_dir / filename
        if not path.is_file():
            raise FileNotFoundError(f"Configured figure was not created: {filename}")
        artifacts.append(
            {
                "filename": filename,
                "size_bytes": path.stat().st_size,
                "sha256": file_sha256(path),
            }
        )

    figure_manifest = {
        "figure_schema_version": "1",
        "status": "complete",
        "created_at_utc": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        "source_analysis": {
            "directory_name": analysis_dir.name,
            "manifest_sha256": file_sha256(
                analysis_dir / "analysis_manifest.json"
            ),
            "analysis_schema_version": analysis_manifest.get(
                "analysis_schema_version"
            ),
            "source_clinical_run": analysis_manifest.get("source_clinical_run"),
        },
        "figure_inventory": {
            "legacy_equivalent_count": 19,
            "aggregate_interval_replacement_count": 6,
            "interval_encoding": {
                "range": (
                    "thin line (minimum to maximum after analysis filtering)"
                ),
                "iqr": "thick line",
                "median": "point",
            },
        },
        "figure_count": len(artifacts),
        "figures": artifacts,
    }
    (output_dir / "figure_manifest.json").write_text(
        json.dumps(figure_manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "_SUCCESS").touch(exist_ok=False)
