"""Safety checks and metadata helpers for immutable clinical runs."""

from collections.abc import Mapping
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Any

from pydantic import BaseModel


CONFIGURATION_HASH_PREFIX_LENGTH = 12
GIT_COMMIT_PREFIX_LENGTH = 12
RUN_SUCCESS_MARKER = "_SUCCESS"

_FULL_GIT_COMMIT_PATTERN = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_FULL_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_RUN_TIMESTAMP_PATTERN = re.compile(r"^\d{8}T\d{6}Z$")
_SAFE_PATH_COMPONENT_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


class RunMode(str, Enum):
    """Allowed clinical-pipeline execution modes."""

    DEVELOPMENT = "development"
    VERSIONED = "versioned"


@dataclass(frozen=True)
class RunBundlePaths:
    """Final and in-progress locations for one immutable run bundle."""

    final: Path
    incomplete: Path


def canonical_configuration_json(
    config_sections: Mapping[str, BaseModel | Mapping[str, Any]],
) -> str:
    """Serialize explicitly selected result-affecting configuration."""
    serialized_sections: dict[str, Any] = {}
    for section_name, section in config_sections.items():
        if isinstance(section, BaseModel):
            serialized_sections[section_name] = section.model_dump(mode="json")
        else:
            serialized_sections[section_name] = dict(section)

    try:
        return json.dumps(
            serialized_sections,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise ValueError(
            "Result-affecting configuration must be JSON serializable"
        ) from error


def configuration_sha256(
    config_sections: Mapping[str, BaseModel | Mapping[str, Any]],
) -> str:
    """Return the reproducible SHA-256 configuration fingerprint."""
    canonical_json = canonical_configuration_json(config_sections)
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def abbreviated_configuration_hash(configuration_hash: str) -> str:
    """Return the approved run-directory representation of a full hash."""
    if not _FULL_SHA256_PATTERN.fullmatch(configuration_hash):
        raise ValueError("Configuration hash must be a full SHA-256 digest")
    return configuration_hash[:CONFIGURATION_HASH_PREFIX_LENGTH]


def git_commit_sha(repository_path: str | Path) -> str:
    """Return the full commit hash for the repository's current HEAD."""
    repository = Path(repository_path).resolve()
    result = subprocess.run(
        ["git", "-C", str(repository), "rev-parse", "--verify", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    commit = result.stdout.strip().lower()
    if result.returncode != 0 or not _FULL_GIT_COMMIT_PATTERN.fullmatch(commit):
        raise RuntimeError("Unable to identify the current Git commit")
    return commit


def git_branch_name(repository_path: str | Path) -> str | None:
    """Return the current branch, or ``None`` for a detached HEAD."""
    repository = Path(repository_path).resolve()
    result = subprocess.run(
        ["git", "-C", str(repository), "symbolic-ref", "--short", "-q", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 1:
        return None
    branch = result.stdout.strip()
    if result.returncode != 0 or not branch:
        raise RuntimeError("Unable to identify the current Git branch")
    return branch


def abbreviated_git_commit(commit: str) -> str:
    """Return the approved run-directory representation of a full commit."""
    normalized = commit.lower()
    if not _FULL_GIT_COMMIT_PATTERN.fullmatch(normalized):
        raise ValueError("Git commit must be a full SHA-1 or SHA-256 hash")
    return normalized[:GIT_COMMIT_PREFIX_LENGTH]


def utc_run_timestamp(run_time: datetime | None = None) -> str:
    """Return an unambiguous second-resolution UTC run timestamp."""
    timestamp = run_time or datetime.now(timezone.utc)
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("Run timestamp must be timezone-aware")
    return timestamp.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def build_run_relative_path(
    *,
    dataset_version: str,
    algorithm_variant: str,
    run_timestamp: str,
    git_commit: str,
    configuration_hash: str,
) -> Path:
    """Build, but do not create, the approved immutable run path."""
    for name, value in {
        "dataset_version": dataset_version,
        "algorithm_variant": algorithm_variant,
    }.items():
        if not _SAFE_PATH_COMPONENT_PATTERN.fullmatch(value):
            raise ValueError(f"{name} is not a safe path component")
    if not _RUN_TIMESTAMP_PATTERN.fullmatch(run_timestamp):
        raise ValueError("Run timestamp must use YYYYMMDDTHHMMSSZ format")

    directory_name = (
        f"{run_timestamp}__{abbreviated_git_commit(git_commit)}"
        f"__cfg-{abbreviated_configuration_hash(configuration_hash)}"
    )
    return Path(dataset_version) / algorithm_variant / directory_name


def validate_output_table_names(filenames: Iterable[str]) -> None:
    """Require stable bundle-internal parquet basenames without versions."""
    names = list(filenames)
    if len(names) != len(set(names)):
        raise ValueError("Clinical output table filenames must be unique")
    invalid = [
        name
        for name in names
        if Path(name).name != name
        or not re.fullmatch(r"[a-z0-9][a-z0-9_]*\.parquet", name)
        or re.search(r"_v\d+\.parquet$", name)
    ]
    if invalid:
        raise ValueError(
            "Clinical output filenames must be stable parquet basenames "
            "without embedded version suffixes"
        )


def create_incomplete_run_bundle(
    clinical_runs_root: str | Path,
    relative_run_path: str | Path,
) -> RunBundlePaths:
    """Create a new in-progress bundle without replacing existing paths."""
    root = Path(clinical_runs_root).resolve()
    relative = Path(relative_run_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("Run path must be relative and cannot traverse parents")

    final = root / relative
    incomplete = final.with_name(f"{final.name}.incomplete")
    if final.exists():
        raise FileExistsError(f"Completed run already exists: {final}")
    if incomplete.exists():
        raise FileExistsError(f"Incomplete run already exists: {incomplete}")

    incomplete.parent.mkdir(parents=True, exist_ok=True)
    incomplete.mkdir(exist_ok=False)
    return RunBundlePaths(final=final, incomplete=incomplete)


def finalize_run_bundle(paths: RunBundlePaths) -> Path:
    """Mark an in-progress bundle complete and atomically publish it."""
    if paths.incomplete.parent != paths.final.parent:
        raise ValueError("Incomplete and final run paths must share a parent")
    if not paths.incomplete.is_dir():
        raise FileNotFoundError(
            f"Incomplete run directory does not exist: {paths.incomplete}"
        )
    if paths.final.exists():
        raise FileExistsError(f"Completed run already exists: {paths.final}")

    (paths.incomplete / RUN_SUCCESS_MARKER).touch(exist_ok=False)
    paths.incomplete.rename(paths.final)
    return paths.final


def require_clean_git_worktree(repository_path: str | Path) -> None:
    """Stop a versioned clinical run when Git has pending changes."""
    repository = Path(repository_path).resolve()
    result = subprocess.run(
        [
            "git",
            "-C",
            str(repository),
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "Unable to verify that the Git working tree is clean. "
            "The clinical run was not started."
        )

    pending_entries = [
        line for line in result.stdout.splitlines() if line.strip()
    ]
    if pending_entries:
        raise RuntimeError(
            "Refusing to create a versioned clinical run from a dirty Git "
            f"working tree ({len(pending_entries)} pending entries). "
            "Review `git status --short` and commit the intended changes "
            "before running the pipeline."
        )


def enforce_run_mode_preconditions(
    run_mode: RunMode,
    repository_path: str | Path,
) -> None:
    """Apply safeguards required before the selected execution mode starts."""
    if run_mode is RunMode.VERSIONED:
        require_clean_git_worktree(repository_path)
