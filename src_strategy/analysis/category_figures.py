"""Bar charts and heatmaps built from aggregate category tables."""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from matplotlib.ticker import FuncFormatter, MaxNLocator
import numpy as np
import polars as pl
import seaborn as sns

from .figure_config import (
    BILLING_COLOR,
    CALCULATED_COLOR,
    ICU_NO_COLOR,
    ICU_YES_COLOR,
    NPOA_COLOR,
    PATHWAY_BOTH_COLOR,
    PATHWAY_NEITHER_COLOR,
    PATHWAY_ORGAN_COLOR,
    PATHWAY_VASOPRESSOR_COLOR,
    POA_COLOR,
    Phase4FigureConfig,
)


def _save(fig: plt.Figure, path: Path, dpi: int) -> None:
    fig.tight_layout()
    fig.savefig(path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)


def _category_values(
    dataframe: pl.DataFrame,
    category_order: tuple[str, ...],
    value_col: str,
) -> np.ndarray:
    return np.array(
        [
            dataframe.filter(pl.col("category") == category)[value_col].item()
            if dataframe.filter(pl.col("category") == category).height
            else 0
            for category in category_order
        ],
        dtype=float,
    )


def plot_single_category_counts(
    category_counts: pl.DataFrame,
    *,
    source: str,
    title: str,
    filename: str,
    output_dir: Path,
    config: Phase4FigureConfig,
) -> None:
    """Reproduce one legacy cohort-count bar chart."""
    subset = category_counts.filter(pl.col("category_source") == source)
    counts = _category_values(subset, config.category_order, "encounter_count")
    color = config.source_colors[source]

    fig, ax = plt.subplots(figsize=(12, 8))
    bars = ax.bar(config.category_order, counts, color=color)
    ax.bar_label(bars, labels=[f"{int(value):,}" for value in counts], padding=3)
    ax.set_title(title)
    ax.set_xlabel("Category")
    ax.set_ylabel("Encounters")
    sns.despine(ax=ax)
    _save(fig, output_dir / filename, config.dpi)


def plot_mortality_by_category(
    mortality: pl.DataFrame,
    *,
    output_dir: Path,
    config: Phase4FigureConfig,
) -> None:
    """Reproduce the billed-versus-calculated mortality-rate chart."""
    sources = ["billed", "calculated_arrival_plus_48h"]
    x = np.arange(len(config.category_order))
    width = 0.36
    fig, ax = plt.subplots(figsize=(12, 6))

    for index, source in enumerate(sources):
        subset = mortality.filter(pl.col("category_source") == source)
        rates = _category_values(subset, config.category_order, "mortality_rate")
        deaths = _category_values(subset, config.category_order, "death_count")
        totals = _category_values(subset, config.category_order, "encounter_count")
        positions = x + (index - 0.5) * width
        bars = ax.bar(
            positions,
            rates * 100,
            width,
            label=config.source_labels[source],
            color=config.source_colors[source],
        )
        for bar, rate, deaths_count, total in zip(bars, rates, deaths, totals):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height(),
                f"{rate * 100:.1f}%\n({int(deaths_count):,}/{int(total):,})",
                ha="center",
                va="bottom",
                fontsize=8,
            )

    ax.set_xticks(x, config.category_order)
    ax.set_ylabel("Mortality Rate (%)")
    ax.set_xlabel("Sepsis Category")
    ax.set_title("Billing vs Computed Sepsis Category Mortality Rates")
    ax.legend()
    sns.despine(ax=ax)
    _save(fig, output_dir / "dist_mortality_rate_flag.png", config.dpi)


def plot_mortality_by_severity_heatmap(
    mortality: pl.DataFrame,
    *,
    output_dir: Path,
    config: Phase4FigureConfig,
) -> None:
    """Plot the 3x3 calculated-versus-billed severity mortality matrix."""
    def margin_annotation(
        rate: float | None,
        deaths: int,
        encounters: int,
    ) -> str:
        if rate is None:
            return "N/A\n(0/0)"
        return f"{rate:.1%}\n({deaths:,}/{encounters:,})"

    severities = [1, 2, 3]
    rate_matrix = np.full((3, 3), np.nan, dtype=float)
    annotations = np.full((3, 3), "N/A\n(0/0)", dtype=object)
    row_margins: list[str] = []
    column_margins: list[str] = []

    for row_index, calculated in enumerate(severities):
        for column_index, billed in enumerate(severities):
            row = mortality.filter(
                (pl.col("calculated_severity") == calculated)
                & (pl.col("billed_severity") == billed)
            )
            encounters = row["encounter_count"].item()
            deaths = row["death_count"].item()
            rate = row["mortality_rate"].item()
            if rate is not None:
                rate_matrix[row_index, column_index] = rate * 100
                annotations[row_index, column_index] = (
                    f"{rate:.1%}\n({deaths:,}/{encounters:,})"
                )

        row = mortality.filter(
            pl.col("calculated_severity") == calculated
        ).row(0, named=True)
        row_margins.append(
            margin_annotation(
                row["calculated_severity_mortality_rate"],
                row["calculated_severity_deaths"],
                row["calculated_severity_total"],
            )
        )

    for billed in severities:
        column = mortality.filter(
            pl.col("billed_severity") == billed
        ).row(0, named=True)
        column_margins.append(
            margin_annotation(
                column["billed_severity_mortality_rate"],
                column["billed_severity_deaths"],
                column["billed_severity_total"],
            )
        )

    fig, ax = plt.subplots(figsize=(10, 7))
    sns.heatmap(
        rate_matrix,
        annot=annotations,
        fmt="",
        cmap="Reds",
        vmin=0,
        vmax=100,
        linewidths=0.5,
        linecolor="white",
        xticklabels=[f"Sepsis {severity}" for severity in severities],
        yticklabels=[f"Sepsis {severity}" for severity in severities],
        cbar_kws={"label": "Mortality rate (%)", "pad": 0.14},
        ax=ax,
    )
    for index, margin in enumerate(row_margins):
        ax.text(
            len(severities) + 0.08,
            index + 0.5,
            margin,
            ha="left",
            va="center",
            fontweight="bold",
            clip_on=False,
        )
    for index, margin in enumerate(column_margins):
        ax.text(
            index + 0.5,
            -0.45,
            margin,
            ha="center",
            va="bottom",
            fontweight="bold",
            clip_on=False,
        )

    ax.xaxis.tick_top()
    ax.tick_params(axis="x", rotation=0, length=0)
    ax.tick_params(axis="y", rotation=0, length=0)
    ax.set_title(
        "Mortality Rate: Computed vs Billed Sepsis Severity",
        pad=105,
    )
    ax.set_xlabel("Billed Sepsis Severity", labelpad=12)
    ax.set_ylabel("Computed Sepsis Severity")
    _save(
        fig,
        output_dir / "mortality_rate_computed_vs_billed_severity_heatmap.png",
        config.dpi,
    )


def plot_category_distribution(
    category_counts: pl.DataFrame,
    *,
    title: str,
    filename: str,
    output_dir: Path,
    config: Phase4FigureConfig,
) -> None:
    """Plot billed and calculated category percentages with raw counts."""
    sources = ["billed", "calculated_arrival_plus_48h"]
    x = np.arange(len(config.category_order))
    width = 0.36
    fig, ax = plt.subplots(figsize=(12, 6))

    for index, source in enumerate(sources):
        subset = category_counts.filter(pl.col("category_source") == source)
        proportions = _category_values(subset, config.category_order, "proportion")
        counts = _category_values(subset, config.category_order, "encounter_count")
        positions = x + (index - 0.5) * width
        bars = ax.bar(
            positions,
            proportions * 100,
            width,
            label=config.source_labels[source],
            color=config.source_colors[source],
        )
        for bar, proportion, count in zip(bars, proportions, counts):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height(),
                f"{proportion * 100:.1f}%\n({int(count):,})",
                ha="center",
                va="bottom",
                fontsize=8,
            )

    ax.set_xticks(x, config.category_order)
    ax.set_ylabel("Percentage (%)")
    ax.set_xlabel("Sepsis Category")
    ax.set_title(title)
    ax.legend()
    sns.despine(ax=ax)
    _save(fig, output_dir / filename, config.dpi)


def plot_crosstab_heatmap(
    crosstab: pl.DataFrame,
    *,
    title: str,
    filename: str,
    output_dir: Path,
    config: Phase4FigureConfig,
    show_totals: bool,
) -> None:
    """Render the legacy column-normalized mismatch heatmap."""
    categories = list(config.category_order)
    count_matrix = np.zeros((len(categories), len(categories)), dtype=float)
    proportion_matrix = np.zeros_like(count_matrix)
    row_totals = np.zeros(len(categories), dtype=int)
    column_totals = np.zeros(len(categories), dtype=int)

    for row_index, calculated in enumerate(categories):
        for column_index, billed in enumerate(categories):
            row = crosstab.filter(
                (pl.col("calculated_category") == calculated)
                & (pl.col("billed_category") == billed)
            )
            if row.height:
                count_matrix[row_index, column_index] = row[
                    "encounter_count"
                ].item()
                proportion_matrix[row_index, column_index] = row[
                    "column_proportion"
                ].item()
                row_totals[row_index] = row["calculated_category_total"].item()
                column_totals[column_index] = row["billed_category_total"].item()

    annotations = np.empty(count_matrix.shape, dtype=object)
    for row_index in range(count_matrix.shape[0]):
        for column_index in range(count_matrix.shape[1]):
            annotations[row_index, column_index] = (
                f"{proportion_matrix[row_index, column_index]:.1%}\n"
                f"({int(count_matrix[row_index, column_index]):,})"
            )

    fig, ax = plt.subplots(figsize=(12 if show_totals else 10, 8))
    diagonal_mask = np.eye(len(categories), dtype=bool)
    sns.heatmap(
        1 - proportion_matrix,
        annot=annotations,
        fmt="",
        cmap="Blues",
        vmin=0,
        vmax=1,
        mask=diagonal_mask,
        linewidths=0.5,
        linecolor="white",
        xticklabels=categories,
        yticklabels=categories,
        cbar_kws={
            "label": "Mismatch proportion (column normalized)",
            "pad": 0.12 if show_totals else 0.02,
        },
        ax=ax,
    )
    for index in range(len(categories)):
        ax.text(
            index + 0.5,
            index + 0.5,
            annotations[index, index],
            ha="center",
            va="center",
            color="black",
        )
        ax.add_patch(
            Rectangle(
                (index, index),
                1,
                1,
                fill=False,
                edgecolor="green",
                linewidth=2.5,
            )
        )

    if show_totals:
        for index, total in enumerate(row_totals):
            ax.text(
                len(categories) + 0.08,
                index + 0.5,
                f"{total:,}",
                ha="left",
                va="center",
                fontweight="bold",
                clip_on=False,
            )
        for index, total in enumerate(column_totals):
            ax.text(
                index + 0.5,
                -0.55,
                f"{total:,}",
                ha="center",
                va="bottom",
                fontweight="bold",
                clip_on=False,
            )

    ax.xaxis.tick_top()
    ax.tick_params(axis="x", rotation=30, length=0)
    ax.tick_params(axis="y", length=0)
    ax.set_title(title, pad=25)
    # Keep the axis label below the heatmap so it cannot overlap column totals.
    ax.set_xlabel("Billing Sepsis Category", labelpad=12)
    ax.set_ylabel("Computed Sepsis Category")
    _save(fig, output_dir / filename, config.dpi)


def plot_icu_by_category_heatmap_claude_rate(
    crosstab: pl.DataFrame,
    *,
    output_dir: Path,
    config: Phase4FigureConfig,
) -> None:
    """Plot ICU encounter share by computed and billed sepsis category."""

    def share_annotation(count: int, total: int) -> str:
        if total == 0:
            return "N/A\n(0/0)"
        return f"{count / total:.1%}\n({count:,}/{total:,})"

    categories = list(config.category_order)
    n_categories = len(categories)
    count_matrix = np.zeros((n_categories, n_categories), dtype=int)
    row_totals = np.zeros(n_categories, dtype=int)
    column_totals = np.zeros(n_categories, dtype=int)

    for row_index, calculated in enumerate(categories):
        for column_index, billed in enumerate(categories):
            row = crosstab.filter(
                (pl.col("calculated_category") == calculated)
                & (pl.col("billed_category") == billed)
            )
            if row.height:
                count_matrix[row_index, column_index] = row[
                    "encounter_count"
                ].item()
                row_totals[row_index] = row[
                    "calculated_category_total"
                ].item()
                column_totals[column_index] = row[
                    "billed_category_total"
                ].item()

    # --- New: convert counts to % of all ICU encounters ---------------------
    grand_total = int(count_matrix.sum())
    if grand_total:
        percent_matrix = count_matrix / grand_total * 100
        vmax = max(float(percent_matrix.max()), 1.0)
    else:
        percent_matrix = np.full((n_categories, n_categories), np.nan)
        vmax = 100.0

    annotations = np.array(
        [
            [share_annotation(int(count), grand_total) for count in matrix_row]
            for matrix_row in count_matrix
        ],
        dtype=object,
    )
    row_margins = [share_annotation(int(t), grand_total) for t in row_totals]
    column_margins = [
        share_annotation(int(t), grand_total) for t in column_totals
    ]
    # -------------------------------------------------------------------------

    fig, ax = plt.subplots(figsize=(12, 8))
    sns.heatmap(
        percent_matrix,
        annot=annotations,
        fmt="",
        cmap="Reds",
        vmin=0,
        vmax=vmax,
        linewidths=0.5,
        linecolor="white",
        xticklabels=categories,
        yticklabels=categories,
        cbar_kws={"label": "Share of ICU encounters (%)", "pad": 0.14},
        ax=ax,
    )
    for index, margin in enumerate(row_margins):
        ax.text(
            n_categories + 0.08,
            index + 0.5,
            margin,
            ha="left",
            va="center",
            fontweight="bold",
            clip_on=False,
        )
    for index, margin in enumerate(column_margins):
        ax.text(
            index + 0.5,
            -0.55,
            margin,
            ha="center",
            va="bottom",
            fontweight="bold",
            clip_on=False,
        )

    ax.xaxis.tick_top()
    ax.tick_params(axis="x", rotation=30, length=0)
    ax.tick_params(axis="y", rotation=0, length=0)
    ax.set_title(
        "ICU Encounters: Computed vs Billed Sepsis Category",
        pad=115,
    )
    ax.set_xlabel("Billing Sepsis Category", labelpad=12)
    ax.set_ylabel("Computed Sepsis Category")
    _save(
        fig,
        output_dir / "icu_encounter_count_computed_vs_billed_category_heatmap.png",
        config.dpi,
    )


def plot_icu_by_category_heatmap(
    crosstab: pl.DataFrame,
    *,
    output_dir: Path,
    config: Phase4FigureConfig,
) -> None:
    """Plot ICU encounter counts by computed and billed sepsis category."""
    categories = list(config.category_order)
    count_matrix = np.zeros((len(categories), len(categories)), dtype=int)
    row_totals = np.zeros(len(categories), dtype=int)
    column_totals = np.zeros(len(categories), dtype=int)

    for row_index, calculated in enumerate(categories):
        for column_index, billed in enumerate(categories):
            row = crosstab.filter(
                (pl.col("calculated_category") == calculated)
                & (pl.col("billed_category") == billed)
            )
            if row.height:
                count_matrix[row_index, column_index] = row[
                    "encounter_count"
                ].item()
                row_totals[row_index] = row[
                    "calculated_category_total"
                ].item()
                column_totals[column_index] = row[
                    "billed_category_total"
                ].item()

    fig, ax = plt.subplots(figsize=(12, 8))
    sns.heatmap(
        count_matrix,
        annot=True,
        fmt=",d",
        cmap="Purples",
        vmin=0,
        vmax=max(int(count_matrix.max()), 1),
        linewidths=0.5,
        linecolor="white",
        xticklabels=categories,
        yticklabels=categories,
        cbar_kws={"label": "ICU encounter count", "pad": 0.12},
        ax=ax,
    )
    for index, total in enumerate(row_totals):
        ax.text(
            len(categories) + 0.08,
            index + 0.5,
            f"{total:,}",
            ha="left",
            va="center",
            fontweight="bold",
            clip_on=False,
        )
    for index, total in enumerate(column_totals):
        ax.text(
            index + 0.5,
            -0.55,
            f"{total:,}",
            ha="center",
            va="bottom",
            fontweight="bold",
            clip_on=False,
        )

    ax.xaxis.tick_top()
    ax.tick_params(axis="x", rotation=30, length=0)
    ax.tick_params(axis="y", length=0)
    ax.set_title(
        "ICU Encounters: Computed vs Billed Sepsis Category",
        pad=95,
    )
    ax.set_xlabel("Billing Sepsis Category", labelpad=12)
    ax.set_ylabel("Computed Sepsis Category")
    _save(
        fig,
        output_dir / "icu_encounter_count_computed_vs_billed_category_heatmap.png",
        config.dpi,
    )


def plot_icu_by_severity_heatmap(
    crosstab: pl.DataFrame,
    *,
    output_dir: Path,
    config: Phase4FigureConfig,
) -> None:
    """Plot ICU encounter counts by computed and billed sepsis severity."""
    severities = [1, 2, 3]
    count_matrix = np.zeros((3, 3), dtype=int)
    row_totals = np.zeros(3, dtype=int)
    column_totals = np.zeros(3, dtype=int)

    for row_index, calculated in enumerate(severities):
        for column_index, billed in enumerate(severities):
            row = crosstab.filter(
                (pl.col("calculated_severity") == calculated)
                & (pl.col("billed_severity") == billed)
            )
            if row.height:
                count_matrix[row_index, column_index] = row[
                    "icu_encounter_count"
                ].item()
                row_totals[row_index] = row[
                    "calculated_severity_total"
                ].item()
                column_totals[column_index] = row[
                    "billed_severity_total"
                ].item()

    labels = [f"Sepsis {severity}" for severity in severities]
    fig, ax = plt.subplots(figsize=(10, 7))
    sns.heatmap(
        count_matrix,
        annot=True,
        fmt=",d",
        cmap="Purples",
        vmin=0,
        vmax=max(int(count_matrix.max()), 1),
        linewidths=0.5,
        linecolor="white",
        xticklabels=labels,
        yticklabels=labels,
        cbar_kws={"label": "ICU encounter count", "pad": 0.14},
        ax=ax,
    )
    for index, total in enumerate(row_totals):
        ax.text(
            len(severities) + 0.08,
            index + 0.5,
            f"{total:,}",
            ha="left",
            va="center",
            fontweight="bold",
            clip_on=False,
        )
    for index, total in enumerate(column_totals):
        ax.text(
            index + 0.5,
            -0.45,
            f"{total:,}",
            ha="center",
            va="bottom",
            fontweight="bold",
            clip_on=False,
        )

    ax.xaxis.tick_top()
    ax.tick_params(axis="x", rotation=0, length=0)
    ax.tick_params(axis="y", rotation=0, length=0)
    ax.set_title(
        "ICU Encounters: Computed vs Billed Sepsis Severity",
        pad=90,
    )
    ax.set_xlabel("Billed Sepsis Severity", labelpad=12)
    ax.set_ylabel("Computed Sepsis Severity")
    _save(
        fig,
        output_dir / "icu_encounter_count_computed_vs_billed_severity_heatmap.png",
        config.dpi,
    )


def plot_icu_by_severity_heatmap_claude_rate(
    crosstab: pl.DataFrame,
    *,
    output_dir: Path,
    config: Phase4FigureConfig,
) -> None:
    """Plot ICU encounter share by computed and billed sepsis severity."""

    def share_annotation(count: int, total: int) -> str:
        if total == 0:
            return "N/A\n(0/0)"
        return f"{count / total:.1%}\n({count:,}/{total:,})"

    severities = [1, 2, 3]
    n_severities = len(severities)
    count_matrix = np.zeros((n_severities, n_severities), dtype=int)
    row_totals = np.zeros(n_severities, dtype=int)
    column_totals = np.zeros(n_severities, dtype=int)

    for row_index, calculated in enumerate(severities):
        for column_index, billed in enumerate(severities):
            row = crosstab.filter(
                (pl.col("calculated_severity") == calculated)
                & (pl.col("billed_severity") == billed)
            )
            if row.height:
                count_matrix[row_index, column_index] = row[
                    "icu_encounter_count"
                ].item()
                row_totals[row_index] = row[
                    "calculated_severity_total"
                ].item()
                column_totals[column_index] = row[
                    "billed_severity_total"
                ].item()

    # --- Convert counts to % of all ICU encounters ---------------------------
    grand_total = int(count_matrix.sum())
    if grand_total:
        percent_matrix = count_matrix / grand_total * 100
        vmax = max(float(percent_matrix.max()), 1.0)
    else:
        percent_matrix = np.full((n_severities, n_severities), np.nan)
        vmax = 100.0

    annotations = np.array(
        [
            [share_annotation(int(count), grand_total) for count in matrix_row]
            for matrix_row in count_matrix
        ],
        dtype=object,
    )
    row_margins = [share_annotation(int(t), grand_total) for t in row_totals]
    column_margins = [
        share_annotation(int(t), grand_total) for t in column_totals
    ]
    # -------------------------------------------------------------------------

    labels = [f"Sepsis {severity}" for severity in severities]
    fig, ax = plt.subplots(figsize=(10, 7))
    sns.heatmap(
        percent_matrix,
        annot=annotations,
        fmt="",
        cmap="Reds",
        vmin=0,
        vmax=vmax,
        linewidths=0.5,
        linecolor="white",
        xticklabels=labels,
        yticklabels=labels,
        cbar_kws={"label": "Share of ICU encounters (%)", "pad": 0.14},
        ax=ax,
    )
    for index, margin in enumerate(row_margins):
        ax.text(
            n_severities + 0.08,
            index + 0.5,
            margin,
            ha="left",
            va="center",
            fontweight="bold",
            clip_on=False,
        )
    for index, margin in enumerate(column_margins):
        ax.text(
            index + 0.5,
            -0.45,
            margin,
            ha="center",
            va="bottom",
            fontweight="bold",
            clip_on=False,
        )

    ax.xaxis.tick_top()
    ax.tick_params(axis="x", rotation=0, length=0)
    ax.tick_params(axis="y", rotation=0, length=0)
    ax.set_title(
        "ICU Encounters: Computed vs Billed Sepsis Severity",
        pad=105,
    )
    ax.set_xlabel("Billed Sepsis Severity", labelpad=12)
    ax.set_ylabel("Computed Sepsis Severity")
    _save(
        fig,
        output_dir / "icu_encounter_count_computed_vs_billed_severity_heatmap.png",
        config.dpi,
    )


def plot_icu_status_diverging_bars(
    counts: pl.DataFrame,
    *,
    classification_source: str,
    classification_order: list[str],
    display_labels: list[str],
    title: str,
    filename: str,
    output_dir: Path,
    config: Phase4FigureConfig,
    y_limits: tuple[float, float] | None = None,
) -> None:
    """Plot ICU=1 upward and ICU=0 downward for one classification source."""
    subset = counts.filter(
        pl.col("classification_source") == classification_source
    )
    positive_counts = np.array(
        [
            subset.filter(
                (pl.col("classification") == classification)
                & (pl.col("icu_status") == 1)
            )["encounter_count"].item()
            for classification in classification_order
        ],
        dtype=int,
    )
    negative_counts = np.array(
        [
            subset.filter(
                (pl.col("classification") == classification)
                & (pl.col("icu_status") == 0)
            )["encounter_count"].item()
            for classification in classification_order
        ],
        dtype=int,
    )
    category_totals = positive_counts + negative_counts

    positions = np.arange(len(classification_order))
    fig, ax = plt.subplots(figsize=(12, 7))
    positive_bars = ax.bar(
        positions,
        positive_counts,
        color=ICU_YES_COLOR,
        label="ICU_YN = 1",
    )
    negative_bars = ax.bar(
        positions,
        -negative_counts,
        color=ICU_NO_COLOR,
        label="ICU_YN = 0",
    )
    for bar, count, total in zip(
        positive_bars,
        positive_counts,
        category_totals,
    ):
        if count == 0:
            continue
        ax.annotate(
            f"{count:,} ({count / total:.1%})",
            xy=(bar.get_x() + bar.get_width() / 2, bar.get_height()),
            xytext=(0, 3),
            textcoords="offset points",
            ha="center",
            va="bottom",
        )
    for bar, count, total in zip(
        negative_bars,
        negative_counts,
        category_totals,
    ):
        if count == 0:
            continue
        ax.annotate(
            f"{count:,} ({count / total:.1%})",
            xy=(bar.get_x() + bar.get_width() / 2, bar.get_height()),
            xytext=(0, -3),
            textcoords="offset points",
            ha="center",
            va="top",
        )

    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_xticks(positions, display_labels)
    ax.yaxis.set_major_locator(MaxNLocator(integer=True))
    ax.yaxis.set_major_formatter(
        FuncFormatter(lambda value, _: f"{abs(value):,.0f}")
    )
    if y_limits is not None:
        ax.set_ylim(y_limits)
    ax.set_xlabel("Sepsis Classification")
    ax.set_ylabel("Encounter Count (ICU_YN=0 shown below zero)")
    ax.set_title(title)
    ax.legend()
    sns.despine(ax=ax)
    _save(fig, output_dir / filename, config.dpi)


def plot_icu_sepsis3_pathway_diverging_bars(
    counts: pl.DataFrame,
    *,
    output_dir: Path,
    config: Phase4FigureConfig,
) -> None:
    """Compare ICU status for computed and billed Sepsis 3 by pathway."""
    # sources = ["computed_sepsis3", "billed_sepsis3"]
    # source_labels = ["Computed Sepsis 3", "Billed Sepsis 3"]
    sources = ["billed_sepsis3", "computed_sepsis3"]
    source_labels = ["Billed Sepsis 3", "Computed Sepsis 3"]
    pathway_styles = [
        ("organ_dysfunction", "Organ Dysfunction Pathway", PATHWAY_ORGAN_COLOR),
        ("vasopressors", "Vasopressors Pathway", PATHWAY_VASOPRESSOR_COLOR),
        ("both", "Both Pathways", PATHWAY_BOTH_COLOR),
        ("neither", "Neither Pathway", PATHWAY_NEITHER_COLOR),
    ]
    positions = np.arange(len(sources))
    positive_bottom = np.zeros(len(sources), dtype=float)
    negative_bottom = np.zeros(len(sources), dtype=float)
    segment_annotations = []
    fig, ax = plt.subplots(figsize=(11, 8))

    for pathway_group, display_label, color in pathway_styles:
        positive_counts = np.array(
            [
                counts.filter(
                    (pl.col("classification_source") == source)
                    & (pl.col("pathway_group") == pathway_group)
                    & (pl.col("icu_status") == 1)
                )["encounter_count"].item()
                for source in sources
            ],
            dtype=int,
        )
        negative_counts = np.array(
            [
                counts.filter(
                    (pl.col("classification_source") == source)
                    & (pl.col("pathway_group") == pathway_group)
                    & (pl.col("icu_status") == 0)
                )["encounter_count"].item()
                for source in sources
            ],
            dtype=int,
        )
        denominators = np.array(
            [
                counts.filter(pl.col("classification_source") == source)[
                    "denominator"
                ].item(0)
                for source in sources
            ],
            dtype=int,
        )
        positive_bars = ax.bar(
            positions,
            positive_counts,
            bottom=positive_bottom,
            color=color,
            label=display_label,
        )
        negative_bars = ax.bar(
            positions,
            -negative_counts,
            bottom=-negative_bottom,
            color=color,
        )
        for bars, segment_counts, direction_bottom, direction in [
            (positive_bars, positive_counts, positive_bottom, 1),
            (negative_bars, negative_counts, negative_bottom, -1),
        ]:
            for source_index, (bar, count, denominator, bottom) in enumerate(zip(
                bars,
                segment_counts,
                denominators,
                direction_bottom,
            )):
                if count == 0:
                    continue
                segment_annotations.append(
                    (
                        source_index,
                        direction,
                        bottom + count / 2,
                        int(count),
                        int(denominator),
                        color,
                    )
                )
        positive_bottom += positive_counts
        negative_bottom += negative_counts

    positive_max = max(positive_bottom.max(), 1)
    negative_max = max(negative_bottom.max(), 1)
    small_annotations = []
    for annotation in segment_annotations:
        source_index, direction, center, count, denominator, color = annotation
        direction_max = positive_max if direction == 1 else negative_max
        threshold = direction_max * (0.04 if direction == 1 else 0.10)
        if count < threshold:
            small_annotations.append(annotation)
        else:
            ax.annotate(
                f"{count:,}\n({count / denominator:.1%})",
                xy=(positions[source_index], direction * center),
                ha="center",
                va="center",
                fontsize=8,
            )

    for source_index in range(len(sources)):
        for direction in [1, -1]:
            items = sorted(
                [
                    annotation
                    for annotation in small_annotations
                    if annotation[0] == source_index
                    and annotation[1] == direction
                ],
                key=lambda annotation: annotation[2],
            )
            direction_max = positive_max if direction == 1 else negative_max
            label_gap = direction_max * 0.12
            previous_position = 0.0
            for _, _, center, count, denominator, color in items:
                label_position = max(center, previous_position + label_gap)
                previous_position = label_position
                text_x = positions[source_index] + (
                    -0.42 if source_index == 0 else 0.42
                )
                ax.annotate(
                    f"{count:,} ({count / denominator:.1%})",
                    xy=(positions[source_index], direction * center),
                    xytext=(text_x, direction * label_position),
                    textcoords="data",
                    arrowprops={
                        "arrowstyle": "-",
                        "color": color,
                        "linewidth": 1,
                    },
                    ha="right" if source_index == 0 else "left",
                    va="center",
                    fontsize=8,
                )

    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_ylim(-negative_max * 1.20, positive_max * 1.10)
    ax.set_xticks(positions, source_labels)
    ax.yaxis.set_major_locator(MaxNLocator(integer=True))
    ax.yaxis.set_major_formatter(
        FuncFormatter(lambda value, _: f"{abs(value):,.0f}")
    )
    ax.set_xlabel("Sepsis 3 Classification Source")
    ax.set_ylabel("Encounter Count (ICU_YN=0 shown below zero)")
    ax.set_title("ICU Status for Sepsis 3 by Computed Clinical Pathway")
    ax.legend(title="Pathway criterion met")
    sns.despine(ax=ax)
    _save(
        fig,
        output_dir / "icu_status_sepsis3_by_pathway_diverging_barplot.png",
        config.dpi,
    )


def plot_poa_status_comparison(
    poa_counts: pl.DataFrame,
    *,
    output_dir: Path,
    config: Phase4FigureConfig,
) -> None:
    """Compare aggregate POA/NPOA counts across the three timing sources."""
    sources = [
        "billed",
        "calculated_inpatient_admission",
        "calculated_arrival_plus_48h",
    ]
    statuses = ["NPOA", "POA"]
    x = np.arange(len(statuses))
    width = 0.24
    fig, ax = plt.subplots(figsize=(10, 6))

    for index, source in enumerate(sources):
        subset = poa_counts.filter(pl.col("category_source") == source)
        counts = np.array(
            [
                subset.filter(pl.col("poa_status") == status)[
                    "encounter_count"
                ].item()
                for status in statuses
            ]
        )
        positions = x + (index - 1) * width
        bars = ax.bar(
            positions,
            counts,
            width,
            label=config.source_labels[source],
            color=config.source_colors[source],
        )
        ax.bar_label(bars, labels=[f"{int(value):,}" for value in counts], padding=2)

    ax.set_xticks(x, statuses)
    ax.set_ylabel("Encounters")
    ax.set_title("Category Counts: Billing vs Inpatient vs Arrival + 48 Hours")
    ax.legend()
    sns.despine(ax=ax)
    _save(
        fig,
        output_dir
        / "sepsis_category_comparison_arrival_inpatient_aggregate_poa.png",
        config.dpi,
    )
