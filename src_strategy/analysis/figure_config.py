"""Presentation settings and output names for Phase 4 analysis figures."""

from dataclasses import dataclass, field


NPOA_COLOR = "#66b2ff"
POA_COLOR = "#003d99"
BILLING_COLOR = "#DD8452"
CALCULATED_COLOR = "#4C72B0"
MATCH_COLOR = "#917B6F"
DEATH_NO_COLOR = "#003d99"
DEATH_YES_COLOR = "#d62728"
ICU_NO_COLOR = "#4C72B0"
ICU_YES_COLOR = "#DD8452"
PATHWAY_ORGAN_COLOR = "#4C72B0"
PATHWAY_VASOPRESSOR_COLOR = "#DD8452"
PATHWAY_BOTH_COLOR = "#55A868"
PATHWAY_NEITHER_COLOR = "#C7C7C7"


@dataclass(frozen=True)
class Phase4FigureConfig:
    """Stable figure inventory and shared rendering settings."""

    dpi: int = 200
    category_order: tuple[str, ...] = (
        "NPOA-1",
        "NPOA-2",
        "NPOA-3",
        "POA-1",
        "POA-2",
        "POA-3",
    )
    source_colors: dict[str, str] = field(
        default_factory=lambda: {
            "billed": BILLING_COLOR,
            "calculated_arrival_plus_48h": CALCULATED_COLOR,
            "calculated_inpatient_admission": POA_COLOR,
        }
    )
    source_labels: dict[str, str] = field(
        default_factory=lambda: {
            "billed": "Billing Categorization",
            "calculated_arrival_plus_48h": "Arrival + 48 Hours",
            "calculated_inpatient_admission": "Inpatient Admission Time",
        }
    )
    figure_filenames: tuple[str, ...] = (
        "cohortbyComputedFromAnalysisScript.png",
        "cohortbyBillingFromAnalysisScript.png",
        "dist_mortality_rate_flag.png",
        "mortality_rate_computed_vs_billed_severity_heatmap.png",
        "icu_encounter_count_computed_vs_billed_category_heatmap.png",
        "icu_encounter_count_computed_vs_billed_severity_heatmap.png",
        "icu_status_computed_severity_diverging_barplot.png",
        "icu_status_billed_severity_diverging_barplot.png",
        "icu_status_computed_category_diverging_barplot.png",
        "icu_status_billed_category_diverging_barplot.png",
        "icu_status_sepsis3_by_pathway_diverging_barplot.png",
        "dist_48hrs_arrival.png",
        "dist_24hrs_admission.png",
        "heatmap_48hrs_arrival.png",
        "heatmap_24hrs_admission.png",
        "sepsis_heatmap_arrival.png",
        "sepsis_heatmap_inpatient.png",
        "sepsis_heatmap_arrival_with_totals.png",
        "sepsis_heatmap_inpatient_with_totals.png",
        "sepsis_category_comparison_arrival_inpatient_aggregate_poa.png",
        "sepsis_time_iqr_median_range_arrival.png",
        "los_distribution_arrival_sepsis1.png",
        "los_distribution_arrival_sepsis2.png",
        "los_distribution_arrival_sepsis3.png",
        "dist_los_arrival.png",
        "los_distribution_arrival_poa3.png",
        "los_distribution_arrival_npoa3.png",
        "death_flag_distribution_ratio_poa3.png",
        "death_flag_distribution_ratio_poa2.png",
        "death_flag_distribution_ratio_npoa3.png",
        "death_flag_distribution_ratio_sepsis3.png",
        "death_flag_distribution_ratio_sepsis2.png",
        "death_flag_distribution_ratio_sepsis1.png",
    )


phase4_figure_config = Phase4FigureConfig()
