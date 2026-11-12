"""Bar charts and heatmaps built from aggregate category tables."""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import numpy as np
import polars as pl
import seaborn as sns

from .figure_config import (
    BILLING_COLOR,
    CALCULATED_COLOR,
    NPOA_COLOR,
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
