import polars as pl
import numpy as np
from pathlib import Path
import os
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from scipy.stats import chi2_contingency, fisher_exact
from typing import List
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import seaborn as sns
import matplotlib.ticker as mticker

from src.configs.analysis.twoexpr import TwoExprAnalysisConfig 
from src.utils.logger import get_logger
from src.utils.utils import load_output_folder 
import pandas as pd
from typing import Optional

ALGO_PALETTE = {
    "Algorithm A": "#0066cc",   # medium-dark blue
    "Algorithm B": "#cc6600",   # contrasting amber/orange
}

SCORE_PALETTE_A = ["#cce5ff", "#66b2ff", "#0066cc"]   # score 1, 2, 3
SCORE_PALETTE_B = ["#ffe0cc", "#ffaa66", "#cc6600"]   # score 1, 2, 3

COLUMN_DISPLAY_NAMES = {
    "sepsis_score":              "Sepsis Score",
    "sepsis_score_at_max":       "Sepsis Score at Max",
    "Sepsis_Category":           "Billing Categorization",
    "first_sepsis_instant":      "First Sepsis Instant",
    "first_sepsis_instant_at_max": "First Sepsis Instant at Max",
    "detection_diff_hours":      "Detection Time Difference (Hours)",
    "LOS_days":                  "Length of Stay (Days)",
}


def get_display_name(col: str) -> str:
    return COLUMN_DISPLAY_NAMES.get(col, col)

logger = get_logger(__name__)

class TwoExperimentsAnalysis():
    def __init__(self, expr1_dir: Path, expr2_dir: Path, output_path: Path|str, two_expr_config: TwoExprAnalysisConfig) -> None:
        if isinstance(output_path, str):
            self.output_path = Path(output_path)
        elif isinstance(output_path, Path):
            self.output_path = output_path
        else: 
            raise ValueError("output_path must be a string or Path object")

        self.output_path.mkdir(parents=True, exist_ok=True)
        self.expr1_dir = expr1_dir
        self.expr2_dir = expr2_dir
        self.two_expr_config = two_expr_config
        self._load_dataframes()

    def _load_dataframes(self):
        self.df_dict_1 = load_output_folder(self.expr1_dir, logger)
        self.df_dict_2 = load_output_folder(self.expr2_dir, logger)


    # ──────────────────────────────────────────────
# 2.  Data preparation
# ──────────────────────────────────────────────

    def prepare_joined_data(
        self,
        df_a: pl.DataFrame,
        df_b: pl.DataFrame,
        label_a: str = "Algorithm A",
        label_b: str = "Algorithm B",
    ) -> pd.DataFrame:
        """
        Join the two experiment outputs on EncounterEpicCsn and
        return a long-form pandas DataFrame suitable for plotting.

        Parameters
        ----------
        df_a : pl.DataFrame   – output of experiment A
        df_b : pl.DataFrame   – output of experiment B
        label_a, label_b      – human-readable names for each algorithm

        Returns
        -------
        pd.DataFrame with columns:
            EncounterEpicCsn, algorithm, sepsis_score, sepsis_score_at_max,
            first_sepsis_instant, first_sepsis_instant_at_max,
            Sepsis_Category, Death_Flag, LOS_days
        """

        score_cols = [
            "EncounterEpicCsn",
            "sepsis_score",
            "sepsis_score_at_max",
            "first_sepsis_instant",
            "first_sepsis_instant_at_max",
        ]
        meta_cols = [
            "EncounterEpicCsn",
            "Sepsis_Category",
            "Death_Flag",
            "LOS_days",
            "Arrival_Instant",
            "InpatientAdmissionInstant",
        ]

        # Keep only the columns we need from each algorithm
        a = df_a.select(score_cols).with_columns(pl.lit(label_a).alias("algorithm"))
        b = df_b.select(score_cols).with_columns(pl.lit(label_b).alias("algorithm"))

        # Stack vertically (long form)
        long = pl.concat([a, b])

        # Grab metadata from either frame (they share the same encounters)
        meta = df_a.select(meta_cols).unique(subset=["EncounterEpicCsn"])

        long = long.join(meta, on="EncounterEpicCsn", how="left")

        return long.to_pandas()


    def build_agreement_matrix(
        self,
        df_a: pl.DataFrame,
        df_b: pl.DataFrame,
        label_a: str,
        label_b: str,
        score_col: str,
    ) -> pd.DataFrame:
        """
        Build a 3×3 agreement (confusion) matrix between the two algorithms
        for a given score column.

        Returns a pandas DataFrame with Algorithm A scores as rows and
        Algorithm B scores as columns.
        """
        joined = (
            df_a.select(["EncounterEpicCsn", score_col])
            .rename({score_col: "score_a"})
            .join(
                df_b.select(["EncounterEpicCsn", score_col])
                .rename({score_col: "score_b"}),
                on="EncounterEpicCsn",
                how="inner",
            )
        ).to_pandas()

        labels = [1, 2, 3]
        matrix = pd.crosstab(
            joined["score_a"],
            joined["score_b"],
            rownames=[label_a],
            colnames=[label_b],
            dropna=False,
        ).reindex(index=labels, columns=labels, fill_value=0)

        return matrix


    # ──────────────────────────────────────────────
    # 3.  Visualization functions
    # ──────────────────────────────────────────────

    def plot_score_distribution(
        self,
        long_df: pd.DataFrame,
        score_col: str = "sepsis_score",
        output_path: Optional[Path] = None,
        ALGO_PALETTE: dict = ALGO_PALETTE,
        figsize: tuple = (10, 5),
    ) -> plt.Figure:
        """
        Side-by-side grouped bar chart showing the count distribution
        of a score column (1, 2, 3) for each algorithm.
        """
        fig, ax = plt.subplots(figsize=figsize)

        order = [1, 2, 3]

        sns.countplot(
            data=long_df,
            x=score_col,
            hue="algorithm",
            order=order,
            palette=ALGO_PALETTE,
            edgecolor="white",
            ax=ax,
        )

        # Annotate bar counts
        for container in ax.containers:
            ax.bar_label(container, fmt="%d", fontsize=9, padding=3)

        ax.set_title(f"Distribution of {get_display_name(score_col)} by Algorithm", fontsize=13)
        ax.set_xlabel(get_display_name(score_col))
        ax.set_ylabel("Encounter Count")
        ax.legend(title="Algorithm")
        ax.yaxis.set_major_locator(mticker.MaxNLocator(integer=True))

        fig.tight_layout()
        if output_path:
            fig.savefig(output_path, bbox_inches="tight", dpi=150)
        return fig


    def plot_score_distribution_normalized(
        self,
        long_df: pd.DataFrame,
        score_col: str = "sepsis_score",
        output_path: Optional[Path] = None,
        ALGO_PALETTE: dict = ALGO_PALETTE,
        figsize: tuple = (10, 5),
    ) -> plt.Figure:
        """
        Same comparison but as proportions (%) within each algorithm,
        making it easier to compare when sample sizes differ.
        """
        # Compute proportions
        counts = (
            long_df.groupby(["algorithm", score_col])
            .size()
            .reset_index(name="count")
        )
        totals = counts.groupby("algorithm")["count"].transform("sum")
        counts["proportion"] = counts["count"] / totals * 100

        fig, ax = plt.subplots(figsize=figsize)

        sns.barplot(
            data=counts,
            x=score_col,
            y="proportion",
            hue="algorithm",
            order=[1, 2, 3],
            palette=ALGO_PALETTE,
            edgecolor="white",
            ax=ax,
        )

        for container in ax.containers:
            ax.bar_label(container, fmt="%.1f%%", fontsize=9, padding=3)

        ax.set_title(
            f"Normalized Distribution of {get_display_name(score_col)} by Algorithm",
            fontsize=13,
        )
        ax.set_xlabel(get_display_name(score_col))
        ax.set_ylabel("Percentage of Encounters (%)")
        ax.legend(title="Algorithm")

        fig.tight_layout()
        if output_path:
            fig.savefig(output_path, bbox_inches="tight", dpi=150)
        return fig


    def plot_agreement_heatmap(
        self,
        matrix: pd.DataFrame,
        score_col: str = "sepsis_score",
        output_path: Optional[Path] = None,
        figsize: tuple = (6, 5),
    ) -> plt.Figure:
        """
        Heatmap of the 3×3 agreement matrix between Algorithm A and B.
        Diagonal = agreement; off-diagonal = disagreement.
        """
        fig, ax = plt.subplots(figsize=figsize)

        sns.heatmap(
            matrix,
            annot=True,
            fmt="d",
            cmap="Blues",
            linewidths=0.5,
            linecolor="white",
            cbar_kws={"label": "Encounter Count"},
            ax=ax,
        )

        ax.set_title(f"Agreement Matrix – {get_display_name(score_col)}", fontsize=13)
        ax.set_xlabel("Algorithm B Score")
        ax.set_ylabel("Algorithm A Score")

        fig.tight_layout()
        if output_path:
            fig.savefig(output_path, bbox_inches="tight", dpi=150)
        return fig


    def plot_score_by_category(
        self,
        long_df: pd.DataFrame,
        score_col: str = "sepsis_score",
        category_col: str = "Sepsis_Category",
        output_path: Optional[Path] = None,
        ALGO_PALETTE: dict = ALGO_PALETTE,
        figsize: tuple = (12, 5),
    ) -> plt.Figure:
        """
        Grouped bar chart of score distribution, faceted by Sepsis_Category.
        Uses your stripplot-over-boxplot style for the score treated as
        a continuous-ish variable.
        """
        cat_order = sorted(long_df[category_col].dropna().unique())

        fig, ax = plt.subplots(figsize=figsize)

        # Scatter layer (below)
        sns.stripplot(
            data=long_df,
            x=category_col,
            y=score_col,
            hue="algorithm",
            order=cat_order,
            palette=ALGO_PALETTE,
            dodge=True,
            alpha=0.3,
            size=3,
            jitter=True,
            ax=ax,
            legend=False,
        )

        # Boxplot layer (on top)
        sns.boxplot(
            data=long_df,
            x=category_col,
            y=score_col,
            hue="algorithm",
            order=cat_order,
            palette=ALGO_PALETTE,
            dodge=True,
            width=0.5,
            flierprops={"marker": ""},
            ax=ax,
        )

        ax.set_title(
            f"{get_display_name(score_col)} by {get_display_name(category_col)}",
            fontsize=13,
        )
        ax.set_xlabel(get_display_name(category_col))
        ax.set_ylabel(get_display_name(score_col))
        ax.set_yticks([1, 2, 3])
        ax.legend(title="Algorithm")

        fig.tight_layout()
        if output_path:
            fig.savefig(output_path, bbox_inches="tight", dpi=150)
        return fig


    def plot_score_sankey_style(
        self,
        df_a: pl.DataFrame,
        df_b: pl.DataFrame,
        label_a: str,
        label_b: str,
        score_col: str = "sepsis_score",
        output_path: Optional[Path] = None,
        figsize: tuple = (8, 6),
    ) -> plt.Figure:
        """
        Heatmap showing how encounters 'migrate' between score buckets
        from Algorithm A → Algorithm B.  A quick proxy for a Sankey diagram.
        Rows = Algo A score, Columns = Algo B score, values = % of total.
        """
        matrix = self.build_agreement_matrix(df_a, df_b, label_a, label_b,  score_col)
        pct_matrix = matrix / matrix.values.sum() * 100

        fig, ax = plt.subplots(figsize=figsize)

        sns.heatmap(
            pct_matrix,
            annot=matrix.values,       # show raw counts in cells
            fmt="d",
            cmap="YlGnBu",
            linewidths=0.5,
            linecolor="white",
            cbar_kws={"label": "% of All Encounters"},
            ax=ax,
        )

        # Overlay percentages as secondary annotation
        for i in range(pct_matrix.shape[0]):
            for j in range(pct_matrix.shape[1]):
                ax.text(
                    j + 0.5, i + 0.72,
                    f"({pct_matrix.iloc[i, j]:.1f}%)",
                    ha="center", va="center", fontsize=8, color="gray",
                )

        ax.set_title(
            f"Score Migration: {get_display_name(score_col)}\n({label_a} → {label_b})",
            fontsize=13,
        )
        ax.set_xlabel(f"{label_b} Score")
        ax.set_ylabel(f"{label_a} Score")

        fig.tight_layout()
        if output_path:
            fig.savefig(output_path, bbox_inches="tight", dpi=150)
        return fig


    # ──────────────────────────────────────────────
    # 4.  Summary statistics
    # ──────────────────────────────────────────────

    def compute_agreement_stats(
        self,
        df_a: pl.DataFrame,
        df_b: pl.DataFrame,
        label_a: str = "Algorithm A",
        label_b: str = "Algorithm B",
        score_col: str = "sepsis_score",
    ) -> dict:
        """
        Return a dict with:
        - total_encounters
        - exact_agreement_count / exact_agreement_pct
        - upgrade_count   (B > A)
        - downgrade_count (B < A)
        - cohens_kappa
        """
        joined = (
            df_a.select(["EncounterEpicCsn", score_col])
            .rename({score_col: label_a})
            .join(
                df_b.select(["EncounterEpicCsn", score_col])
                .rename({score_col: label_b}),
                on="EncounterEpicCsn",
                how="inner",
            )
        )

        pdf = joined.to_pandas()
        n = len(pdf)
        agree = (pdf[label_a] == pdf[label_b]).sum()
        upgrade = (pdf[label_b] > pdf[label_a]).sum()
        downgrade = (pdf[label_b] < pdf[label_a]).sum()

        # Cohen's kappa (simple)
        from sklearn.metrics import cohen_kappa_score
        kappa = cohen_kappa_score(pdf[label_a], pdf[label_b])

        return {
            "score_column": score_col,
            "total_encounters": n,
            "exact_agreement_count": int(agree),
            "exact_agreement_pct": round(agree / n * 100, 2) if n else 0,
            f"upgrade_count ({label_b} > {label_a})": int(upgrade),
            f"downgrade_count ({label_b} < {label_a})": int(downgrade),
            "cohens_kappa": round(kappa, 4),
        }


    # ──────────────────────────────────────────────
    # 5.  Main runner
    # ──────────────────────────────────────────────

    def _prepare_sepsis_df(self, df, col_name, score):
        return (
            df.group_by("EncounterEpicCsn")
            .agg(pl.col(col_name).min().alias("first_sepsis_instant"))
            .with_columns(pl.lit(score).alias("sepsis_score"))
            .select("EncounterEpicCsn", "first_sepsis_instant", "sepsis_score")
        )
    def _aggregate_sepsis(self, df_s1, df_s2, df_s3, strategy="max"):
        ds1 = self._prepare_sepsis_df(df_s1, "earliest_sepsis1_instance", 1)
        ds2 = self._prepare_sepsis_df(df_s2, "earliest_sepsis2_instance", 2)
        ds3 = self._prepare_sepsis_df(df_s3, "earliest_sepsis3_instance", 3)
        df_sall = pl.concat([ds1, ds2, ds3], how="vertical")

        if strategy == "max":
            return (
                df_sall.group_by("EncounterEpicCsn")
                .agg(
                    pl.col("sepsis_score").max().alias("sepsis_score"),
                    # First instant at which the max severity occurred:
                    pl.col("first_sepsis_instant")
                    .filter(pl.col("sepsis_score") == pl.col("sepsis_score").max())
                    .min()
                    .alias("first_sepsis_instant"),
                )
                .sort("EncounterEpicCsn")
            )
        elif strategy == "first":
            return (
                df_sall.group_by("EncounterEpicCsn")
                .agg(
                    pl.col("first_sepsis_instant").min().alias("first_sepsis_instant"),
                    # Highest severity at the earliest instant (tie-break):
                    pl.col("sepsis_score")
                    .filter(pl.col("first_sepsis_instant") == pl.col("first_sepsis_instant").min())
                    .max()
                    .alias("sepsis_score"),
                )
                .sort("EncounterEpicCsn")
            )

    def preprocess_experiment_df_dict(self, df_dict: dict[str, pl.DataFrame]):
        df_by_first = self._aggregate_sepsis(df_dict['df_sepsis1'], df_dict['df_sepsis2'], df_dict['df_sepsis3'], strategy="first")
        df_by_max = self._aggregate_sepsis(df_dict['df_sepsis1'], df_dict['df_sepsis2'], df_dict['df_sepsis3'], strategy="max")
        df_combined = df_by_first.join(
            df_by_max, on="EncounterEpicCsn", suffix="_at_max"
        )
        df_joined = df_combined.group_by(["EncounterEpicCsn", "first_sepsis_instant", "first_sepsis_instant_at_max"]).agg(
            pl.col("sepsis_score_at_max").max(),
            pl.col("sepsis_score").max()
        )
        df_joined = df_joined.join(
            df_dict['df_all'].group_by("EncounterEpicCsn").agg(
                pl.col("Arrival_Instant").min(),
                pl.col("InpatientAdmissionInstant").min(),
                pl.col("LengthOfStayInDays").first().cast(pl.Float64).alias("LOS_days"),
                pl.col("Sepsis_Category").first(),
                pl.col("Death_Flag").first(),
            ), on="EncounterEpicCsn"
        )
        return df_joined

    def compute_detection_summary(
        self,
        df_a: pl.DataFrame,
        df_b: pl.DataFrame,
        label_a: str = "Algorithm A",
        label_b: str = "Algorithm B",
    ) -> dict:
        """
        Compare which encounters each algorithm detected as sepsis-positive.

        An encounter is considered 'detected' if it has a non-null sepsis_score.

        Returns
        -------
        dict with detection counts, overlap, and unique-to-each-algorithm counts.
        """

        # Encounters with a non-null sepsis_score in each algorithm
        ids_a = set(
            df_a.filter(pl.col("sepsis_score").is_not_null())
            .get_column("EncounterEpicCsn")
            .to_list()
        )
        ids_b = set(
            df_b.filter(pl.col("sepsis_score").is_not_null())
            .get_column("EncounterEpicCsn")
            .to_list()
        )

        both      = ids_a & ids_b
        only_a    = ids_a - ids_b
        only_b    = ids_b - ids_a
        all_union = ids_a | ids_b

        summary = {
            f"{label_a} detected":          len(ids_a),
            f"{label_b} detected":          len(ids_b),
            "Detected by both":             len(both),
            f"Only in {label_a}":           len(only_a),
            f"Only in {label_b}":           len(only_b),
            "Union (any algorithm)":        len(all_union),
            "Jaccard similarity (%)":       round(len(both) / len(all_union) * 100, 2)
                                            if all_union else 0.0,
        }

        return summary, only_a, only_b, both


    def plot_detection_venn(
        self,
        df_a: pl.DataFrame,
        df_b: pl.DataFrame,
        label_a: str = "Algorithm A",
        label_b: str = "Algorithm B",
        output_path: Path | None = None,
        figsize: tuple = (8, 5),
    ) -> plt.Figure:
        """
        Stacked horizontal bar chart showing detection overlap.
        (A lightweight alternative to a Venn diagram that renders
        cleanly without matplotlib_venn.)
        """
        summary, only_a, only_b, both = self.compute_detection_summary(
            df_a, df_b, label_a, label_b
        )

        categories = ["Both Algorithms", f"Only {label_a}", f"Only {label_b}"]
        counts     = [len(both), len(only_a), len(only_b)]
        colors     = [ALGO_PALETTE.get(label_a, "#0066cc"),
                    "#66b2ff",
                    "#ffaa66"]

        fig, ax = plt.subplots(figsize=figsize)

        bars = ax.barh(categories, counts, color=colors, edgecolor="white")
        ax.bar_label(bars, fmt="%d", padding=5, fontsize=11)

        ax.set_xlabel("Number of Encounters")
        ax.set_title("Sepsis Detection Overlap Between Algorithms", fontsize=13)
        ax.invert_yaxis()

        fig.tight_layout()
        if output_path:
            fig.savefig(output_path, bbox_inches="tight", dpi=150)
        return fig


    def characterize_unique_encounters(
        self,
        df_source: pl.DataFrame,
        encounter_ids: set,
        label: str,
    ) -> pd.DataFrame:
        """
        For encounters detected by only one algorithm, return a summary
        of their clinical characteristics so you can assess whether
        the 'missed' encounters are clinically meaningful.

        Returns a pandas DataFrame with descriptive statistics.
        """
        unique_df = df_source.filter(
            pl.col("EncounterEpicCsn").is_in(list(encounter_ids))
        ).to_pandas()

        if unique_df.empty:
            print(f"  No unique encounters for {label}.")
            return pd.DataFrame()

        stats = {
            "algorithm":                label,
            "n_encounters":             len(unique_df),
            "death_flag_mean (%)":      round(unique_df["Death_Flag"].mean() * 100, 2),
            "LOS_days_median":          round(unique_df["LOS_days"].median(), 2),
            "LOS_days_mean":            round(unique_df["LOS_days"].mean(), 2),
            "sepsis_score_distribution": unique_df["sepsis_score"]
                                        .value_counts()
                                        .sort_index()
                                        .to_dict(),
            "sepsis_category_distribution": unique_df["Sepsis_Category"]
                                            .value_counts()
                                            .to_dict(),
        }

        return pd.DataFrame([stats])

    def run_comparison(
        self,
        df_a: pl.DataFrame,
        df_b: pl.DataFrame,
        label_a: str = "Algorithm A",
        label_b: str = "Algorithm B",
        output_dir: str | Path = "comparison_output",
    ) -> None:

        ALGO_PALETTE = {
            "Algorithm A": "#0066cc",   # medium-dark blue
            "Algorithm B": "#cc6600",   # contrasting amber/orange
        }

        SCORE_PALETTE_A = ["#cce5ff", "#66b2ff", "#0066cc"]   # score 1, 2, 3
        SCORE_PALETTE_B = ["#ffe0cc", "#ffaa66", "#cc6600"]   # score 1, 2, 3

        COLUMN_DISPLAY_NAMES = {
            "sepsis_score":              "Sepsis Score",
            "sepsis_score_at_max":       "Sepsis Score at Max",
            "Sepsis_Category":           "Billing Categorization",
            "first_sepsis_instant":      "First Sepsis Instant",
            "first_sepsis_instant_at_max": "First Sepsis Instant at Max",
            "detection_diff_hours":      "Detection Time Difference (Hours)",
            "LOS_days":                  "Length of Stay (Days)",
        }


        """
        End-to-end comparison: prints stats, saves all figures.
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)


        # ── NEW: Detection-level comparison ──────────────────
        summary, only_a, only_b, both = self.compute_detection_summary(
            df_a, df_b, label_a, label_b
        )

        print(f"\n{'='*55}")
        print(f"  Detection Summary")
        print(f"{'='*55}")
        for k, v in summary.items():
            print(f"  {k:>35s}: {v}")

        self.plot_detection_venn(
            df_a, df_b, label_a, label_b,
            output_path=output_path / "detection_overlap.png",
        )

        # Characterize encounters unique to each algorithm
        if only_a:
            char_a = self.characterize_unique_encounters(df_a, only_a, label_a)
            print(f"\n  Encounters only in {label_a}:")
            print(char_a.to_string(index=False))

        if only_b:
            char_b = self.characterize_unique_encounters(df_b, only_b, label_b)
            print(f"\n  Encounters only in {label_b}:")
            print(char_b.to_string(index=False))




        # ── Prepare long-form data ──
        long_df = self.prepare_joined_data(df_a, df_b, label_a, label_b)

        # Update palette keys to match user-supplied labels
        palette = {label_a: ALGO_PALETTE["Algorithm A"],
                label_b: ALGO_PALETTE["Algorithm B"]}
        # global ALGO_PALETTE
        ALGO_PALETTE = palette

        for score_col in ["sepsis_score", "sepsis_score_at_max"]:
            safe_name = score_col.replace(" ", "_")

            # ── Summary stats ──
            stats = self.compute_agreement_stats(df_a, df_b, score_col)
            print(f"\n{'='*50}")
            print(f"  Agreement Stats – {get_display_name(score_col)}")
            print(f"{'='*50}")
            for k, v in stats.items():
                print(f"  {k:>30s}: {v}")

            # ── Distribution (counts) ──
            self.plot_score_distribution(
                long_df, score_col,
                output_path=output_path / f"{safe_name}_distribution.png", ALGO_PALETTE=ALGO_PALETTE
            )

            # ── Distribution (normalized %) ──
            self.plot_score_distribution_normalized(
                long_df, score_col,
                output_path=output_path / f"{safe_name}_distribution_normalized.png", ALGO_PALETTE=ALGO_PALETTE
            )

            # ── Agreement heatmap ──
            matrix = self.build_agreement_matrix(df_a, df_b, label_a, label_b, score_col)
            self.plot_agreement_heatmap(
                matrix, score_col,
                output_path=output_path / f"{safe_name}_agreement_heatmap.png"
            )

            # ── Migration heatmap ──
            self.plot_score_sankey_style(
                df_a, df_b, label_a, label_b, score_col,
                output_path=output_path / f"{safe_name}_migration_heatmap.png",
            )

            # ── Score by Sepsis Category ──
            self.plot_score_by_category(
                long_df, score_col,
                output_path=output_path / f"{safe_name}_by_category.png", ALGO_PALETTE=ALGO_PALETTE
            )

        plt.close("all")
        print(f"\n✅ All figures saved to: {output_path.resolve()}")

    def analyze(self, label_a, label_b, output_dir):
        df_joined_1  = self.preprocess_experiment_df_dict(self.df_dict_1)
        df_joined_2 = self.preprocess_experiment_df_dict(self.df_dict_2)
        self.run_comparison(
                df_joined_1,
                df_joined_2,
                label_a=label_a,
                label_b=label_b,
                output_dir=output_dir
            )

