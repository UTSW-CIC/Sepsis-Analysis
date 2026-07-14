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

from src.configs.basic import BasicAnalysisConfig 
from src.utils.logger import get_logger
from src.utils.utils import load_output_folder 
import pandas as pd

NPOA_BLUES = ["#cce5ff", "#66b2ff", "#0066cc"]  # light to dark for NPOA-1,2,3
POA_BLUES  = ["#003d99", "#001f66", "#000a33"]  # darker shades for POA-1,2,3

COLUMN_DISPLAY_NAMES = {
    "Sepsis_Category":              "Billing Categorization",
    "POA_Arrival+48hrs":            "Arrival + 48 Hours",
    "POA_InpatientAdmissionInstant": "Inpatient Admission Time",
    "Arrival To Sepsis Time":       "Arrival To Sepsis Time (Hours)",
}

def get_display_name(col: str) -> str:
    return COLUMN_DISPLAY_NAMES.get(col, col) 

PALETTE_FULL = {
    "NPOA-1": NPOA_BLUES[0],
    "NPOA-2": NPOA_BLUES[1],
    "NPOA-3": NPOA_BLUES[2],
    "POA-1":  POA_BLUES[0],
    "POA-2":  POA_BLUES[1],
    "POA-3":  POA_BLUES[2],
}

PALETTE_AGG = {
    "NPOA": "#66b2ff",
    "POA":  "#003d99",
}

SEPSIS_CATEGORY_ORDER = [
    "NPOA-1", "NPOA-2", "NPOA-3",
    "POA-1", "POA-2", "POA-3",
]

PALETTE_SOURCE = {
    "Sepsis_Category":    "#66b2ff",  # medium blue
    "POA_Arrival+48hrs":  "#003d99",  # dark blue
    "POA_InpatientAdmissionInstant": "#001f66",

}

logger = get_logger(__name__)

class CoreAnalysis():
    def __init__(self, data_dir: Path, output_path: Path|str, basic_analysis_config: BasicAnalysisConfig) -> None:
        if isinstance(output_path, str):
            self.output_path = Path(output_path)
        elif isinstance(output_path, Path):
            self.output_path = output_path
        else: 
            raise ValueError("output_path must be a string or Path object")

        self.output_path.mkdir(parents=True, exist_ok=True)
        self.data_dir = data_dir
        self.basic_analyusis_config = basic_analysis_config
        self._load_dataframes()

    def _load_dataframes(self):
        self.df_dict = load_output_folder(self.data_dir, logger)

    def _get_dfenc(self):
        df_all = self.df_dict['df_all']
        return df_all.select(self.basic_analyusis_config.encounter_level_info_cols).group_by(self.basic_analyusis_config.encounter_col).last()

    def _assignPOAvNPOA(self, df_joined, hours_after_arrival=48, hours_after_inpatient_admission=0):
        df_joined =  df_joined.with_columns(
            pl.when(pl.col("first_sepsis_instant") <= (pl.col("Arrival_Instant")+pl.duration(hours=hours_after_arrival))).then(pl.lit("POA")).otherwise(pl.lit("NPOA")).alias("POA_Arrival+48hrs_class"),
            pl.when(pl.col("first_sepsis_instant") <= (pl.col("InpatientAdmissionInstant")+pl.duration(hours=hours_after_inpatient_admission))).then(pl.lit("POA")).otherwise(pl.lit("NPOA")).alias("POA_InpatientAdmissionInstant_class"),
        )
        return df_joined.with_columns(
            (pl.col("POA_Arrival+48hrs_class")+'-'+pl.col("sepsis_score_at_max").cast(pl.String)).alias("POA_Arrival+48hrs"),
            (pl.col("POA_InpatientAdmissionInstant_class")+'-'+pl.col("sepsis_score_at_max").cast(pl.String)).alias("POA_InpatientAdmissionInstant")
        )

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


    def crosstab(self, df, col1_index, col2_cols):
        crosstab = (
            df
            .group_by([col1_index, col2_cols])
            .agg(pl.len().alias("count"))
            .pivot(
                on=col2_cols,       # these values become column headers
                index=col1_index,   # this stays as the row identifier
                values="count",
                aggregate_function="first"  # there's only one value per group since we already aggregated
            )
            .fill_null(0)
            .sort(by=col1_index)
        )
        return crosstab

    
    def _process_crosstab(self, crosstab_df, index_col):
        crosstab_noU = crosstab_df.drop([c for c in crosstab_df.columns if c.startswith("U")])
        clean_billing_valus = [c for c in self.basic_analyusis_config.billing_values_order if not c.startswith("U")]
        crosstab_noU = crosstab_noU.select([index_col]+clean_billing_valus)
        crosstab_noU = crosstab_noU.with_columns(
            pl.sum_horizontal(set(crosstab_noU.columns)-{index_col}).alias("total")
        )
        crosstab_noU = pl.concat([crosstab_noU, crosstab_noU.sum()], how='vertical').fill_null("total")
        return crosstab_noU


    def plot_sepsis_heatmap(
        self,
        crosstab: pl.DataFrame,
        normalize: str = "row",  # "row" or "col"
        index_col: str = "max_sepsis_score",
        sum_row_label = "sum",  # whatever label you used for the sum row
        sum_col_label = "sum",  # whatever label you used for the sum row
        figsize: tuple = (10, 7),
        fmt_pct: str = ".1%",
        fmt_count: str = "d",
        title_suffix_label: str="Arrival Time + 48 Hours",
        filename: str = "sepsis_heatmap.png",
    ):
        # ── 1. Separate core matrix from margins ─────────────────────────────
        # Split sum row vs core rows
        core = crosstab.filter(pl.col(index_col) != sum_row_label)
        sum_row = crosstab.filter(pl.col(index_col) == sum_row_label)

        # Category columns = everything except the index and the row-sum col
        # Adjust "sum" if you named the horizontal sum column differently
        cat_cols = [c for c in crosstab.columns if c not in [index_col, sum_col_label]]

        # Row labels (your algorithm scores)
        row_labels = core[index_col].to_list()

        # Core matrix as numpy (rows=algo score, cols=billing category)
        matrix = core.select(cat_cols).to_numpy().astype(float)  # shape (n_scores, n_categories)

        # ── 2. Extract margins for normalization ─────────────────────────────
        if normalize == "row":
            # row sums: pull from the "sum" column you already computed
            row_sums = core["sum"].to_numpy().astype(float)          # shape (n_scores,)
            norm_matrix = matrix / row_sums[:, np.newaxis]           # broadcast across columns

        elif normalize == "col":
            # col sums: pull from the sum row
            col_sums = sum_row.select(cat_cols).to_numpy().astype(float)  # shape (1, n_categories)
            norm_matrix = matrix / col_sums                               # broadcast across rows

        else:
            raise ValueError("normalize must be 'row' or 'col'")

        # ── 3. Build annotation: "pct\n(raw count)" ──────────────────────────
        annot = np.empty(matrix.shape, dtype=object)
        for i in range(matrix.shape[0]):
            for j in range(matrix.shape[1]):
                pct_str = format(norm_matrix[i, j], fmt_pct)
                count_str = format(int(matrix[i, j]), fmt_count)
                annot[i, j] = f"{pct_str}\n({count_str})"

        # ── 4. Plot ───────────────────────────────────────────────────────────
        fig, ax = plt.subplots(figsize=figsize)

        diag_mask = np.eye(matrix.shape[0], matrix.shape[1], dtype=bool)

        sns.heatmap(
            1 - norm_matrix,
            ax=ax,
            annot=annot,
            fmt="",
            cmap="Blues",
            vmin=0, vmax=1,
            mask=diag_mask,          # <-- excludes diagonal from colormap
            linewidths=0.5,
            linecolor="white",
            cbar_kws={"label": f"Mismatch proportion ({'row' if normalize == 'row' else 'column'} normalized)"},
            xticklabels=cat_cols,
            yticklabels=row_labels,
        )
        # ?? Re-annotate diagonal cells manually ??????????????????????????????????
        for i in range(min(matrix.shape)):
            ax.text(
                i + 0.5, i + 0.5,        # center of cell (col+0.5, row+0.5)
                annot[i, i],
                ha="center", va="center",
                fontsize=10,
                color="black",
            )

        # ?? Diagonal border ???????????????????????????????????????????????????????
        for i in range(min(matrix.shape)):
            ax.add_patch(Rectangle((i, i), 1, 1, fill=False, edgecolor="green", linewidth=2.5, clip_on=False))

        # ?? Highlight diagonal cells with a green border ?????????????????????????
        for i in range(min(matrix.shape)):
            ax.add_patch(Rectangle(
                (i, i),                # (x, y) in data coordinates = (col, row)
                1, 1,                  # width, height = one cell
                fill=False,
                edgecolor="green",
                linewidth=2.5,
                clip_on=False
            ))


        # ── 5. Move x-axis labels to top ─────────────────────────────────────
        ax.xaxis.tick_top()                        # move ticks to top
        ax.xaxis.set_label_position("top")         # move axis label to top
        ax.tick_params(axis="x", length=0)         # hide tick marks, keep labels
        ax.tick_params(axis="y", length=0)
        plt.xticks(rotation=30, ha="left")         # ha="left" looks better on top

        direction = "Row" if normalize == "row" else "Column"
        ax.set_title(
            f"Computed Category vs Billing Category ({direction}-Normalized) - {title_suffix_label}",
            pad=20,                                # padding so title clears the top labels
        )
        ax.set_ylabel("Computed Sepsis Category")
        ax.set_xlabel("Billing Sepsis Category", labelpad=12)
        fig.savefig(self.output_path / Path(filename), bbox_inches="tight")
        # plt.tight_layout()
        # plt.show()

    def plot_sepsis_heatmap_with_row_and_col_totals(
    self,
    crosstab: pl.DataFrame,
    normalize: str = "row",  # "row" or "col"
    index_col: str = "max_sepsis_score",
    sum_row_label="sum",
    sum_col_label="sum",
    figsize: tuple = (10, 7),
    fmt_pct: str = ".1%",
    fmt_count: str = "d",
    margin_fmt: str = ",d",
    title_suffix_label: str = "Arrival Time + 48 Hours",
    filename: str = "sepsis_heatmap.png",
    ):
        # 1. Separate core matrix from margins
        core = crosstab.filter(pl.col(index_col) != sum_row_label)
        sum_row = crosstab.filter(pl.col(index_col) == sum_row_label)

        cat_cols = [
            c for c in crosstab.columns
            if c not in [index_col, sum_col_label]
        ]

        row_labels = core[index_col].to_list()

        matrix = core.select(cat_cols).to_numpy().astype(float)

        # 2. Extract row and column totals
        row_sums = core[sum_col_label].to_numpy().astype(float)

        if sum_row.height == 0:
            raise ValueError(
                f"No sum row found where {index_col} == {sum_row_label}"
            )

        col_sums = sum_row.select(cat_cols).to_numpy().ravel().astype(float)

        # 3. Normalize safely
        if normalize == "row":
            norm_matrix = np.divide(
                matrix,
                row_sums[:, np.newaxis],
                out=np.zeros_like(matrix, dtype=float),
                where=row_sums[:, np.newaxis] != 0,
            )

        elif normalize == "col":
            norm_matrix = np.divide(
                matrix,
                col_sums[np.newaxis, :],
                out=np.zeros_like(matrix, dtype=float),
                where=col_sums[np.newaxis, :] != 0,
            )

        else:
            raise ValueError("normalize must be 'row' or 'col'")

        # 4. Build annotation: "pct\n(raw count)"
        annot = np.empty(matrix.shape, dtype=object)

        for i in range(matrix.shape[0]):
            for j in range(matrix.shape[1]):
                pct_str = format(norm_matrix[i, j], fmt_pct)
                count_str = format(int(matrix[i, j]), fmt_count)
                annot[i, j] = f"{pct_str}\n({count_str})"

        # 5. Plot
        fig, ax = plt.subplots(figsize=figsize)

        n_rows, n_cols = matrix.shape

        diag_mask = np.eye(n_rows, n_cols, dtype=bool)

        sns.heatmap(
            1 - norm_matrix,
            ax=ax,
            annot=annot,
            fmt="",
            cmap="Blues",
            vmin=0,
            vmax=1,
            mask=diag_mask,
            linewidths=0.5,
            linecolor="white",
            cbar_kws={
                "label": (
                    f"Mismatch proportion "
                    f"({'row' if normalize == 'row' else 'column'} normalized)"
                )
            },
            xticklabels=cat_cols,
            yticklabels=row_labels,
        )

        # 6. Re-annotate diagonal cells manually
        for i in range(min(n_rows, n_cols)):
            ax.text(
                i + 0.5,
                i + 0.5,
                annot[i, i],
                ha="center",
                va="center",
                fontsize=10,
                color="black",
            )

        # 7. Highlight diagonal cells with a green border
        for i in range(min(n_rows, n_cols)):
            ax.add_patch(
                Rectangle(
                    (i, i),
                    1,
                    1,
                    fill=False,
                    edgecolor="green",
                    linewidth=2.5,
                    clip_on=False,
                )
            )

        # 8. Add row totals on the right
        row_total_x = n_cols + 0.15

        for i, total in enumerate(row_sums):
            ax.text(
                row_total_x,
                i + 0.5,
                format(int(total), margin_fmt),
                ha="left",
                va="center",
                fontsize=10,
                fontweight="bold",
                color="black",
                clip_on=False,
            )

        # ax.text(
        #     row_total_x,
        #     -0.35,
        #     "Row total",
        #     ha="left",
        #     va="center",
        #     fontsize=10,
        #     fontweight="bold",
        #     color="black",
        #     clip_on=False,
        # )

        # 9. Add column totals above each column
        col_total_y = -0.25

        for j, total in enumerate(col_sums):
            ax.text(
                j + 0.5,
                col_total_y,
                format(int(total), margin_fmt),
                ha="center",
                va="center",
                fontsize=10,
                fontweight="bold",
                color="black",
                clip_on=False,
            )

        # ax.text(
        #     -0.15,
        #     col_total_y,
        #     "Col total",
        #     ha="right",
        #     va="center",
        #     fontsize=10,
        #     fontweight="bold",
        #     color="black",
        #     clip_on=False,
        # )

        # 10. Expand limits so external text is visible
        ax.set_xlim(0, n_cols + 1.35)
        ax.set_ylim(n_rows, -0.55)

        # 11. Move x-axis labels to top
        ax.xaxis.tick_top()
        ax.xaxis.set_label_position("top")
        ax.tick_params(axis="x", length=0)
        ax.tick_params(axis="y", length=0) 

        plt.xticks(rotation=30, ha="left")

        direction = "Row" if normalize == "row" else "Column"

        ax.set_title(
            f"Computed Category vs Billing Category ({direction}-Normalized) - {title_suffix_label}",
            pad=35,
        )

        ax.set_ylabel("Computed Sepsis Category")
        ax.set_xlabel("Billing Sepsis Category", labelpad=12)

        fig.savefig(self.output_path / Path(filename), bbox_inches="tight")


    def plot_category_comparison(
        self,
        df: pl.DataFrame,
        cols: list = ["Sepsis_Category", "POA_Arrival+48hrs"],
        aggregate_poa: bool = False,
        figsize: tuple = (10, 6),
        filename="category_comparison.png"
    ):
        pdf = df.select(cols).to_pandas()

        if aggregate_poa:
            for col in cols:
                pdf[col] = pdf[col].str.replace(r"-\d+", "", regex=True)
            palette = PALETTE_AGG
        else:
            palette = PALETTE_FULL

        # ?? Count frequencies in each column independently ????????????????????
        frames = []
        for col in cols:
            counts = pdf[col].value_counts().rename("count").reset_index()
            counts.columns = ["category", "count"]
            counts["source"] = get_display_name(col)
            frames.append(counts)

        merged = pd.concat(frames, ignore_index=True)

        # ?? Sort order ????????????????????????????????????????????????????????
        cat_order = sorted(merged["category"].unique(), key=lambda x: (0 if "NPOA" in x else 1, x))

        # ?? Build palette dynamically from display names ??????????????????????
        # source_colors = ["#cce5ff", "#66b2ff", "#003d99", "#001f66"]  # light to dark blues
        source_colors = ["#ff7f0e", "#66b2ff", "#003d99", "#001f66"]

        sources = [get_display_name(col) for col in cols]
        palette_display = {source: color for source, color in zip(sources, source_colors)}

        # ?? Plot ??????????????????????????????????????????????????????????????
        fig, ax = plt.subplots(figsize=figsize)

        sns.barplot(
            data=merged,
            x="category",
            y="count",
            hue="source",
            order=cat_order,
            palette=palette_display,
            ax=ax,
        )

        title_cols = " vs ".join([get_display_name(col) for col in cols])
        ax.set_title(f"Category Counts: {title_cols}")
        ax.set_xlabel("Category")
        ax.set_ylabel("Count")
        ax.legend(title="Source")
        fig.savefig(self.output_path / Path(filename), bbox_inches="tight") 

        # plt.tight_layout()
        # plt.show()


    def plot_sepsis_time_boxplot(
        self,
        df: pl.DataFrame,
        time_col: str = "Arrival To Sepsis Time",
        group_cols: list = ["Sepsis_Category", "POA_Arrival+48hrs"],
        aggregate_poa: bool = False,
        figsize: tuple = (12, 6),
        filename="sepsis_time_boxplot.png"
    ):
        # ?? Melt each group column into long format ???????????????????????????
        frames = []
        for col in group_cols:
            tmp = df.select([time_col, col]).to_pandas()
            if aggregate_poa:
                tmp[col] = tmp[col].str.replace(r"-\d+", "", regex=True)
            tmp = tmp.rename(columns={col: "category"})
            tmp["source"] = col
            frames.append(tmp)

        melted = pd.concat(frames, ignore_index=True)
        melted["source"] = melted["source"].map(lambda x: get_display_name(x))
        palette_display = {get_display_name(k): v for k, v in PALETTE_SOURCE.items()}


        # ?? Sort order ????????????????????????????????????????????????????????
        cat_order = sorted(melted["category"].unique(), key=lambda x: (0 if "NPOA" in x else 1, x))

        palette = PALETTE_AGG if aggregate_poa else PALETTE_FULL

        # ?? Plot ??????????????????????????????????????????????????????????????
        fig, ax = plt.subplots(figsize=figsize)

        # Scatter first (below)
        sns.stripplot(
            data=melted,
            x="category",
            y=time_col,
            hue="source",
            order=cat_order,
            palette=palette_display,
            dodge=True,
            alpha=0.3,
            size=3,
            jitter=True,
            ax=ax,
            legend=False,
        )

        # Boxplot on top
        sns.boxplot(
            data=melted,
            x="category",
            y=time_col,
            hue="source",
            order=cat_order,
            palette=palette_display,
            dodge=True,
            width=0.5,
            flierprops={"marker": ""},   # hide outlier markers since scatter shows all points
            ax=ax,
        )

        ax.set_title(f"{get_display_name(time_col)} by Category")
        ax.set_xlabel("Category")
        ax.set_ylabel(get_display_name(time_col))
        ax.legend(title="Source")

        fig.savefig(self.output_path / Path(filename), bbox_inches="tight")
        # plt.tight_layout()
        # plt.show()

    def plot_los_distribution(
        self,
        df: pl.DataFrame,
        los_col: str = "LOS_days",
        poa_col: str = "POA_Arrival+48hrs",
        billing_col: str = "Sepsis_Category",
        target_category: str = "POA-3",
        figsize: tuple = (12, 6),
        figtitle_prefix: str = "LOS Distribution",
        xlabel: str = "Length of Stay (Days)",
        filename="los_distribution.png"
    ):
        # ?? Filter the three groups ???????????????????????????????????????????
        group2 = df.filter(
            (pl.col(poa_col) == target_category) & (pl.col(billing_col) != target_category)
        ).select(los_col).to_pandas()
        group2["source"] = f"Computed={target_category}\nBilling ≠ {target_category}"

        group1 = df.filter(
            (pl.col(billing_col) == target_category) & (pl.col(poa_col) != target_category)
        ).select(los_col).to_pandas()
        group1["source"] = f"Billing={target_category}\nComputed ≠ {target_category}"

        group3 = df.filter(
            (pl.col(poa_col) == target_category) & (pl.col(billing_col) == target_category)
        ).select(los_col).to_pandas()
        group3["source"] = f"Billing={target_category}\nComputed = {target_category}"

        melted = pd.concat([group1, group2, group3], ignore_index=True)
        melted[los_col] = melted[los_col].astype(float)

        # ?? Order: match first, then discordant groups ????????????????????????
        # source_order = melted["source"].unique().tolist()
        # colors = ["#003d99", "#66b2ff", "#cce5ff"]
        # palette = {source: color for source, color in zip(source_order, colors)}
        # # ?? Palette: dark blue for match, medium and light for mismatches ?????
        # colors = ["#003d99", "#66b2ff", "#cce5ff"]
        # unique_sources = [s for s in source_order if s in melted["source"].unique().tolist()]
        # palette = {source: color for source, color in zip(unique_sources, colors)}
        # palette = {
        #     f"Both={target_category}":                          "#003d99",
        #     f"Algorithm={target_category}\nBilling={target_category}": "#66b2ff",
        #     f"Billing={target_category}\nAlgorithm={target_category}": "#cce5ff",
        # }
        
        source_order = melted["source"].unique().tolist()
        colors = ["#DD8452", "#4C72B0", "#917B6F"]
        palette = {source: color for source, color in zip(source_order, colors)}

        # ?? Plot ??????????????????????????????????????????????????????????????
        fig, ax_box = plt.subplots(figsize=figsize)
        # fig, (ax_box, ax_kde) = plt.subplots(
        #     2, 1,
        #     figsize=figsize,
        #     gridspec_kw={"height_ratios": [1, 1.5]},
        # )

        sns.stripplot(
            data=melted,
            y="source",
            x=los_col,
            order=source_order,
            color="#aaaaaa",
            alpha=0.3,
            size=3,
            jitter=True,
            ax=ax_box,
            legend=False,
        )

        sns.boxplot(
            data=melted,
            y="source",
            x=los_col,
            order=source_order,
            palette=palette,
            width=0.5,
            flierprops={"marker": ""},
            ax=ax_box,
        )
        for i, source in enumerate(source_order):
            subset = melted[melted["source"] == source][los_col]
            q1     = subset.quantile(0.25)
            median = subset.quantile(0.50)
            q3     = subset.quantile(0.75)

            ax_box.text(
                median, i-0.35,
                f"  Q1={q1:.1f}  Md={median:.1f}  Q3={q3:.1f}",
                va="center", ha="left",
                fontsize=8,
                color="black",
            )

        ax_box.set_title(f"{figtitle_prefix}: {target_category} Agreement vs Disagreement")
        ax_box.set_ylabel("")
        ax_box.set_xlabel(xlabel)

        #########################################
            # ?? Row 2: KDE + histogram ????????????????????????????????????????????
        # for source in source_order:
        #     subset = melted[melted["source"] == source][los_col]
        #     label = source.replace("\n", " ")
        #     sns.histplot(
        #         subset,
        #         ax=ax_kde,
        #         # color=palette[source],
        #         color=  ["#003d99", "#ff7f0e", "#d62728"],  # blue, orange, red

        #         alpha=0.1,
        #         binwidth=1,
        #         stat="density",
        #         label=label,
        #     )
        #     sns.kdeplot(
        #         subset,
        #         ax=ax_kde,
        #         # color=palette[source],

        #         color=  ["#003d99", "#ff7f0e", "#d62728"],  # blue, orange, red
        #         linewidth=2,
        #     )

        # ax_kde.set_xlabel("Length of Stay (Days)")
        # ax_kde.set_ylabel("Density")
        # ax_kde.legend(title="Group")
        
        fig.savefig(self.output_path / Path(filename), dpi=300, bbox_inches="tight")

    def plot_medication_distribution(
        self,
        df: pl.DataFrame,
        med_col: str = "MedicationCount",          # ← swap for your actual column name
        poa_col: str = "POA_Arrival+48hrs",
        billing_col: str = "Sepsis_Category",
        target_category: str = "POA-3",
        figsize: tuple = (12, 6),
        clip_quantile: float | None = 0.99,        # tame the long tail for readability; None = off
        filename: str = "medication_distribution.png",
    ):
        # ── Three concordance groups (identical logic to LOS) ──────────────────
        group1 = df.filter(
            (pl.col(poa_col) == target_category) & (pl.col(billing_col) != target_category)
        ).select(med_col).to_pandas()
        group1["source"] = f"Computed={target_category}\nBilling ≠ {target_category}"

        group2 = df.filter(
            (pl.col(billing_col) == target_category) & (pl.col(poa_col) != target_category)
        ).select(med_col).to_pandas()
        group2["source"] = f"Billing={target_category}\nComputed ≠ {target_category}"

        group3 = df.filter(
            (pl.col(poa_col) == target_category) & (pl.col(billing_col) == target_category)
        ).select(med_col).to_pandas()
        group3["source"] = f"Both={target_category}"

        melted = pd.concat([group1, group2, group3], ignore_index=True)
        melted[med_col] = melted[med_col].astype(float)

        # ── Palette: dark blue = match, medium/light = the two discordant cells ─
        source_order = melted["source"].unique().tolist()
        colors  = ["#003d99", "#66b2ff", "#cce5ff"]
        palette = {src: col for src, col in zip(source_order, colors)}

        # ── Optional tail clip (annotations still use the FULL data) ───────────
        plot_df = melted
        if clip_quantile is not None:
            hi = melted[med_col].quantile(clip_quantile)
            plot_df = melted[melted[med_col] <= hi]

        # ── Plot: strip behind, box on top (your LOS idiom) ────────────────────
        fig, ax_box = plt.subplots(figsize=figsize)

        sns.stripplot(
            data=plot_df, y="source", x=med_col, order=source_order,
            color="#aaaaaa", alpha=0.3, size=3, jitter=True, ax=ax_box, legend=False,
        )
        sns.boxplot(
            data=plot_df, y="source", x=med_col, order=source_order,
            palette=palette, width=0.5, flierprops={"marker": ""}, ax=ax_box,
        )

        # ── Quartile annotations computed on the UNCLIPPED data ────────────────
        for i, source in enumerate(source_order):
            subset = melted[melted["source"] == source][med_col]
            q1, median, q3 = subset.quantile(0.25), subset.quantile(0.50), subset.quantile(0.75)
            ax_box.text(
                median, i - 0.35,
                f"  Q1={q1:.1f}  Md={median:.1f}  Q3={q3:.1f}",
                va="center", ha="left", fontsize=8, color="black",
            )

        ax_box.set_title(f"Medications Administered: {target_category} Agreement vs Disagreement")
        ax_box.set_ylabel("")
        ax_box.set_xlabel("Medications Administered (count)")

        fig.savefig(self.output_path / Path(filename), dpi=300, bbox_inches="tight")

    def plot_medgroup_distribution_heatmap(
        self,
        med_long: pl.DataFrame,            # long table: (EncounterEpicCsn, Event_Grouper, meds_count)
        sepsis_labels: pl.DataFrame,       # one row per encounter: (EncounterEpicCsn, <group_col>)
        group_col: str = "Sepsis_Category",
        normalize: str = "col",            # "col" → each stratum sums to 1 (medication mix)
                                        # "row" → each medication sums to 1 (across-stratum spread)
        stratum_order: list | None = None,
        figsize: tuple = (10, 7),
        cmap: str = "Blues",
        title_suffix: str = "",
        filename: str = "med_distribution_heatmap.png",
    ):
        """Heatmap of medication-event distribution across sepsis strata.

        Rows = medication groups (alphabetical), columns = strata.
        `normalize` chooses which axis sums to 1; color encodes that share,
        annotation shows `share% (raw event count)`.
        """
        strata = stratum_order or ["POA-1", "POA-2", "POA-3", "NPOA-1", "NPOA-2", "NPOA-3"]

        # ── 1. TRANSFORM: join labels → total events per (medication, stratum) ─────────
        # inner join: encounters absent from the med table contribute no events and
        # are correctly excluded from an event-share figure. Capture the drop count so
        # heavy attrition surfaces as a data-completeness finding rather than a silent gap.
        n_cohort = sepsis_labels.height
        joined = med_long.join(
            sepsis_labels.select("EncounterEpicCsn", group_col),
            on="EncounterEpicCsn", how="inner",
        )
        n_kept = joined.get_column("EncounterEpicCsn").n_unique()
        if n_kept < n_cohort:
            print(f"[med heatmap] {n_cohort - n_kept} of {n_cohort} cohort encounters "
                f"had no medication events and were dropped from the figure.")

        wide = (
            joined.group_by([group_col, "Event_Grouper"])
                .agg(pl.col("meds_count").sum().alias("events"))
                .pivot(values="events", index="Event_Grouper", on=group_col)
                .fill_null(0)                       # absent (med, stratum) combos = 0 events
                .sort("Event_Grouper")              # alphabetical row order = predictable lookup
        )

        med_order = wide.get_column("Event_Grouper").to_list()
        strata = [s for s in strata if s in wide.columns]        # tolerate a missing stratum
        events = wide.select(strata).to_numpy().astype(float)    # shape: (n_meds, n_strata)

        # ── 2. NORMALIZE: safe divide, denominator axis set by `normalize` ─────────────
        # keepdims keeps the sum broadcastable against `events`; out/where guard a
        # zero-total axis (→ 0, never nan/inf). This is your concordance template's core.
        if normalize == "col":
            denom = events.sum(axis=0, keepdims=True)            # per-stratum total
        elif normalize == "row":
            denom = events.sum(axis=1, keepdims=True)            # per-medication total
        else:
            raise ValueError("normalize must be 'col' or 'row'")
        share = np.divide(events, denom, out=np.zeros_like(events), where=denom != 0)

        # ── 3. ANNOTATION: active-direction share % over constant raw count ────────────
        annot = np.empty(events.shape, dtype=object)
        for i in range(events.shape[0]):
            for j in range(events.shape[1]):
                annot[i, j] = f"{share[i, j] * 100:.1f}%\n({int(events[i, j]):,})"

        # ── 4. RENDER: your house theme (Blues, white gridlines, x-axis on top) ────────
        fig, ax = plt.subplots(figsize=figsize)
        sns.heatmap(
            share, ax=ax, annot=annot, fmt="", cmap=cmap,
            vmin=0, vmax=float(share.max()),
            linewidths=0.5, linecolor="white",
            cbar_kws={"label": f"Share of medication events "
                            f"({'column' if normalize == 'col' else 'row'}-normalized)"},
            xticklabels=strata, yticklabels=med_order,
        )
        ax.xaxis.tick_top()
        ax.xaxis.set_label_position("top")
        ax.tick_params(axis="x", length=0)
        ax.tick_params(axis="y", length=0)
        plt.setp(ax.get_xticklabels(), rotation=30, ha="left")

        direction = "Column" if normalize == "col" else "Row"
        ax.set_title(
            f"Medication Distribution by {group_col} ({direction}-Normalized)"
            f"{(' — ' + title_suffix) if title_suffix else ''}",
            pad=35,
        )
        ax.set_ylabel("Medication Group")
        ax.set_xlabel(group_col, labelpad=12)

        fig.savefig(self.output_path / Path(filename), dpi=200, bbox_inches="tight")
        plt.close(fig)
        return wide       # return the raw matrix so you can sanity-check numbers outside the plot

    def plot_death_flag_distribution_ratio(
        self,
        df: pl.DataFrame,
        flag_col: str = "Death_Flag",
        poa_col: str = "POA_Arrival+48hrs",
        billing_col: str = "Sepsis_Category",
        target_category: str = "POA-3",
        figsize: tuple = (12, 6),
        filename: str = "death_flag_distribution_ratio.png",
    ):
        # ?? Filter the three groups ???????????????????????????????????????????
        group2 = df.filter(
            (pl.col(poa_col) == target_category) & (pl.col(billing_col) != target_category)
        ).select(flag_col).to_pandas()
        group2["source"] = f"Computed={target_category}\nBilling ≠ {target_category}"

        group1 = df.filter(
            (pl.col(billing_col) == target_category) & (pl.col(poa_col) != target_category)
        ).select(flag_col).to_pandas()
        group1["source"] = f"Billing={target_category}\nComputed ≠ {target_category}"

        group3 = df.filter(
            (pl.col(poa_col) == target_category) & (pl.col(billing_col) == target_category)
        ).select(flag_col).to_pandas()
        group3["source"] = f"Billing={target_category}\nComputed = {target_category}"

        melted = pd.concat([group1, group2, group3], ignore_index=True)

        source_order = melted["source"].unique().tolist()

        # ?? Compute % per group ???????????????????????????????????????????????
        proportions = (
            melted.groupby("source")[flag_col]
            .value_counts(normalize=True)
            .mul(100)
            .rename("pct")
            .reset_index()
        )

        # Pivot to wide: rows=source, cols=flag values
        pivot = proportions.pivot(index="source", columns=flag_col, values="pct").fillna(0)
        pivot = pivot.loc[source_order]  # enforce order

        # ?? Plot stacked bar ??????????????????????????????????????????????????
        fig, ax = plt.subplots(figsize=figsize)

        flag_values = pivot.columns.tolist()
        bar_colors  = ["#003d99", "#d62728"]  # blue for 0/No, red for 1/Yes

        bottom = np.zeros(len(source_order))
        for val, color in zip(flag_values, bar_colors):
            ax.bar(
                source_order,
                pivot[val],
                bottom=bottom,
                color=color,
                label=str(val),
                width=0.5,
            )
            # Annotate each segment with its percentage
            for i, (pct, bot) in enumerate(zip(pivot[val], bottom)):
                if pct > 3:  # skip annotation if segment too small to read
                    ax.text(
                        i, bot + pct / 2,
                        f"{pct:.1f}%",
                        ha="center", va="center",
                        fontsize=10, color="white", fontweight="bold",
                    )
            bottom += pivot[val].values

        group_counts = melted.groupby("source").size()
        for i, source in enumerate(source_order):
            n = group_counts[source]
            if i<2:
                ax.text(
                    i +0.3, 90,          # just above the bar
                    f"n={n}",
                    ha="left", va="bottom",
                    fontsize=9, color="black",
                )
            else:
                ax.text(
                    i -0.4, 60,          # just above the bar
                    f"n={n}",
                    ha="left", va="bottom",
                    fontsize=9, color="black",
                )

        ax.set_ylim(0, 100)
        ax.set_ylabel("Percentage (%)")
        ax.set_xlabel("")
        ax.set_title(f"Death Flag Distribution: {target_category} Agreement vs Disagreement")
        ax.legend(title=flag_col)
        fig.savefig(self.output_path / Path(filename), dpi=300, bbox_inches="tight")
        # plt.tight_layout()
        # plt.show()
    
    def _extract_severity_from_billing_calculated(self, df: pl.DataFrame, billing_col: str = "Sepsis_Category",
                                                  billing_score_col: str = "billing_score", computed_col: str = None, computed_score_col: str = "computed_score"):
        expr = [
            pl.col(billing_col).str.extract(r"(\d+)").cast(pl.Int64).alias(billing_score_col)
        ]
        if computed_col is not None:
            expr.append(pl.col(computed_col).str.extract(r"(\d+)").cast(pl.Int64).alias(computed_score_col))
        return df.with_columns(expr)

    def _add_first_pressors(self, df: pl.DataFrame, df_all: pl.DataFrame, pressors_grouper_vals: List=[], billing_col:str="Sepsis_Category", computed_col:str="POA_Arrival+48hrs"):
        # poa3_npoa3_billing_comp_encs = df.filter(
        #     pl.col(computed_col).is_in(["NPOA-3", 'POA-3'])|
        #     pl.col(billing_col).is_in(['NPOA-3', 'POA-3'])
        # )['EncounterEpicCsn'].unique()

        df_pressors = df_all.filter(
            # pl.col("EncounterEpicCsn").is_in(poa3_npoa3_billing_comp_encs)&
            pl.col("Event_Grouper").is_in(pressors_grouper_vals)
        ).group_by("EncounterEpicCsn").agg(pl.col("Event_DateTime").min(), pl.col("Sepsis_Category").first(),
                                           pl.col("Arrival_Instant").first(), pl.col("InpatientAdmissionInstant").first()).sort(by=["EncounterEpicCsn", "Event_DateTime"])\
            .with_columns(
                (pl.col("Event_DateTime")-pl.col("Arrival_Instant")).dt.total_hours(fractional=True).alias("arrival to first pressor hrs"),
                (pl.col("Event_DateTime")-pl.col("InpatientAdmissionInstant")).dt.total_hours(fractional=True).alias("admit to first pressor hrs")
            )
        df_pressors = df_pressors.rename({"Event_DateTime":"first_pressor_time"}).join(
                        df,
                        on='EncounterEpicCsn',
                        how='inner'
                    ).select("EncounterEpicCsn", billing_col, computed_col, "arrival to first pressor hrs", "admit to first pressor hrs")

        return df_pressors

        # df_pressors_first = df_all.join(
        #     df_pressors,
        #     on=["EncounterEpicCsn", "Event_DateTime"],
        #     how='inner',
        #     suffix='_firstpressortime'
        # ).filter(pl.col("Event_Grouper").is_in(pressors_grouper_vals)).sort(by=["EncounterEpicCsn", "Event_DateTime"])

        # df_pressors_first_enc = df.join(
        #     df_pressors_first,
        #     on="EncounterEpicCsn",
        #     how="inner"
        # ).with_columns(
        #     (pl.col("Event_DateTime")-pl.col("Arrival_Instant")).dt.total_hours(fractional=True).alias("arrival to first pressor hrs"),
        #     (pl.col("Event_DateTime")-pl.col("InpatientAdmissionInstant")).dt.total_hours(fractional=True).alias("admit to first pressor hrs")
        # ).select("EncounterEpicCsn", billing_col, computed_col, "arrival to first pressor hrs", "admit to first pressor hrs")

        # return df_pressors_first_enc

    def build_sepsis_crosstab(
        self,
        df: pl.DataFrame,
        row_col: str = "Computed_Sepsis_Category",
        col_col: str = "Sepsis_Category",
        categories: list[str] | None = None,
        index_col_name: str = "max_sepsis_score",
        sum_label: str = "sum",
    ) -> pl.DataFrame:
        """
        Build a contingency table from two categorical columns.
    
        Returns a Polars DataFrame in the exact shape that
        ``plot_sepsis_heatmap_with_row_and_col_totals`` expects:
    
            index_col | cat-1 | cat-2 | ... | cat-N | sum
            --------- | ----- | ----- | ... | ----- | ---
            cat-1     |   5   |   2   | ... |   0   |  7
            ...       |  ...  |  ...  | ... |  ...  | ...
            sum       |  10   |   8   | ... |   3   | 50
    
        Parameters
        ----------
        df : pl.DataFrame
            Must contain *row_col* and *col_col*.
        row_col : str
            Column whose values become the rows (default: Computed).
        col_col : str
            Column whose values become the columns (default: Billing).
        categories : list[str] | None
            Ordered category labels.  Defaults to SEPSIS_CATEGORY_ORDER.
        index_col_name : str
            Name of the row-label column in the output (must match the
            ``index_col`` arg you pass to the heatmap plotter).
        sum_label : str
            Label used for the marginal row / column.
        """
        if categories is None:
            categories = SEPSIS_CATEGORY_ORDER
    
        # --- Step 1: count every (row_val, col_val) pair ---
        counts = df.group_by([row_col, col_col]).len()
        # Result has columns: [row_col, col_col, "len"]
    
        # --- Step 2: pivot to wide format ---
        pivot = counts.pivot(
            values="len",
            index=row_col,
            on=col_col,
        ).fill_null(0)
    
        # --- Step 3: guarantee every category exists as a column ---
        for cat in categories:
            if cat not in pivot.columns:
                pivot = pivot.with_columns(pl.lit(0).alias(cat))
    
        # --- Step 4: guarantee every category exists as a row ---
        existing_rows = set(pivot[row_col].to_list())
        missing = [c for c in categories if c not in existing_rows]
        if missing:
            filler = pl.DataFrame(
                [{row_col: c, **{cat: 0 for cat in categories}} for c in missing]
            )
            pivot = pl.concat([pivot, filler], how="vertical_relaxed")
    
        # --- Step 5: rename index column and enforce column order ---
        pivot = pivot.rename({row_col: index_col_name})
        pivot = pivot.select([index_col_name] + categories)
    
        # --- Step 6: sort rows by the canonical category order ---
        order_df = pl.DataFrame({
            index_col_name: categories,
            "_order": list(range(len(categories))),
        })
        pivot = (
            pivot
            .join(order_df, on=index_col_name, how="left")
            .sort("_order")
            .drop("_order")
        )
    
        # --- Step 7: add row totals (rightmost column) ---
        pivot = pivot.with_columns(
            pl.sum_horizontal(categories).alias(sum_label)
        )
    
        # --- Step 8: add column totals (bottom row) ---
        sum_row_data = {index_col_name: sum_label}
        for cat in categories:
            sum_row_data[cat] = pivot[cat].sum()
        sum_row_data[sum_label] = pivot[sum_label].sum()
    
        sum_row = pl.DataFrame([sum_row_data])
        crosstab = pl.concat([pivot, sum_row], how="vertical_relaxed")
    
        return crosstab

    def plot_distribution_comparison(
        self,
        df: pl.DataFrame,
        billing_col: str = "Sepsis_Category",
        computed_col: str = "Computed_Sepsis_Category",
        categories: list[str] | None = None,
        variable_col: str | None = None,
        variable_agg: str | None = None,
        figsize: tuple = (12, 6),
        title: str = "Billing vs Computed Sepsis Category",
        subtitle: str = "",
        filename: str = "sepsis_distribution.png",
        output_path: Path = Path("."),
        dpi: int = 200,
    ):
        """
        Side-by-side bar chart comparing billing and computed distributions.
    
        Each bar is annotated with its percentage *and* raw count so the
        audience gets both the relative shape and the absolute numbers.
    
        Parameters
        ----------
        df : pl.DataFrame
            Must contain *billing_col* and *computed_col*.
        subtitle : str
            Second line of the title (e.g. the time-window label).
        filename : str
            Output file name (saved inside *output_path*).
        output_path : Path
            Directory to save the figure into.
        dpi : int
            Resolution — 200 is good for slides projected at 1080p.
        """
        if categories is None:
            categories = SEPSIS_CATEGORY_ORDER
    
        total = len(df)
    
        if variable_col is None:
            # --- count per category for each source ---
            billing_counts = np.array([
                df.filter(pl.col(billing_col) == cat).height
                for cat in categories
            ])
            computed_counts = np.array([
                df.filter(pl.col(computed_col) == cat).height
                for cat in categories
            ])
        else:
            # --- count per category for each source ---
            billing_counts = np.array([
                df.filter(pl.col(billing_col) == cat)[variable_col].mean() if variable_agg == "mean" else df.filter(pl.col(billing_col) == cat)[variable_col].median()
                for cat in categories
            ])
            computed_counts = np.array([
                df.filter(pl.col(computed_col) == cat)[variable_col].mean() if variable_agg == "mean" else df.filter(pl.col(computed_col) == cat)[variable_col].median()
                for cat in categories
            ])
    
        if variable_col is None:
            # Count mode → convert to percentages
            billing_plot = billing_counts / total * 100
            computed_plot = computed_counts / total * 100
            ylabel = "Percentage (%)"
        else:
            # Variable mode → plot raw aggregated values directly
            billing_plot = billing_counts.astype(float)
            computed_plot = computed_counts.astype(float)
            agg_label = (variable_agg or "median").capitalize()
            ylabel = f"{agg_label} {variable_col}"

        # --- bar positions ---
        x = np.arange(len(categories))
        width = 0.35

        fig, ax = plt.subplots(figsize=figsize)

        bars_b = ax.bar(
            x - width / 2, billing_plot, width,
            label="Billing",
            color="#DD8452",
            edgecolor="white",
            linewidth=0.5,
        )
        bars_c = ax.bar(
            x + width / 2, computed_plot, width,
            label="Computed",
            color="#4C72B0",
            edgecolor="white",
            linewidth=0.5,
        )

        # --- annotate: scale the offset to the data range ---
        ymax = max(billing_plot.max(), computed_plot.max())
        offset = ymax * 0.02  # 2% of the tallest bar

        for bars, raw_values in [(bars_b, billing_counts), (bars_c, computed_counts)]:
            for bar, raw in zip(bars, raw_values):
                h = bar.get_height()

                if variable_col is None:
                    label = f"{h:.1f}%\n({int(raw):,d})"
                else:
                    label = f"{raw:.2f}"

                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    h + offset,
                    label,
                    ha="center",
                    va="bottom",
                    fontsize=9,
                    fontweight="bold",
                )

        # --- axes, labels, legend ---
        ax.set_xticks(x)
        ax.set_xticklabels(categories, fontsize=11)
        ax.set_ylabel(ylabel, fontsize=12)


        # billing_pct = billing_counts / total * 100
        # computed_pct = computed_counts / total * 100
    
        # # --- bar positions ---
        # x = np.arange(len(categories))
        # width = 0.35
    
        # fig, ax = plt.subplots(figsize=figsize)
    
        # bars_b = ax.bar(
        #     x - width / 2, billing_pct, width,
        #     label="Billing",
        #     color="#DD8452",       # muted orange
        #     edgecolor="white",
        #     linewidth=0.5,
        # )
        # bars_c = ax.bar(
        #     x + width / 2, computed_pct, width,
        #     label="Computed",
        #     color="#4C72B0",       # muted blue
        #     edgecolor="white",
        #     linewidth=0.5,
        # )
    
        # # --- annotate each bar: "pct%\n(count)" ---
        # for bars, counts in [(bars_b, billing_counts), (bars_c, computed_counts)]:
        #     for bar, count in zip(bars, counts):
        #         h = bar.get_height()
        #         ax.text(
        #             bar.get_x() + bar.get_width() / 2,
        #             h + 0.5,
        #             f"{h:.1f}%\n({count:.2f})",
        #             ha="center",
        #             va="bottom",
        #             fontsize=9,
        #             fontweight="bold",
        #         )
    
        # # --- axes, labels, legend ---
        # ax.set_xticks(x)
        # ax.set_xticklabels(categories, fontsize=11)
        # ax.set_ylabel("Percentage (%)", fontsize=12)
        # ax.set_xlabel("Sepsis Category", fontsize=12)
    
        full_title = f"{title}\n{subtitle}" if subtitle else title
        ax.set_title(full_title, fontsize=14, fontweight="bold", pad=15)
    
        ax.legend(fontsize=11, loc="best")
    
        # clean up spines for a presentation-friendly look
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
    
        # # headroom so annotations don't clip
        # ymax = max(billing_pct.max(), computed_pct.max())
        # ax.set_ylim(0, ymax * 1.35)
    
        fig.tight_layout()
        fig.savefig(output_path / filename, dpi=dpi, bbox_inches="tight")
        plt.close(fig)
    
        return fig

    def plot_indicator_comparison(
        self,
        df_computed: pl.DataFrame,
        df_billing: pl.DataFrame,
        computed_cat_col: str = "POA_Arrival+48hrs",
        billing_cat_col: str = "Sepsis_Category",
        value_col: str = "pct",
        count_col: str = "true",
        total_col: str = "total",
        categories: list[str] | None = None,
        figsize: tuple = (12, 6),
        title: str = "Billing vs Computed Sepsis Category Mortality Rates",
        subtitle: str = "",
        ylabel: str = "Morality Rate (%)",
        filename: str = "indicator_comparison.png",
        output_path: Path = Path.cwd(),
        dpi: int = 200,
    ):
        """
        Grouped bar chart from two pre-aggregated DataFrames.

        Unlike plot_distribution_comparison, this does NOT compute
        counts from raw data — it reads values directly from the
        aggregated tables you pass in.
        """
        if categories is None:
            categories = SEPSIS_CATEGORY_ORDER

        # ── Align both tables to the canonical category order ──
        # For each category, pull the row from each DataFrame.
        # If a category is missing, default to 0.
        billing_vals, computed_vals = [], []
        billing_labels, computed_labels = [], []

        for cat in categories:
            # Computed
            row_c = df_computed.filter(pl.col(computed_cat_col) == cat)
            if row_c.height > 0:
                computed_vals.append(row_c[value_col].item())
                computed_labels.append(
                    f"{row_c[count_col].item():,d}/{row_c[total_col].item():,d}"
                )
            else:
                computed_vals.append(0.0)
                computed_labels.append("0/0")

            # Billing
            row_b = df_billing.filter(pl.col(billing_cat_col) == cat)
            if row_b.height > 0:
                billing_vals.append(row_b[value_col].item())
                billing_labels.append(
                    f"{row_b[count_col].item():,d}/{row_b[total_col].item():,d}"
                )
            else:
                billing_vals.append(0.0)
                billing_labels.append("0/0")

        billing_vals = np.array(billing_vals)*100
        computed_vals = np.array(computed_vals)*100

        # ── Plot ──
        x = np.arange(len(categories))
        width = 0.35

        fig, ax = plt.subplots(figsize=figsize)

        bars_b = ax.bar(
            x - width / 2, billing_vals, width,
            label="Billing",
            color="#DD8452",
            edgecolor="white",
            linewidth=0.5,
        )
        bars_c = ax.bar(
            x + width / 2, computed_vals, width,
            label="Computed",
            color="#4C72B0",
            edgecolor="white",
            linewidth=0.5,
        )

        # ── Annotate: "pct%\n(count/total)" ──
        ymax = max(billing_vals.max(), computed_vals.max())
        offset = ymax * 0.02

        for bars, vals, labels in [
            (bars_b, billing_vals, billing_labels),
            (bars_c, computed_vals, computed_labels),
        ]:
            for bar, val, lbl in zip(bars, vals, labels):
                h = bar.get_height()
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    h + offset,
                    f"{val:.1f}%\n({lbl})",
                    ha="center",
                    va="bottom",
                    fontsize=9,
                    fontweight="bold",
                )

        ax.set_xticks(x)
        ax.set_xticklabels(categories, fontsize=11)
        ax.set_ylabel(ylabel, fontsize=12)
        ax.set_xlabel("Sepsis Category", fontsize=12)

        full_title = f"{title}\n{subtitle}" if subtitle else title
        ax.set_title(full_title, fontsize=14, fontweight="bold", pad=15)

        ax.legend(fontsize=11, loc="upper right")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.set_ylim(0, ymax * 1.35)

        fig.tight_layout()
        fig.savefig(output_path / filename, dpi=dpi, bbox_inches="tight")
        plt.close(fig)

        return fig

    def plot_sepsis_counts(self, df_sepsis_v2_max_first, category="Computed_Sepsis_Category", filename=Path("cohort_by_sepsis_counts.png"), output_path=Path(".")):
        # Extend display names so axes/titles match the house style
        COLUMN_DISPLAY_NAMES.update({
            "PatientAgeAtAdmission": "Age at Admission (Years)",
            "los_source":            "Length of Stay (Days)",
            "Death_Flag":            "In-Hospital Mortality (%)",
            "Computed_Sepsis_Category": "Algorithm Categorization",
            "POA_Arrival+48hrs": "Algorithm Categorization",
        })
        STRATA = ["NPOA-1","NPOA-2","NPOA-3","POA-1","POA-2","POA-3",]
        CATEGORY_COLORS = {
            "Computed_Sepsis": "#4C72B0",
            "Sepsis_Category": "#DD8452",
            "POA_Arrival+48hrs": "#4C72B0",
        }
        def get_display_name(col: str) -> str:
            return COLUMN_DISPLAY_NAMES.get(col, col) 
            # → INTRO SLIDE 2 figure A: encounters per stratum (the counts bar, your stratum palette)
        cnt_pd = (df_sepsis_v2_max_first.group_by(category).agg(pl.len().alias("n"))
                    .rename({category:"category"}).to_pandas())
        order_present = [s for s in STRATA if s in cnt_pd["category"].values]
        fig, ax = plt.subplots(figsize=(12,8))
        sns.barplot(data=cnt_pd, x="category", y="n", order=order_present, ax=ax, palette=None, color=CATEGORY_COLORS[category]) # Billing color: #DD842
                    # hue="category", palette=PALETTE_FULL, ax=ax)
        for c in ax.containers: ax.bar_label(c, fmt="%d", padding=2, fontsize=9)
        ax.set_title(f"Cohort by {get_display_name(category)}")
        ax.set_xlabel("Category"); ax.set_ylabel("Encounters"); sns.despine(ax=ax)
        fig.tight_layout(); fig.savefig(output_path / filename, dpi=200, bbox_inches="tight"); plt.close(fig)

    def analyze(self):
        # df_s1 = self.df_dict['df_sepsis1']
        # # s1_cols = [
        # #         [self.basic_analyusis_config.encounter_col,
        # #         "criterion",
        # #         "infect_dt",
        # #         "suspicion_infection_type"]+
        # #         [c for c in df_s1.columns if c.endswith("Flag")]+['sirs_score']
        # # ]
        # df_s2 = self.df_dict['df_sepsis2']
        # df_s3 = self.df_dict['df_sepsis3']

        # df_first = self._aggregatesepsis123byfirst(df_s1, df_s2, df_s3)
        # df_max = self._aggregatesepsis123bymax(df_s1, df_s2, df_s3)
        df_by_first = self._aggregate_sepsis(self.df_dict['df_sepsis1'], self.df_dict['df_sepsis2'], self.df_dict['df_sepsis3'], strategy="first")
        df_by_max = self._aggregate_sepsis(self.df_dict['df_sepsis1'], self.df_dict['df_sepsis2'], self.df_dict['df_sepsis3'], strategy="max")
        df_combined = df_by_first.join(
            df_by_max, on="EncounterEpicCsn", suffix="_at_max"
        )
        
        # df_joined = df_first.join(
        #     df_max,
        #     on = self.basic_analyusis_config.encounter_col,
        #     suffix="_max"
        # ).select(
        #     self.basic_analyusis_config.encounter_col,
        #     "max_sepsis_score",
        #     pl.col("first_sepsis_instant_max").alias("max_sepsis_instance"),
        #     pl.col("sepsis_score").alias("first_sepsis_score"),
        #     pl.col("min_instant").alias("first_sepsis_instance"),
        # )
        df_joined = df_combined.group_by(["EncounterEpicCsn", "first_sepsis_instant", "first_sepsis_instant_at_max"]).agg(
            pl.col("sepsis_score_at_max").max(),
            pl.col("sepsis_score").max()
        )
        df_joined = df_joined.join(
            self.df_dict['df_all'].group_by("EncounterEpicCsn").agg(
                pl.col("Arrival_Instant").min(),
                pl.col("InpatientAdmissionInstant").min(),
                pl.col("LengthOfStayInDays").first().cast(pl.Float64).alias("LOS_days"),
                pl.col("Sepsis_Category").first(),
                pl.col("Death_Flag").first(),
            ), on="EncounterEpicCsn"
        )
        meds_types = [
            'IV Antibiotics - Single',
            'IV Antibiotics - Last',
            'Medication Administration',
            'IV Antibiotics',
            'IV Antibiotics - First',
            'Perioperative Antibiotics'
        ]

        septic_shock_pressors = [
            "Norepinephrine",
            "Vasopressin",
            "Epinephrine",
            "Dopamine",
            "Phenylephrine",
        ]

        # df_meds_grb_cnt = self.df_dict['df_all'].filter(
        #     pl.col("Type").is_in(meds_types)
        # ).select("EncounterEpicCsn", "Event_DateTime", "Type",
        #          "Event_Grouper", "Event_Name", "Value").group_by("EncounterEpicCsn", "Event_Grouper").agg(
        #         pl.len().alias("meds_count")
        # )
        
        # df_meds_cnt = self.df_dict['df_all'].filter(
        #     pl.col("Type").is_in(meds_types)
        # ).select("EncounterEpicCsn", "Event_DateTime", "Type",
        #          "Event_Grouper", "Event_Name", "Value").group_by("EncounterEpicCsn").agg(
        #         pl.len().alias("meds_count")
        # )


        df_joined = self._assignPOAvNPOA(df_joined)
        df_joined = df_joined.with_columns(
            (pl.col("first_sepsis_instant")-pl.col("Arrival_Instant")).dt.total_hours(fractional=True).alias("Arrival To Sepsis Time")
        )

        # df_joined = df_joined.with_columns(
        #     pl.col("LOS_days").cast(pl.Float64)
        # )
        # df_joined = df_joined.join(
        #     df_meds_cnt,
        #     on="EncounterEpicCsn",
        #     how="left"
        # )
        
        self.plot_sepsis_counts(
            df_joined,
            category="POA_Arrival+48hrs",
            filename="cohortbyComputedFromAnalysisScript.png",
            output_path=self.output_path
        )
        self.plot_sepsis_counts(
            df_joined,
            category="Sepsis_Category",
            filename="cohortbyBillingFromAnalysisScript.png",
            output_path=self.output_path
        )

        df_joined = self._extract_severity_from_billing_calculated(df_joined, "Sepsis_Category", "billing_score")

        df_joined = df_joined.filter(~pl.col("Sepsis_Category").str.starts_with("U"))
        df_billing_mortality_rate = df_joined.group_by("Sepsis_Category").agg(
            (pl.col("Death_Flag")==1).sum().alias("true"),
            pl.len().alias("total")
        ).with_columns(
            (pl.col("true")/pl.col("total")).alias("pct")
        )
        df_computed_mortality_rate = df_joined.group_by("POA_Arrival+48hrs").agg(
            (pl.col("Death_Flag")==1).sum().alias("true"),
            pl.len().alias("total")
        ).with_columns(
            (pl.col("true")/pl.col("total")).alias("pct")
        )
        self.plot_indicator_comparison(
            df_billing=df_billing_mortality_rate,
            df_computed=df_computed_mortality_rate,
            computed_cat_col= "POA_Arrival+48hrs",
            billing_cat_col= "Sepsis_Category",
            value_col= "pct",
            count_col= "true",
            total_col= "total",
            filename="dist_mortality_rate_flag.png",
            output_path=self.output_path,
        )

        df_pressors = self._add_first_pressors(df_joined, self.df_dict['df_all'], septic_shock_pressors, billing_col="Sepsis_Category", computed_col="POA_Arrival+48hrs")
        df_pressors = df_pressors.unique(subset='EncounterEpicCsn').filter(
            ~pl.col("Sepsis_Category").str.starts_with("U")
        )
        df_pressors_before_48hrs_arrival = df_pressors.filter(
            pl.col("arrival to first pressor hrs")<48
        )

        df_pressors_before_24hrs_admission = df_pressors.filter(
            pl.col("admit to first pressor hrs")<24
        )

        self.plot_distribution_comparison(
        df_pressors_before_48hrs_arrival,
        computed_col="POA_Arrival+48hrs",
        subtitle="Pressors Within 48 hrs of Arrival",
        filename="dist_48hrs_arrival.png",
        output_path=self.output_path,
        )
        self.plot_distribution_comparison(
        df_pressors_before_24hrs_admission,
        computed_col="POA_Arrival+48hrs",
        subtitle="Pressors Within 24 hrs of Admission",
        filename="dist_24hrs_admission.png",
        output_path=self.output_path,
        )
        ct_48 = self.build_sepsis_crosstab(
        df_pressors_before_48hrs_arrival,
        row_col="POA_Arrival+48hrs",
        col_col="Sepsis_Category",
    )
        self.plot_sepsis_heatmap_with_row_and_col_totals(
            ct_48,
            normalize="col",
            title_suffix_label="Pressors Within 48 hrs of Arrival",
            filename="heatmap_48hrs_arrival.png",
        )

        ct_24 = self.build_sepsis_crosstab(
            df_pressors_before_24hrs_admission,
            row_col="POA_Arrival+48hrs",
            col_col="Sepsis_Category",
        )
        self.plot_sepsis_heatmap_with_row_and_col_totals(
        ct_24,
        normalize="col",
        title_suffix_label="Pressors Within 24 hrs of Admission",
        filename="heatmap_24hrs_admission.png",
        )
        x=0
        # df_pressors.write_csv("notebooks/df_pressors_analysis.csv")
        # self.plot_los_distribution(df_pressors.filter(
        #                                 (pl.col("arrival to first pressor hrs")<pl.col("arrival to first pressor hrs").quantile(0.99))&
        #                                 (pl.col("arrival to first pressor hrs")>pl.col("arrival to first pressor hrs").quantile(0.01))
        #                             ),
        #                             los_col="arrival to first pressor hrs", poa_col="POA_Arrival+48hrs",
        #                             billing_col="Sepsis_Category", target_category="NPOA-3",
        #                             figtitle_prefix="Arrival to First Pressor Hours",
        #                             xlabel="Arrival to First Pressor Hours",
        #                             filename="hours2firstpressor_NPOA3.png")

        # df_medsgrouper_joined = df_joined.join(
        #     df_meds_grb_cnt,
        #     on="EncounterEpicCsn",
        #     how='left'
        # )

        crosstab_arrival = self.crosstab(df_joined, "POA_Arrival+48hrs", "Sepsis_Category")
        crosstab_arrivalP = self._process_crosstab(crosstab_arrival, "POA_Arrival+48hrs")

        crosstab_inpatient = self.crosstab(df_joined, "POA_InpatientAdmissionInstant", "Sepsis_Category")
        crosstab_inpatP = self._process_crosstab(crosstab_inpatient, "POA_InpatientAdmissionInstant")

        self.plot_sepsis_heatmap(crosstab_arrivalP, normalize='col', index_col="POA_Arrival+48hrs",
                                 sum_row_label="total", sum_col_label="total", title_suffix_label="Arrival Time + 48 hours", filename="sepsis_heatmap_arrival.png")
        self.plot_sepsis_heatmap(crosstab_inpatP, normalize='col', index_col="POA_InpatientAdmissionInstant",
                                 sum_row_label="total", sum_col_label="total", title_suffix_label="Inpatient Admission Time", filename="sepsis_heatmap_inpatient.png")

        self.plot_sepsis_heatmap_with_row_and_col_totals(crosstab_arrivalP, normalize='col', index_col="POA_Arrival+48hrs",
                                 sum_row_label="total", sum_col_label="total", title_suffix_label="Arrival Time + 48 hours", filename="sepsis_heatmap_arrival_with_totals.png")
        self.plot_sepsis_heatmap_with_row_and_col_totals(crosstab_inpatP, normalize='col', index_col="POA_InpatientAdmissionInstant",
                                 sum_row_label="total", sum_col_label="total", title_suffix_label="Inpatient Admission Time", filename="sepsis_heatmap_inpatient_with_totals.png")

        # self.plot_category_comparison(df_joined.filter(~pl.col("Sepsis_Category").str.starts_with("U")), aggregate_poa=True, filename="sepsis_category_comparison_arrival_aggregate_poa.png")
        # self.plot_category_comparison(df_joined.filter(~pl.col("Sepsis_Category").str.starts_with("U")), col2="POA_InpatientAdmissionInstant", aggregate_poa=True, filename="sepsis_category_comparison_inpatient_aggregate_poa.png"))
        self.plot_category_comparison(df_joined.filter(~pl.col("Sepsis_Category").str.starts_with("U")),
                                      cols=["Sepsis_Category", "POA_InpatientAdmissionInstant", "POA_Arrival+48hrs"], aggregate_poa=True, filename="sepsis_category_comparison_arrival_inpatient_aggregate_poa.png")

        # self.plot_poa_barplot(df_joined.filter(~pl.col("Sepsis_Category").str.starts_with("U")))
        # self.plot_poa_barplot(df_joined.filter(~pl.col("Sepsis_Category").str.starts_with("U")),hue_col="POA_InpatientAdmissionInstant")
        self.plot_sepsis_time_boxplot(
            df_joined.filter(~pl.col("Sepsis_Category").str.starts_with("U")).filter(pl.col("Arrival To Sepsis Time")<pl.col("Arrival To Sepsis Time").quantile(0.99)).filter(pl.col("Arrival To Sepsis Time")>0),
              time_col="Arrival To Sepsis Time",
              group_cols=['Sepsis_Category', "POA_Arrival+48hrs"], filename="sepsis_time_boxplot_arrival.png"
        )
        # df_joined = df_joined.filter(pl.col("Arrival To Sepsis Time")<pl.col("Arrival To Sepsis Time").quantile(0.99))
        # df_joined_poa = df_joined.filter(
        #     pl.col("POA_Arrival+48hrs").str.starts_with('P')|pl.col("Sepsis_Category").str.starts_with('P')
        # )
        # self.plot_sepsis_time_boxplot(
        #     df_joined_poa.filter(~pl.col("Sepsis_Category").str.starts_with("U")), time_col="Arrival To Sepsis Time", group_cols=['Sepsis_Category', "POA_InpatientAdmissionInstant"]
        # )
        # df_joined_npoa = df_joined.filter(
        #     pl.col("POA_Arrival+48hrs").str.starts_with('N')|pl.col("Sepsis_Category").str.starts_with('N')
        # )
        # self.plot_sepsis_time_boxplot(
        #     df_joined_npoa.filter(~pl.col("Sepsis_Category").str.starts_with("U")), time_col="Arrival To Sepsis Time", group_cols=['Sepsis_Category', "POA_InpatientAdmissionInstant"]
        # )

        
        # df_joined = df_joined.filter(
        #     pl.col("LOS_days")<pl.col("LOS_days").quantile(0.99)
        # )
        # LOS Sepsis scores
        self.plot_los_distribution(df_joined.filter(pl.col("LOS_days")<pl.col("LOS_days").quantile(0.99)),
                                    los_col="LOS_days", poa_col="sepsis_score_at_max",
                                    billing_col="billing_score", target_category=3, filename="los_distribution_arrival_sepsis3.png")
        self.plot_los_distribution(df_joined.filter(pl.col("LOS_days")<pl.col("LOS_days").quantile(0.99)),
                                    los_col="LOS_days", poa_col="sepsis_score_at_max",
                                    billing_col="billing_score", target_category=2, filename="los_distribution_arrival_sepsis2.png")
        self.plot_los_distribution(df_joined.filter(pl.col("LOS_days")<pl.col("LOS_days").quantile(0.99)),
                                    los_col="LOS_days", poa_col="sepsis_score_at_max",
                                    billing_col="billing_score", target_category=1, filename="los_distribution_arrival_sepsis1.png")

        self.plot_distribution_comparison(
            df_joined.filter(pl.col("LOS_days")<pl.col("LOS_days").quantile(0.99)),
            variable_col="LOS_days",
            variable_agg="median",
            computed_col="POA_Arrival+48hrs",
            subtitle="LOS Distribution by Arrival Time + 48 hours",
            filename="dist_los_arrival.png",
            output_path=self.output_path,
        )

        # LOS NPOA vs POA
        self.plot_los_distribution(df_joined.filter(pl.col("LOS_days")<pl.col("LOS_days").quantile(0.99)),
                                    los_col="LOS_days", poa_col="POA_Arrival+48hrs",
                                    billing_col="Sepsis_Category", target_category="POA-3", filename="los_distribution_arrival_poa3.png")

        self.plot_los_distribution(df_joined.filter(pl.col("LOS_days")<pl.col("LOS_days").quantile(0.99)),
                                    los_col="LOS_days", poa_col="POA_Arrival+48hrs",
                                    billing_col="Sepsis_Category", target_category="NPOA-3", filename="los_distribution_arrival_npoa3.png")
        

        # NPOA-3 First pressors
        self.plot_los_distribution(df_joined.filter(pl.col("LOS_days")<pl.col("LOS_days").quantile(0.99)),
                                    los_col="LOS_days", poa_col="POA_Arrival+48hrs",
                                    billing_col="Sepsis_Category", target_category="POA-3", filename="los_distribution_arrival_poa3.png")

        self.plot_los_distribution(df_joined.filter(pl.col("LOS_days")<pl.col("LOS_days").quantile(0.99)),
                                    los_col="LOS_days", poa_col="POA_Arrival+48hrs",
                                    billing_col="Sepsis_Category", target_category="NPOA-3", filename="los_distribution_arrival_npoa3.png")


        # self.plot_medgroup_distribution_heatmap(
        #         df_meds_grb_cnt,
        #         df_joined,
        #         group_col= "Sepsis_Category",
        #         normalize = "row",            # "col" → each stratum sums to 1 (medication mix)
        #                                         # "row" → each medication sums to 1 (across-stratum spread)
        #         stratum_order= None,
        #         figsize = (10, 7),
        #         cmap= "Blues",
        #         title_suffix= "Billing Categorization",
        #         filename = "med_grouper_distribution_heatmap_rownorm_billing.png",
        #     )

        # self.plot_medgroup_distribution_heatmap(
        #         df_meds_grb_cnt,
        #         df_joined,
        #         group_col= "POA_Arrival+48hrs",
        #         normalize = "row",            # "col" → each stratum sums to 1 (medication mix)
        #                                         # "row" → each medication sums to 1 (across-stratum spread)
        #         stratum_order= None,
        #         figsize = (10, 7),
        #         cmap= "Blues",
        #         title_suffix= "Computed Categorization",
        #         filename = "med_grouper_distribution_heatmap_rownorm_computed.png",
        #     )


        # self.plot_medication_distribution(df_joined, med_col="meds_count",
        #                                    poa_col="POA_Arrival+48hrs",
        #                                    billing_col="Sepsis_Category",
        #                                    target_category="POA-3", filename="medication_distribution_poa3.png" )
        # self.plot_medication_distribution(df_joined, med_col="meds_count",
        #                                    poa_col="POA_Arrival+48hrs",
        #                                    billing_col="Sepsis_Category",
        #                                    target_category="NPOA-3", filename="medication_distribution_npoa3.png" )

        # self.plot_death_flag_distribution(df_joined, target_category="NPOA-3", filename="death_flag_distribution_npoa3.png")

        df_mortality_rate_billing = df_joined.filter(~pl.col("Sepsis_Category").str.starts_with("U")).group_by("Sepsis_Category").agg( (pl.col("Death_Flag")==1).sum().alias("deceased"), pl.len().alias("total")).with_columns(
                (pl.col("deceased")/pl.col("total")).alias("Mortality_Rate")
            )
        df_mortality_rate_computed = df_joined.filter(~pl.col("Sepsis_Category").str.starts_with("U")).group_by("POA_Arrival+48hrs").agg( (pl.col("Death_Flag")==1).sum().alias("deceased"), pl.len().alias("total")).with_columns(
                (pl.col("deceased")/pl.col("total")).alias("Mortality_Rate")
            )
        
        self.plot_death_flag_distribution_ratio(df_joined, target_category="POA-3", filename="death_flag_distribution_ratio_poa3.png")
        self.plot_death_flag_distribution_ratio(df_joined, target_category="POA-2", filename="death_flag_distribution_ratio_poa2.png")
        self.plot_death_flag_distribution_ratio(df_joined, target_category="NPOA-3", filename="death_flag_distribution_ratio_npoa3.png")
        
        # Death Flag for 3 groups
        self.plot_death_flag_distribution_ratio(df_joined, poa_col="sepsis_score_at_max", billing_col="billing_score", target_category=3, filename="death_flag_distribution_ratio_sepsis3.png")
        self.plot_death_flag_distribution_ratio(df_joined, poa_col="sepsis_score_at_max", billing_col="billing_score", target_category=2, filename="death_flag_distribution_ratio_sepsis2.png")
        self.plot_death_flag_distribution_ratio(df_joined, poa_col="sepsis_score_at_max", billing_col="billing_score", target_category=1, filename="death_flag_distribution_ratio_sepsis1.png")

        # Death flag different figures
                
        # df_mortality = df_joined.filter(~pl.col("Sepsis_Category").str.starts_with("U")).group_by("EncounterEpicCsn").agg(
        #     pl.col("Sepsis_Category").max().alias("Sepsis_Category"),
        #     pl.col("POA_Arrival+48hrs").max().alias("POA_Arrival+48hrs"),
        #     pl.col("Death_Flag").max().alias("Death_Flag"),
        # ).filter(pl.col("Death_Flag")==1)
        

        x = 0
        