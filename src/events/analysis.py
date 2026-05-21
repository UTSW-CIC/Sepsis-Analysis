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

PALETTE_SOURCE = {
    "Sepsis_Category":    "#66b2ff",  # medium blue
    "POA_Arrival+48hrs":  "#003d99",  # dark blue
    "POA_InpatientAdmissionInstant": "#001f66",

}

logger = get_logger(__name__)

class Analysis:
    def __init__(self, data_dir: Path, basic_analysis_config: BasicAnalysisConfig) -> None:
        self.data_dir = data_dir
        self.basic_analyusis_config = basic_analysis_config
        self._load_dataframes()

    def _load_dataframes(self):
        self.df_dict = load_output_folder(self.data_dir, logger)

    def _get_dfenc(self):
        df_all = self.df_dict['df_all']
        return df_all.select(self.basic_analyusis_config.encounter_level_info_cols).group_by(self.basic_analyusis_config.encounter_col).last()

    def _assignPOAvNPOA(self, df_joined):
        df_joined =  df_joined.with_columns(
            pl.when(pl.col("first_sepsis_instance") <= pl.col("Arrival_Instant")+pl.duration(hours=48)).then(pl.lit("POA")).otherwise(pl.lit("NPOA")).alias("POA_Arrival+48hrs_class"),
            pl.when(pl.col("first_sepsis_instance") <= pl.col("InpatientAdmissionInstant")).then(pl.lit("POA")).otherwise(pl.lit("NPOA")).alias("POA_InpatientAdmissionInstant_class"),
        )
        return df_joined.with_columns(
            (pl.col("POA_Arrival+48hrs_class")+'-'+pl.col("max_sepsis_score").cast(pl.String)).alias("POA_Arrival+48hrs"),
            (pl.col("POA_InpatientAdmissionInstant_class")+'-'+pl.col("max_sepsis_score").cast(pl.String)).alias("POA_InpatientAdmissionInstant")
        )
        

    def _aggregatesepsis123bymax(self, df_s1, df_s2, df_s3):
        ds1 = df_s1.group_by("EncounterEpicCsn").agg(pl.col("earliest_sepsis1_instance").min().alias("first_sepsis_instant")).with_columns(
            pl.lit(1).alias("sepsis_score"),
        ).select("EncounterEpicCsn", "first_sepsis_instant", "sepsis_score")

        ds2 = df_s2.group_by("EncounterEpicCsn").agg(pl.col("earliest_sepsis2_instance").min().alias("first_sepsis_instant")).with_columns(
            pl.lit(2).alias("sepsis_score"),
        ).select("EncounterEpicCsn", "first_sepsis_instant", "sepsis_score")

        ds3 = df_s3.group_by("EncounterEpicCsn").agg(pl.col("earliest_sepsis3_instance").min().alias("first_sepsis_instant")).with_columns(
            pl.lit(3).alias("sepsis_score"),
        ).select("EncounterEpicCsn", "first_sepsis_instant", "sepsis_score")

        df_sall = pl.concat([ds1, ds2, ds3], how='vertical')
        df_max =  df_sall.group_by("EncounterEpicCsn").agg(pl.col("sepsis_score").max().alias('max_sepsis_score'))
        return df_max.join(df_sall, on='EncounterEpicCsn').filter(pl.col("sepsis_score")==pl.col("max_sepsis_score")).sort(by='EncounterEpicCsn')

    def _aggregatesepsis123byfirst(self, df_s1, df_s2, df_s3):
        ds1 = df_s1.group_by("EncounterEpicCsn").agg(pl.col("earliest_sepsis1_instance").min().alias("first_sepsis_instant")).with_columns(
            pl.lit(1).alias("sepsis_score"),
        ).select("EncounterEpicCsn", "first_sepsis_instant", "sepsis_score")

        ds2 = df_s2.group_by("EncounterEpicCsn").agg(pl.col("earliest_sepsis2_instance").min().alias("first_sepsis_instant")).with_columns(
            pl.lit(2).alias("sepsis_score"),
        ).select("EncounterEpicCsn", "first_sepsis_instant", "sepsis_score")

        ds3 = df_s3.group_by("EncounterEpicCsn").agg(pl.col("earliest_sepsis3_instance").min().alias("first_sepsis_instant")).with_columns(
            pl.lit(3).alias("sepsis_score"),
        ).select("EncounterEpicCsn", "first_sepsis_instant", "sepsis_score")

        df_sall = pl.concat([ds1, ds2, ds3], how='vertical')
        df_first = df_sall.group_by("EncounterEpicCsn").agg(pl.col("first_sepsis_instant").min().alias("min_instant"))
        return df_first.join(df_sall, on='EncounterEpicCsn').filter(pl.col("min_instant")==pl.col("first_sepsis_instant")).sort(by='EncounterEpicCsn')

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
        title_suffix_label: str="Arrival Time + 48 Hours"
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

        # sns.heatmap(
        #     norm_matrix,
        #     ax=ax,
        #     annot=annot,
        #     fmt="",                  # empty because annot is already strings
        #     cmap="Blues",
        #     vmin=0, vmax=1,
        #     linewidths=0.5,
        #     linecolor="white",
        #     cbar_kws={"label": f"Proportion ({'row' if normalize == 'row' else 'column'} normalized)"},
        #     xticklabels=cat_cols,
        #     yticklabels=row_labels,
        # )
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
        # sns.heatmap(
        #     1 - norm_matrix,           # <-- only change to the data
        #     ax=ax,
        #     annot=annot,               # keep original counts/pct (they still reflect real values)
        #     fmt="",
        #     cmap="Blues",               # high = bad (mismatch)
        #     vmin=0, vmax=1,
        #     linewidths=0.5,
        #     linecolor="white",
        #     cbar_kws={"label": f"Mismatch proportion ({'row' if normalize == 'row' else 'column'} normalized)"},
        #     xticklabels=cat_cols,
        #     yticklabels=row_labels,
        # )

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

        plt.tight_layout()
        plt.show()


    def plot_death_flag_distribution(
        self,
        df: pl.DataFrame,
        flag_col: str = "Death_Flag",
        poa_col: str = "POA_Arrival+48hrs",
        billing_col: str = "Sepsis_Category",
        target_category: str = "POA-3",
        figsize: tuple = (12, 6),
    ):
        # ?? Filter the three groups ???????????????????????????????????????????
        group1 = df.filter(
            (pl.col(poa_col) == target_category) & (pl.col(billing_col) != target_category)
        ).select(flag_col).to_pandas()
        group1["source"] = f"Computed={target_category}\nBilling!={target_category}"

        group2 = df.filter(
            (pl.col(billing_col) == target_category) & (pl.col(poa_col) != target_category)
        ).select(flag_col).to_pandas()
        group2["source"] = f"Billing={target_category}\nComputed!={target_category}"

        group3 = df.filter(
            (pl.col(poa_col) == target_category) & (pl.col(billing_col) == target_category)
        ).select(flag_col).to_pandas()
        group3["source"] = f"Both={target_category}"

        melted = pd.concat([group1, group2, group3], ignore_index=True)

        # ?? Build source_order and palette from actual labels ?????????????????
        source_order = melted["source"].unique().tolist()
        colors = ["#003d99", "#ff7f0e", "#d62728"]
        palette = {source: color for source, color in zip(source_order, colors)}

        # ?? Count Death_Flag values per group ?????????????????????????????????
        counts = (
            melted.groupby(["source", flag_col])
            .size()
            .reset_index(name="count")
        )

        # ?? Plot ??????????????????????????????????????????????????????????????
        fig, ax = plt.subplots(figsize=figsize)

        sns.barplot(
            data=counts,
            x="source",
            y="count",
            hue=flag_col,
            order=source_order,
            ax=ax,
        )

        ax.set_title(f"Death Flag Distribution: {target_category} Agreement vs Disagreement")
        ax.set_xlabel("")
        ax.set_ylabel("Count")
        ax.legend(title=flag_col)

        plt.tight_layout()
        plt.show()


    def plot_poa_barplot(
        self,
        df: pl.DataFrame,
        x_col: str = "Billing Categorization",
        hue_col: str = "POA_Arrival+48hrs",
        aggregate_poa: bool = False,
        figsize: tuple = (10, 6),
    ):
        pdf = df.select([x_col, hue_col]).to_pandas()

        if aggregate_poa:
            pdf[hue_col] = pdf[hue_col].str.replace(r"-\d+", "", regex=True)
            hue_order = ["NPOA", "POA"]
            palette = PALETTE_AGG
        else:
            hue_order = ["NPOA-1", "NPOA-2", "NPOA-3", "POA-1", "POA-2", "POA-3"]
            palette = PALETTE_FULL

        fig, ax = plt.subplots(figsize=figsize)
        x_order = sorted(pdf[x_col].unique(), key=lambda x: (0 if "NPOA" in x else 1, x))

        sns.countplot(
            data=pdf,
            x=x_col,
            hue=hue_col,
            order=x_order,
            hue_order=hue_order,
            palette=palette,
            ax=ax,
        )

        # sns.countplot(
        #     data=pdf,
        #     x=x_col,
        #     hue=hue_col,
        #     hue_order=hue_order,
        #     ax=ax,
        # )

        ax.set_title(f"Encounter Counts by Billing Categorization and {'Arrival + 48 hours' if 'arrival' in hue_col.lower() else 'Inpatient Admission'}")
        ax.set_xlabel("Billing Categorization")
        ax.set_ylabel("Count")
        ax.legend(title=hue_col)

        plt.tight_layout()
        plt.show()

    def plot_category_comparison1(
        self,
        df: pl.DataFrame,
        col1: str = "Sepsis_Category",
        col2: str = "POA_Arrival+48hrs",
        aggregate_poa: bool = False,
        figsize: tuple = (10, 6),
    ):
        pdf = df.select([col1, col2]).to_pandas()

        if aggregate_poa:
            pdf[col1] = pdf[col1].str.replace(r"-\d+", "", regex=True)
            pdf[col2] = pdf[col2].str.replace(r"-\d+", "", regex=True)
            palette = PALETTE_AGG
        else:
            palette = PALETTE_FULL

        # ?? Count frequencies in each column independently ????????????????????
        counts1 = pdf[col1].value_counts().rename("count").reset_index()
        counts1.columns = ["category", "count"]
        # counts1["source"] = col1
        counts1["source"] = "Billing Categorization"
        PALETTE_SOURCE["Billing Categorization"] = PALETTE_SOURCE['Sepsis_Category']

        counts2 = pdf[col2].value_counts().rename("count").reset_index()
        counts2.columns = ["category", "count"]
        # counts2["source"] = col2
        counts2["source"] = 'Arrival + 48 hours' if 'arrival' in col2.lower() else 'Inpatient Admission'
        PALETTE_SOURCE['Arrival + 48 hours' if 'arrival' in col2.lower() else 'Inpatient Admission'] = PALETTE_SOURCE["POA_Arrival+48hrs"]

        merged = pd.concat([counts1, counts2], ignore_index=True)

        # ?? Sort order ????????????????????????????????????????????????????????
        cat_order = sorted(merged["category"].unique(), key=lambda x: (0 if "NPOA" in x else 1, x))

        # ?? Plot ??????????????????????????????????????????????????????????????
        fig, ax = plt.subplots(figsize=figsize)

        sns.barplot(
            data=merged,
            x="category",
            y="count",
            hue="source",
            order=cat_order,
            palette=PALETTE_SOURCE,
            ax=ax,
        )

        ax.set_title(f"Category Counts: Billing Categorizatoin vs {'Arrival + 48 hours' if 'arrival' in col2.lower() else 'Inpatient Admission'}")
        ax.set_xlabel("Category")
        ax.set_ylabel("Count")
        ax.legend(title="Source")

        plt.tight_layout()
        plt.show()


    def plot_sepsis_time_boxplot(
        self,
    df: pl.DataFrame,
    time_col: str = "Arrival To Sepsis Time",
    group_cols: list = ["Sepsis_Category", "POA_Arrival+48hrs"],
    aggregate_poa: bool = False,
    figsize: tuple = (12, 6),
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

        plt.tight_layout()
        plt.show()


    def plot_los_distribution(
        self,
        df: pl.DataFrame,
        los_col: str = "LOS_days",
        poa_col: str = "POA_Arrival+48hrs",
        billing_col: str = "Sepsis_Category",
        target_category: str = "POA-3",
        figsize: tuple = (12, 6),
    ):
        # ?? Filter the three groups ???????????????????????????????????????????
        group1 = df.filter(
            (pl.col(poa_col) == target_category) & (pl.col(billing_col) != target_category)
        ).select(los_col).to_pandas()
        group1["source"] = f"Computed={target_category}\nBilling!={target_category}"

        group2 = df.filter(
            (pl.col(billing_col) == target_category) & (pl.col(poa_col) != target_category)
        ).select(los_col).to_pandas()
        group2["source"] = f"Billing={target_category}\nComputed!={target_category}"

        group3 = df.filter(
            (pl.col(poa_col) == target_category) & (pl.col(billing_col) == target_category)
        ).select(los_col).to_pandas()
        group3["source"] = f"Both={target_category}"

        melted = pd.concat([group1, group2, group3], ignore_index=True)
        melted[los_col] = melted[los_col].astype(float)

        # ?? Order: match first, then discordant groups ????????????????????????
        source_order = melted["source"].unique().tolist()
        colors = ["#003d99", "#66b2ff", "#cce5ff"]
        palette = {source: color for source, color in zip(source_order, colors)}
        # ?? Palette: dark blue for match, medium and light for mismatches ?????
        colors = ["#003d99", "#66b2ff", "#cce5ff"]
        unique_sources = [s for s in source_order if s in melted["source"].unique().tolist()]
        palette = {source: color for source, color in zip(unique_sources, colors)}
        # palette = {
        #     f"Both={target_category}":                          "#003d99",
        #     f"Algorithm={target_category}\nBilling={target_category}": "#66b2ff",
        #     f"Billing={target_category}\nAlgorithm={target_category}": "#cce5ff",
        # }

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

        ax_box.set_title(f"LOS Distribution: {target_category} Agreement vs Disagreement")
        ax_box.set_ylabel("")
        ax_box.set_xlabel("Length of Stay (Days)")

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


        plt.tight_layout()
        plt.show()


    def plot_death_flag_distribution_ratio(
        self,
        df: pl.DataFrame,
        flag_col: str = "Death_Flag",
        poa_col: str = "POA_Arrival+48hrs",
        billing_col: str = "Sepsis_Category",
        target_category: str = "POA-3",
        figsize: tuple = (12, 6),
    ):
        # ?? Filter the three groups ???????????????????????????????????????????
        group1 = df.filter(
            (pl.col(poa_col) == target_category) & (pl.col(billing_col) != target_category)
        ).select(flag_col).to_pandas()
        group1["source"] = f"Computed={target_category}\nBilling!={target_category}"

        group2 = df.filter(
            (pl.col(billing_col) == target_category) & (pl.col(poa_col) != target_category)
        ).select(flag_col).to_pandas()
        group2["source"] = f"Billing={target_category}\nComputed!={target_category}"

        group3 = df.filter(
            (pl.col(poa_col) == target_category) & (pl.col(billing_col) == target_category)
        ).select(flag_col).to_pandas()
        group3["source"] = f"Both={target_category}"

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

        plt.tight_layout()
        plt.show()


    def plot_category_comparison(
        self,
        df: pl.DataFrame,
        cols: list = ["Sepsis_Category", "POA_Arrival+48hrs"],
        aggregate_poa: bool = False,
        figsize: tuple = (10, 6),
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

        plt.tight_layout()
        plt.show()


    def analyze(self):
        df_s1 = self.df_dict['df_sepsis1']
        # s1_cols = [
        #         [self.basic_analyusis_config.encounter_col,
        #         "criterion",
        #         "infect_dt",
        #         "suspicion_infection_type"]+
        #         [c for c in df_s1.columns if c.endswith("Flag")]+['sirs_score']
        # ]
        df_s2 = self.df_dict['df_sepsis2']
        df_s3 = self.df_dict['df_sepsis3']

        df_first = self._aggregatesepsis123byfirst(df_s1, df_s2, df_s3)
        df_max = self._aggregatesepsis123bymax(df_s1, df_s2, df_s3)
        df_joined = df_first.join(
            df_max,
            on = self.basic_analyusis_config.encounter_col,
            suffix="_max"
        ).select(
            self.basic_analyusis_config.encounter_col,
            "max_sepsis_score",
            pl.col("first_sepsis_instant_max").alias("max_sepsis_instance"),
            pl.col("sepsis_score").alias("first_sepsis_score"),
            pl.col("min_instant").alias("first_sepsis_instance"),
        )
        df_joined = df_joined.group_by(["EncounterEpicCsn", "first_sepsis_instance", "max_sepsis_instance"]).agg(
            pl.col("max_sepsis_score").max(),
            pl.col("first_sepsis_score").max()
        )
        df_joined = df_joined.join(
            df_s1.group_by("EncounterEpicCsn").agg(
                pl.col("Arrival_Instant").min(),
                pl.col("InpatientAdmissionInstant").min(),
                pl.col("LengthOfStayInDays").first().alias("LOS_days"),
                pl.col("Sepsis_Category").first(),
                pl.col("Death_Flag").first(),
            ), on="EncounterEpicCsn"
        )
        df_joined = self._assignPOAvNPOA(df_joined)
        df_joined = df_joined.with_columns(
            (pl.col("first_sepsis_instance")-pl.col("Arrival_Instant")).dt.total_hours(fractional=True).alias("Arrival To Sepsis Time")
        )

        df_joined = df_joined.with_columns(
            pl.col("LOS_days").cast(pl.Float64)
        )

        crosstab_arrival = self.crosstab(df_joined, "POA_Arrival+48hrs", "Sepsis_Category")
        crosstab_arrivalP = self._process_crosstab(crosstab_arrival, "POA_Arrival+48hrs")

        crosstab_inpatient = self.crosstab(df_joined, "POA_InpatientAdmissionInstant", "Sepsis_Category")
        crosstab_inpatP = self._process_crosstab(crosstab_inpatient, "POA_InpatientAdmissionInstant")

        # self.plot_sepsis_heatmap(crosstab_arrivalP, normalize='col', index_col="POA_Arrival+48hrs",
        #                          sum_row_label="total", sum_col_label="total", title_suffix_label="Arrival Time + 48 hours")
        # self.plot_sepsis_heatmap(crosstab_inpatP, normalize='col', index_col="POA_InpatientAdmissionInstant",
        #                          sum_row_label="total", sum_col_label="total", title_suffix_label="Inpatient Admission Time")
        # self.plot_category_comparison(df_joined.filter(~pl.col("Sepsis_Category").str.starts_with("U")), aggregate_poa=True)
        # self.plot_category_comparison(df_joined.filter(~pl.col("Sepsis_Category").str.starts_with("U")), col2="POA_InpatientAdmissionInstant", aggregate_poa=True)
        # self.plot_category_comparison(df_joined.filter(~pl.col("Sepsis_Category").str.starts_with("U")),
        #                               cols=["Sepsis_Category", "POA_InpatientAdmissionInstant", "POA_Arrival+48hrs"], aggregate_poa=True)

        # self.plot_poa_barplot(df_joined.filter(~pl.col("Sepsis_Category").str.starts_with("U")))
        # self.plot_poa_barplot(df_joined.filter(~pl.col("Sepsis_Category").str.starts_with("U")),hue_col="POA_InpatientAdmissionInstant")
        # self.plot_sepsis_time_boxplot(
        #     df_joined.filter(~pl.col("Sepsis_Category").str.starts_with("U")), time_col="Arrival To Sepsis Time", group_cols=['Sepsis_Category', "POA_Arrival+48hrs"]
        # )
        df_joined = df_joined.filter(pl.col("Arrival To Sepsis Time")<pl.col("Arrival To Sepsis Time").quantile(0.99))
        df_joined_poa = df_joined.filter(
            pl.col("POA_Arrival+48hrs").str.starts_with('P')|pl.col("Sepsis_Category").str.starts_with('P')
        )
        self.plot_sepsis_time_boxplot(
            df_joined_poa.filter(~pl.col("Sepsis_Category").str.starts_with("U")), time_col="Arrival To Sepsis Time", group_cols=['Sepsis_Category', "POA_InpatientAdmissionInstant"]
        )
        df_joined_npoa = df_joined.filter(
            pl.col("POA_Arrival+48hrs").str.starts_with('N')|pl.col("Sepsis_Category").str.starts_with('N')
        )
        self.plot_sepsis_time_boxplot(
            df_joined_npoa.filter(~pl.col("Sepsis_Category").str.starts_with("U")), time_col="Arrival To Sepsis Time", group_cols=['Sepsis_Category', "POA_InpatientAdmissionInstant"]
        )

        
        # df_joined = df_joined.filter(
        #     pl.col("LOS_days")<pl.col("LOS_days").quantile(0.99)
        # )
        # self.plot_los_distribution(df_joined, los_col="LOS_days", poa_col="POA_Arrival+48hrs", billing_col="Sepsis_Category", target_category="POA-3")
        # self.plot_death_flag_distribution(df_joined, target_category="NPOA-3")

        # self.plot_death_flag_distribution_ratio(df_joined, target_category="POA-2")
        # self.plot_death_flag_distribution_ratio(df_joined, target_category="NPOA-3")

        x = 0
        