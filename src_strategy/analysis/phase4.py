"""Concrete Template Method implementation for the Phase 4 CoreAnalysis port."""

from dataclasses import dataclass
from pathlib import Path

import polars as pl

from .category_tables import (
    build_category_counts,
    build_category_crosstabs,
    build_poa_status_counts,
)
from .cohort import build_analysis_cohort
from .config import (
    SEPSIS_ENCOUNTER_FILENAME,
    VASOPRESSOR_EVIDENCE_FILENAME,
    Phase4AnalysisConfig,
    phase4_analysis_config,
)
from .outcome_tables import (
    build_arrival_to_sepsis_summary,
    build_length_of_stay_agreement,
    build_length_of_stay_by_category,
    build_mortality_agreement,
    build_mortality_by_category,
)
from .pipeline import AnalysisPipeline
from .vasopressor_tables import (
    build_first_vasopressor_table,
    build_vasopressor_window_category_counts,
    build_vasopressor_window_crosstabs,
)


@dataclass(frozen=True)
class Phase4AnalysisInputs:
    """The two versioned clinical tables required by current analyses."""

    sepsis_encounters: pl.DataFrame
    vasopressor_evidence: pl.DataFrame


class Phase4CoreAnalysisPipeline(AnalysisPipeline):
    """Reproduce active CoreAnalysis questions as aggregate Parquet tables."""

    def __init__(
        self,
        clinical_run_dir: Path,
        output_dir: Path,
        config: Phase4AnalysisConfig = phase4_analysis_config,
    ) -> None:
        super().__init__(clinical_run_dir, output_dir, config)

    def load_inputs(self) -> Phase4AnalysisInputs:
        return Phase4AnalysisInputs(
            sepsis_encounters=pl.read_parquet(
                self.clinical_run_dir / SEPSIS_ENCOUNTER_FILENAME
            ),
            vasopressor_evidence=pl.read_parquet(
                self.clinical_run_dir / VASOPRESSOR_EVIDENCE_FILENAME
            ),
        )

    def prepare_cohort(self, inputs: Phase4AnalysisInputs) -> pl.DataFrame:
        return build_analysis_cohort(inputs.sepsis_encounters, self.config)

    def build_tables(
        self,
        inputs: Phase4AnalysisInputs,
        cohort: pl.DataFrame,
    ) -> dict[str, pl.DataFrame]:
        first_vasopressor = build_first_vasopressor_table(
            cohort,
            inputs.vasopressor_evidence,
        )
        return {
            "category_counts": build_category_counts(cohort, self.config),
            "poa_status_counts": build_poa_status_counts(cohort, self.config),
            "category_crosstabs": build_category_crosstabs(
                cohort,
                self.config,
            ),
            "mortality_by_category": build_mortality_by_category(
                cohort,
                self.config,
            ),
            "arrival_to_sepsis_summary": build_arrival_to_sepsis_summary(
                cohort,
                self.config,
            ),
            "length_of_stay_by_category": build_length_of_stay_by_category(
                cohort,
                self.config,
            ),
            "length_of_stay_agreement": build_length_of_stay_agreement(
                cohort,
                self.config,
            ),
            "mortality_agreement": build_mortality_agreement(cohort),
            "vasopressor_window_category_counts": (
                build_vasopressor_window_category_counts(
                    first_vasopressor,
                    self.config,
                )
            ),
            "vasopressor_window_crosstabs": (
                build_vasopressor_window_crosstabs(
                    first_vasopressor,
                    self.config,
                )
            ),
        }
