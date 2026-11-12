"""Outcome figures and aggregate-native interval replacements."""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import polars as pl
import seaborn as sns

from .figure_config import (
    BILLING_COLOR,
    CALCULATED_COLOR,
    DEATH_NO_COLOR,
    DEATH_YES_COLOR,
    MATCH_COLOR,
    Phase4FigureConfig,
)


def _save(fig: plt.Figure, path: Path, dpi: int) -> None:
    # bbox_inches includes long agreement labels without tight_layout warnings
    # when a small synthetic cohort contains only one comparison group.
    fig.savefig(path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)


def plot_time_summary_intervals(
    summary: pl.DataFrame,
    *,
    output_dir: Path,
    config: Phase4FigureConfig,
) -> None:
    """Replace the patient-level time strip/boxplot with range/IQR/median."""
    sources = ["billed", "calculated_arrival_plus_48h"]
    x = np.arange(len(config.category_order), dtype=float)
    offsets = {"billed": -0.12, "calculated_arrival_plus_48h": 0.12}
    fig, ax = plt.subplots(figsize=(12, 6))

    for source in sources:
        subset = summary.filter(pl.col("category_source") == source)
        first_label = True
        for index, category in enumerate(config.category_order):
            row = subset.filter(pl.col("category") == category)
            if not row.height:
                continue
            position = x[index] + offsets[source]
            minimum = row["minimum"].item()
            q1 = row["q1"].item()
            median = row["median"].item()
            q3 = row["q3"].item()
            maximum = row["maximum"].item()
            color = config.source_colors[source]
            ax.vlines(position, minimum, maximum, color=color, linewidth=1)
            ax.vlines(position, q1, q3, color=color, linewidth=7)
            ax.scatter(
                position,
                median,
                color="white",
                edgecolor=color,
                linewidth=2,
                zorder=3,
                label=config.source_labels[source] if first_label else None,
            )
            first_label = False

    ax.set_xticks(x, config.category_order)
    ax.set_ylabel("Arrival to Sepsis Time (Hours)")
    ax.set_xlabel("Sepsis Category")
    ax.set_title("Arrival to Sepsis Time: Range, IQR, and Median")
    ax.legend()
    sns.despine(ax=ax)
    _save(
        fig,
        output_dir / "sepsis_time_iqr_median_range_arrival.png",
        config.dpi,
    )


def plot_los_agreement_intervals(
    summary: pl.DataFrame,
    *,
    comparison: str,
    target: str,
    filename: str,
    output_dir: Path,
    config: Phase4FigureConfig,
) -> None:
    """Replace one patient-level LOS strip/boxplot with range/IQR/median."""
    subset = summary.filter(
        (pl.col("comparison") == comparison) & (pl.col("target") == target)
    )
    group_order = [
        "billing_only",
        "calculated_only",
        "billing_and_calculated",
    ]
    display_target = f"Sepsis {target}" if comparison == "severity" else target
    group_labels = {
        "billing_only": (
            f"Billing={display_target}; Calculated ≠ {display_target}"
        ),
        "calculated_only": (
            f"Calculated={display_target}; Billing ≠ {display_target}"
        ),
        "billing_and_calculated": (
            f"Billing and Calculated={display_target}"
        ),
    }
    colors = {
        "billing_only": BILLING_COLOR,
        "calculated_only": CALCULATED_COLOR,
        "billing_and_calculated": MATCH_COLOR,
    }
    present_groups = [
        group
        for group in group_order
        if subset.filter(pl.col("agreement_group") == group).height
    ]

    fig, ax = plt.subplots(figsize=(12, 6))
    for index, group in enumerate(present_groups):
        row = subset.filter(pl.col("agreement_group") == group)
        minimum = row["minimum"].item()
        q1 = row["q1"].item()
        median = row["median"].item()
        q3 = row["q3"].item()
        maximum = row["maximum"].item()
        count = row["encounter_count"].item()
        color = colors[group]
        ax.hlines(index, minimum, maximum, color=color, linewidth=1)
        ax.hlines(index, q1, q3, color=color, linewidth=8)
        ax.scatter(
            median,
            index,
            color="white",
            edgecolor=color,
            linewidth=2,
            zorder=3,
        )
        ax.text(maximum, index - 0.18, f" n={count:,}", fontsize=9)

    ax.set_yticks(
        range(len(present_groups)),
        [group_labels[group] for group in present_groups],
    )
    ax.set_xlabel("Length of Stay (Days)")
    ax.set_ylabel("")
    ax.set_title(
        f"LOS: {display_target} Agreement — Range, IQR, and Median"
    )
    ax.invert_yaxis()
    sns.despine(ax=ax)
    _save(fig, output_dir / filename, config.dpi)


def plot_los_median_by_category(
    summary: pl.DataFrame,
    *,
    output_dir: Path,
    config: Phase4FigureConfig,
) -> None:
    """Reproduce the legacy billed-versus-calculated median LOS chart."""
    sources = ["billed", "calculated_arrival_plus_48h"]
    x = np.arange(len(config.category_order))
    width = 0.36
    fig, ax = plt.subplots(figsize=(12, 6))

    for index, source in enumerate(sources):
        subset = summary.filter(pl.col("category_source") == source)
        medians = []
        for category in config.category_order:
            row = subset.filter(pl.col("category") == category)
            medians.append(row["median"].item() if row.height else 0.0)
        positions = x + (index - 0.5) * width
        bars = ax.bar(
            positions,
            medians,
            width,
            label=config.source_labels[source],
            color=config.source_colors[source],
        )
        ax.bar_label(bars, labels=[f"{value:.1f}" for value in medians], padding=2)

    ax.set_xticks(x, config.category_order)
    ax.set_ylabel("Median Length of Stay (Days)")
    ax.set_xlabel("Sepsis Category")
    ax.set_title("LOS Distribution by Arrival Time + 48 Hours")
    ax.legend()
    sns.despine(ax=ax)
    _save(fig, output_dir / "dist_los_arrival.png", config.dpi)


def plot_mortality_agreement(
    mortality: pl.DataFrame,
    *,
    comparison: str,
    target: str,
    filename: str,
    output_dir: Path,
    config: Phase4FigureConfig,
) -> None:
    """Reproduce one stacked mortality agreement/disagreement chart."""
    subset = mortality.filter(
        (pl.col("comparison") == comparison) & (pl.col("target") == target)
    )
    group_order = [
        "billing_only",
        "calculated_only",
        "billing_and_calculated",
    ]
    present_groups = [
        group
        for group in group_order
        if subset.filter(pl.col("agreement_group") == group).height
    ]
    display_target = f"Sepsis {target}" if comparison == "severity" else target
    group_labels = {
        "billing_only": (
            f"Billing={display_target}\nCalculated ≠ {display_target}"
        ),
        "calculated_only": (
            f"Calculated={display_target}\nBilling ≠ {display_target}"
        ),
        "billing_and_calculated": (
            f"Billing and Calculated\n= {display_target}"
        ),
    }

    no_death = []
    death = []
    totals = []
    for group in present_groups:
        rows = subset.filter(pl.col("agreement_group") == group)
        no_row = rows.filter(pl.col("death_flag") == 0)
        yes_row = rows.filter(pl.col("death_flag") == 1)
        no_death.append(no_row["proportion"].item() * 100 if no_row.height else 0)
        death.append(yes_row["proportion"].item() * 100 if yes_row.height else 0)
        totals.append(rows["group_total"].max())

    x = np.arange(len(present_groups))
    fig, ax = plt.subplots(figsize=(12, 6))
    no_bars = ax.bar(x, no_death, color=DEATH_NO_COLOR, label="Survived")
    yes_bars = ax.bar(
        x,
        death,
        bottom=no_death,
        color=DEATH_YES_COLOR,
        label="Died",
    )
    for bars, values, bottoms in [
        (no_bars, no_death, np.zeros(len(no_death))),
        (yes_bars, death, np.array(no_death)),
    ]:
        for bar, value, bottom in zip(bars, values, bottoms):
            if value > 3:
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    bottom + value / 2,
                    f"{value:.1f}%",
                    ha="center",
                    va="center",
                    color="white",
                    fontweight="bold",
                )
    for index, total in enumerate(totals):
        ax.text(index, 102, f"n={total:,}", ha="center", fontsize=9)

    ax.set_xticks(x, [group_labels[group] for group in present_groups])
    ax.set_ylim(0, 110)
    ax.set_ylabel("Percentage (%)")
    ax.set_title(
        "Death Flag Distribution: "
        f"{display_target} Agreement vs Disagreement"
    )
    ax.legend()
    sns.despine(ax=ax)
    _save(fig, output_dir / filename, config.dpi)
