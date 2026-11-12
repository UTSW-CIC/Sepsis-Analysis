"""Compose all Phase 4 figures from a completed aggregate analysis bundle."""

from pathlib import Path

import polars as pl

from .category_figures import (
    plot_category_distribution,
    plot_crosstab_heatmap,
    plot_mortality_by_category,
    plot_poa_status_comparison,
    plot_single_category_counts,
)
from .config import Phase4AnalysisConfig, phase4_analysis_config
from .figure_config import Phase4FigureConfig, phase4_figure_config
from .figure_io import (
    load_completed_analysis_bundle,
    prepare_figure_output_dir,
    write_figure_manifest,
)
from .outcome_figures import (
    plot_los_agreement_intervals,
    plot_los_median_by_category,
    plot_mortality_agreement,
    plot_time_summary_intervals,
)


class Phase4FigurePipeline:
    """Render the approved 19 legacy and six replacement figures."""

    def __init__(
        self,
        analysis_dir: Path,
        output_dir: Path,
        analysis_config: Phase4AnalysisConfig = phase4_analysis_config,
        figure_config: Phase4FigureConfig = phase4_figure_config,
    ) -> None:
        self.analysis_dir = analysis_dir
        self.output_dir = output_dir
        self.analysis_config = analysis_config
        self.figure_config = figure_config

    def run(self) -> None:
        prepare_figure_output_dir(self.output_dir)
        analysis_manifest, tables = load_completed_analysis_bundle(
            self.analysis_dir,
            self.analysis_config,
        )
        self._render_figures(tables)
        write_figure_manifest(
            analysis_dir=self.analysis_dir,
            analysis_manifest=analysis_manifest,
            output_dir=self.output_dir,
            config=self.figure_config,
        )

    def _render_figures(self, tables: dict[str, pl.DataFrame]) -> None:
        self._render_category_figures(tables)
        self._render_vasopressor_figures(tables)
        self._render_outcome_figures(tables)

    def _render_category_figures(
        self,
        tables: dict[str, pl.DataFrame],
    ) -> None:
        counts = tables["category_counts"]
        plot_single_category_counts(
            counts,
            source="calculated_arrival_plus_48h",
            title="Cohort by Algorithm Categorization",
            filename="cohortbyComputedFromAnalysisScript.png",
            output_dir=self.output_dir,
            config=self.figure_config,
        )
        plot_single_category_counts(
            counts,
            source="billed",
            title="Cohort by Billing Categorization",
            filename="cohortbyBillingFromAnalysisScript.png",
            output_dir=self.output_dir,
            config=self.figure_config,
        )
        plot_mortality_by_category(
            tables["mortality_by_category"],
            output_dir=self.output_dir,
            config=self.figure_config,
        )

        crosstabs = tables["category_crosstabs"]
        for reference, title, plain_filename, totals_filename in [
            (
                "arrival_plus_48h",
                "Computed Category vs Billing Category — Arrival + 48 Hours",
                "sepsis_heatmap_arrival.png",
                "sepsis_heatmap_arrival_with_totals.png",
            ),
            (
                "inpatient_admission",
                "Computed Category vs Billing Category — Inpatient Admission",
                "sepsis_heatmap_inpatient.png",
                "sepsis_heatmap_inpatient_with_totals.png",
            ),
        ]:
            subset = crosstabs.filter(
                pl.col("calculated_reference") == reference
            )
            plot_crosstab_heatmap(
                subset,
                title=title,
                filename=plain_filename,
                output_dir=self.output_dir,
                config=self.figure_config,
                show_totals=False,
            )
            plot_crosstab_heatmap(
                subset,
                title=title,
                filename=totals_filename,
                output_dir=self.output_dir,
                config=self.figure_config,
                show_totals=True,
            )

        plot_poa_status_comparison(
            tables["poa_status_counts"],
            output_dir=self.output_dir,
            config=self.figure_config,
        )

    def _render_vasopressor_figures(
        self,
        tables: dict[str, pl.DataFrame],
    ) -> None:
        counts = tables["vasopressor_window_category_counts"]
        crosstabs = tables["vasopressor_window_crosstabs"]
        for window, title, distribution_filename, heatmap_filename in [
            (
                "within_48h_of_arrival",
                "Pressors Within 48 Hours of Arrival",
                "dist_48hrs_arrival.png",
                "heatmap_48hrs_arrival.png",
            ),
            (
                "within_24h_of_inpatient_admission",
                "Pressors Within 24 Hours of Admission",
                "dist_24hrs_admission.png",
                "heatmap_24hrs_admission.png",
            ),
        ]:
            plot_category_distribution(
                counts.filter(pl.col("vasopressor_window") == window),
                title=f"Billing vs Computed Sepsis Category\n{title}",
                filename=distribution_filename,
                output_dir=self.output_dir,
                config=self.figure_config,
            )
            plot_crosstab_heatmap(
                crosstabs.filter(pl.col("vasopressor_window") == window),
                title=f"Computed Category vs Billing Category — {title}",
                filename=heatmap_filename,
                output_dir=self.output_dir,
                config=self.figure_config,
                show_totals=True,
            )

    def _render_outcome_figures(
        self,
        tables: dict[str, pl.DataFrame],
    ) -> None:
        plot_time_summary_intervals(
            tables["arrival_to_sepsis_summary"],
            output_dir=self.output_dir,
            config=self.figure_config,
        )

        los_agreement = tables["length_of_stay_agreement"]
        for comparison, target, filename in [
            ("severity", "1", "los_iqr_median_range_arrival_sepsis1.png"),
            ("severity", "2", "los_iqr_median_range_arrival_sepsis2.png"),
            ("severity", "3", "los_iqr_median_range_arrival_sepsis3.png"),
            ("category", "POA-3", "los_iqr_median_range_arrival_poa3.png"),
            ("category", "NPOA-3", "los_iqr_median_range_arrival_npoa3.png"),
        ]:
            plot_los_agreement_intervals(
                los_agreement,
                comparison=comparison,
                target=target,
                filename=filename,
                output_dir=self.output_dir,
                config=self.figure_config,
            )
        plot_los_median_by_category(
            tables["length_of_stay_by_category"],
            output_dir=self.output_dir,
            config=self.figure_config,
        )

        mortality = tables["mortality_agreement"]
        for comparison, target, filename in [
            ("category", "POA-3", "death_flag_distribution_ratio_poa3.png"),
            ("category", "POA-2", "death_flag_distribution_ratio_poa2.png"),
            ("category", "NPOA-3", "death_flag_distribution_ratio_npoa3.png"),
            ("severity", "3", "death_flag_distribution_ratio_sepsis3.png"),
            ("severity", "2", "death_flag_distribution_ratio_sepsis2.png"),
            ("severity", "1", "death_flag_distribution_ratio_sepsis1.png"),
        ]:
            plot_mortality_agreement(
                mortality,
                comparison=comparison,
                target=target,
                filename=filename,
                output_dir=self.output_dir,
                config=self.figure_config,
            )
