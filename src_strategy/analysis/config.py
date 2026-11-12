"""Configuration and shared column names for Phase 4 analysis."""

from dataclasses import dataclass, field


ENCOUNTER_COL = "EncounterEpicCsn"
BILLED_CATEGORY_COL = "Sepsis_Category"
CALCULATED_CATEGORY_COL = "calculated_sepsis_category"
CALCULATED_SEVERITY_COL = "calculated_sepsis_severity"
CALCULATED_POA_STATUS_COL = "calculated_poa_status"
FIRST_SEPSIS_DT_COL = "first_sepsis_dt"
ARRIVAL_COL = "Arrival_Instant"
INPATIENT_ADMISSION_COL = "InpatientAdmissionInstant"
LOS_COL = "LengthOfStayInDays"
DEATH_COL = "Death_Flag"

INPATIENT_CATEGORY_COL = "calculated_inpatient_category"
INPATIENT_POA_STATUS_COL = "calculated_inpatient_poa_status"
BILLED_SEVERITY_COL = "billed_sepsis_severity"
BILLED_POA_STATUS_COL = "billed_poa_status"
ARRIVAL_TO_SEPSIS_HOURS_COL = "arrival_to_sepsis_hours"

SEPSIS_ENCOUNTER_FILENAME = "df_sepsis_encounters.parquet"
VASOPRESSOR_EVIDENCE_FILENAME = "df_vasopressor_evidence.parquet"


@dataclass(frozen=True)
class Phase4AnalysisConfig:
    """Approved cohort, timing, and output settings for the first analysis slice."""

    sepsis_categories: tuple[str, ...] = (
        "NPOA-1",
        "NPOA-2",
        "NPOA-3",
        "POA-1",
        "POA-2",
        "POA-3",
    )
    poa_statuses: tuple[str, ...] = ("NPOA", "POA")
    arrival_poa_boundary_hours: int = 48
    inpatient_poa_boundary_hours: int = 0
    distribution_upper_quantile: float = 0.99
    arrival_to_sepsis_positive_hours_only: bool = True
    arrival_vasopressor_window_hours: int = 48
    inpatient_vasopressor_window_hours: int = 24
    output_filenames: dict[str, str] = field(
        default_factory=lambda: {
            "category_counts": "category_counts.parquet",
            "poa_status_counts": "poa_status_counts.parquet",
            "category_crosstabs": "category_crosstabs.parquet",
            "mortality_by_category": "mortality_by_category.parquet",
            "arrival_to_sepsis_summary": "arrival_to_sepsis_summary.parquet",
            "length_of_stay_by_category": (
                "length_of_stay_by_category.parquet"
            ),
            "length_of_stay_agreement": "length_of_stay_agreement.parquet",
            "mortality_agreement": "mortality_agreement.parquet",
            "vasopressor_window_category_counts": (
                "vasopressor_window_category_counts.parquet"
            ),
            "vasopressor_window_crosstabs": (
                "vasopressor_window_crosstabs.parquet"
            ),
        }
    )

    def manifest_parameters(self) -> dict[str, object]:
        """Return patient-neutral settings recorded with every analysis bundle."""
        return {
            "calculated_no_sepsis_included": False,
            "billed_upoa_included": False,
            "arrival_poa_boundary_hours": self.arrival_poa_boundary_hours,
            "inpatient_poa_boundary_hours": self.inpatient_poa_boundary_hours,
            "distribution_upper_quantile": self.distribution_upper_quantile,
            "distribution_upper_boundary_inclusive": False,
            "arrival_to_sepsis_positive_hours_only": (
                self.arrival_to_sepsis_positive_hours_only
            ),
            "vasopressor_evidence": "qualifying Phase 4 administrations",
            "arrival_vasopressor_window_hours": (
                self.arrival_vasopressor_window_hours
            ),
            "inpatient_vasopressor_window_hours": (
                self.inpatient_vasopressor_window_hours
            ),
            "vasopressor_window_upper_boundary_inclusive": False,
        }


phase4_analysis_config = Phase4AnalysisConfig()
