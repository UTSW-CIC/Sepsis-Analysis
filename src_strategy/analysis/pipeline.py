"""Template Method for the stable analysis workflow."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import polars as pl

from .config import Phase4AnalysisConfig
from .io import (
    validate_aggregate_tables,
    validate_completed_clinical_run,
    write_analysis_bundle,
)


class AnalysisPipeline(ABC):
    """Own the invariant workflow while subclasses provide analysis details."""

    def __init__(
        self,
        clinical_run_dir: Path,
        output_dir: Path,
        config: Phase4AnalysisConfig,
    ) -> None:
        self.clinical_run_dir = clinical_run_dir
        self.output_dir = output_dir
        self.config = config

    def run(self) -> None:
        """Execute the stable validate → load → analyze → publish workflow."""
        clinical_manifest = validate_completed_clinical_run(
            self.clinical_run_dir
        )
        inputs = self.load_inputs()
        cohort = self.prepare_cohort(inputs)
        tables = self.build_tables(inputs, cohort)
        validate_aggregate_tables(tables, self.config)
        write_analysis_bundle(
            tables=tables,
            output_dir=self.output_dir,
            clinical_run_dir=self.clinical_run_dir,
            clinical_manifest=clinical_manifest,
            config=self.config,
        )

    @abstractmethod
    def load_inputs(self) -> Any:
        """Load only the clinical tables required by the concrete analysis."""

    @abstractmethod
    def prepare_cohort(self, inputs: Any) -> pl.DataFrame:
        """Return the concrete analysis cohort."""

    @abstractmethod
    def build_tables(
        self,
        inputs: Any,
        cohort: pl.DataFrame,
    ) -> dict[str, pl.DataFrame]:
        """Return patient-neutral aggregate output tables."""
