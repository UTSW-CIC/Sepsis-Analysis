import polars as pl
import numpy as np
from pathlib import Path
import os
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from scipy.stats import chi2_contingency, fisher_exact
from typing import List

from src.configs.basic import BasicAnalysisConfig 
from src.utils.logger import get_logger
from src.utils.utils import load_output_folder 


logger = get_logger(__name__)

class BasicAnalysis:
    def __init__(self, data_dir: Path, basic_analysis_config: BasicAnalysisConfig) -> None:
        self.data_dir = data_dir
        self.basic_analyusis_config = basic_analysis_config
        self._load_dataframes()

    def _load_dataframes(self):
        self.df_dict = load_output_folder(self.data_dir, logger)

    def _get_dfenc(self):
        df_all = self.df_dict['df_all']
        return df_all.select(self.basic_analyusis_config.encounter_level_info_cols).group_by(self.basic_analyusis_config.encounter_col).last()



    def _detect_POA1(self):
        df_enc = self._get_dfenc()
        df_sepsis1 = self.df_dict['df_sepsis1']

        enc_id =self.basic_analyusis_config.encounter_col,
        earliest_sepsis1_instance = self.basic_analyusis_config.severitysepsisconfig.earliest_sepsis1_instance
        # arrival_instant = self.basic_analyusis_config.poa_config.period_constraints['Arrival_Instant']
        # admission_instant = self.basic_analyusis_config.poa_config.period_constraints['InpatientAdmissionInstant']

        # Get first sepsis instance
        df_sepsis1_enc = df_sepsis1.group_by(
            enc_id
        ).agg(
            pl.col(earliest_sepsis1_instance).min()
        )


        df_joined = df_enc.join(
            df_sepsis1_enc,
            on = self.basic_analyusis_config.encounter_col
        )

        df_joined = df_joined.with_columns(
            [
                pl.when(
                pl.col(self.basic_analyusis_config.severitysepsisconfig.earliest_sepsis1_instance) <= (pl.col(time_col)+pl.duration(hours=period))
                ).then(pl.lit("POA-1")).otherwise(pl.lit("NPOA-1")).alias(f"POA_Criteria_{time_col}")

                for time_col, period in self.basic_analyusis_config.poa_config.period_constraints.items()
            ]
        )
        return df_joined
        

    def _detect_POA2(self):
        df_enc = self._get_dfenc()
        df_sepsis2 = self.df_dict['df_sepsis2']

        enc_id =self.basic_analyusis_config.encounter_col,
        earliest_sepsis2_instance = self.basic_analyusis_config.severitysepsisconfig.earliest_sepsis2_instance

        # Get first sepsis instance
        df_sepsis2_enc = df_sepsis2.group_by(
            enc_id
        ).agg(
            pl.col(earliest_sepsis2_instance).min()
        )

        df_joined = df_enc.join(
            df_sepsis2_enc,
            on = self.basic_analyusis_config.encounter_col
        )
        df_joined = df_joined.with_columns(
            [
                pl.when(
                    (pl.col(self.basic_analyusis_config.severitysepsisconfig.earliest_sepsis2_instance) <= (pl.col(time_col)+pl.duration(hours=period)))
                ).then(pl.lit("POA-2")).otherwise(pl.lit("NPOA-2")).alias(f"POA_Criteria_{time_col}")

                for time_col, period in self.basic_analyusis_config.poa_config.period_constraints.items()
            ]
        )
        return df_joined

    def _detect_POA3(self):
        df_enc = self._get_dfenc()
        df_sepsis3 = self.df_dict['df_sepsis3']

        enc_id =self.basic_analyusis_config.encounter_col,
        earliest_sepsis3_instance = self.basic_analyusis_config.severitysepsisconfig.earliest_sepsis3_instance

        # Get first sepsis instance
        df_sepsis3_enc = df_sepsis3.group_by(
            enc_id
        ).agg(
            pl.col(earliest_sepsis3_instance).min()
        )


        df_joined = df_enc.join(
            df_sepsis3_enc,
            on = self.basic_analyusis_config.encounter_col
        )
        df_joined = df_joined.with_columns(
            [
                pl.when(
                    (pl.col(self.basic_analyusis_config.severitysepsisconfig.earliest_sepsis3_instance) <= (pl.col(time_col)+pl.duration(hours=period)))
                ).then(pl.lit("POA-3")).otherwise(pl.lit("NPOA-3")).alias(f"POA_Criteria_{time_col}")

                for time_col, period in self.basic_analyusis_config.poa_config.period_constraints.items()
            ]
        )
        return df_joined

    def _convert_sepsis_to_score(self, df_sepsis: pl.DataFrame, colname: str, output_col_name: str):
        return df_sepsis.with_columns(
            pl.col(colname).str.split('-').list.last().cast(pl.Int64).alias(output_col_name)
        )

    def _billing_vs_calculated(self, df_sepsis, col_name):
        counts = df_sepsis.group_by([col_name, self.basic_analyusis_config.billing_sepsis_col]).len()
        ct = counts.pivot(
            on=self.basic_analyusis_config.billing_sepsis_col,
            index=col_name,
            values="len"
            ).fill_null(0)
        billing_cols = self.basic_analyusis_config.billing_values_order  # e.g., ["POA", "NPOA", "UPOA"]
        # Add missing billing columns with 0
        for bcol in billing_cols:
            if bcol not in ct.columns:
                ct = ct.with_columns(pl.lit(0).alias(bcol))
        ct_raw = ct.select([col_name] + billing_cols)

        # --- Compute row totals ---
        # Add a "Total" column = sum of each row across billing columns
        ct_raw = ct_raw.with_columns(
            pl.sum_horizontal(billing_cols).alias("Total")
        )

        # --- Compute row-wise percentages ---
        # For each billing column, compute count / row_total * 100
        # Then format as "count (pct%)"
        display_exprs = [pl.col(col_name)]  # keep the row label

        for bcol in billing_cols:
            display_exprs.append(
                (
                    pl.col(bcol).cast(pl.Utf8)
                    + pl.lit(" (")
                    + (pl.col(bcol) / pl.col("Total") * 100)
                        .round(1)
                        .cast(pl.Utf8)
                    + pl.lit("%)")
                ).alias(bcol)
            )

        # Also format the Total column as just the count
        display_exprs.append(pl.col("Total").cast(pl.Utf8))

        ct_display = ct_raw.select(display_exprs)

        # --- Add column totals row ---
        # Sum each billing column and Total across all rows
        col_totals = {col_name: "Total"}
        for bcol in billing_cols:
            col_sum = ct_raw[bcol].sum()
            total_sum = ct_raw["Total"].sum()
            pct = col_sum / total_sum * 100
            col_totals[bcol] = f"{col_sum} ({pct:.1f}%)"
        col_totals["Total"] = str(ct_raw["Total"].sum())

        totals_row = pl.DataFrame([col_totals])
        ct_display = pl.concat([ct_display, totals_row])
        return ct_display.sort(by=col_name), ct_raw.sort(by=col_name)


    def _billing_vs_calculated_old(self, df_sepsis1, df_sepsis2, df_sepsis3):
        results = {}  # store all tables keyed by (sepsis_level, criterion)

        sepsis_labels = ["Sepsis", "Severe Sepsis", "Septic Shock"]
        for label, df in zip(sepsis_labels, [df_sepsis1, df_sepsis2, df_sepsis3]):
            for col in self.basic_analyusis_config.poa_config.time_columns:
                col_name = f'POA_Criteria_{col}' 
                counts = df.group_by([col_name, self.basic_analyusis_config.billing_sepsis_col]).len()
                ct = counts.pivot(
                    on=self.basic_analyusis_config.billing_sepsis_col,
                    index=col_name,
                    values="len"
                    ).fill_null(0)
                billing_cols = self.basic_analyusis_config.billing_values_order  # e.g., ["POA", "NPOA", "UPOA"]
                # Add missing billing columns with 0
                for bcol in billing_cols:
                    if bcol not in ct.columns:
                        ct = ct.with_columns(pl.lit(0).alias(bcol))
                ct = ct.select([col_name] + billing_cols)

                # --- Compute row totals ---
                # Add a "Total" column = sum of each row across billing columns
                ct = ct.with_columns(
                    pl.sum_horizontal(billing_cols).alias("Total")
                )

                # --- Compute row-wise percentages ---
                # For each billing column, compute count / row_total * 100
                # Then format as "count (pct%)"
                display_exprs = [pl.col(col_name)]  # keep the row label

                for bcol in billing_cols:
                    display_exprs.append(
                        (
                            pl.col(bcol).cast(pl.Utf8)
                            + pl.lit(" (")
                            + (pl.col(bcol) / pl.col("Total") * 100)
                                .round(1)
                                .cast(pl.Utf8)
                            + pl.lit("%)")
                        ).alias(bcol)
                    )

                # Also format the Total column as just the count
                display_exprs.append(pl.col("Total").cast(pl.Utf8))

                ct_display = ct.select(display_exprs)

                # --- Add column totals row ---
                # Sum each billing column and Total across all rows
                col_totals = {col_name: "Total"}
                for bcol in billing_cols:
                    col_sum = ct[bcol].sum()
                    total_sum = ct["Total"].sum()
                    pct = col_sum / total_sum * 100
                    col_totals[bcol] = f"{col_sum} ({pct:.1f}%)"
                col_totals["Total"] = str(ct["Total"].sum())

                totals_row = pl.DataFrame([col_totals])
                ct_display = pl.concat([ct_display, totals_row])

                # --- Store with meaningful key ---
                results[(label, col)] = ct_display

        return results

    def _analyze_billing_vs_calculated(self, df_poa_1, df_poa_2, df_poa_3):           
        results_raw = {}
        results_display = {}
        for col in self.basic_analyusis_config.poa_config.time_columns:
            df_poa1 = self._convert_sepsis_to_score(df_poa_1, f"POA_Criteria_{col}", "severity_score")
            df_poa2 = self._convert_sepsis_to_score(df_poa_2, f"POA_Criteria_{col}", "severity_score")
            df_poa3 = self._convert_sepsis_to_score(df_poa_3, f"POA_Criteria_{col}", "severity_score")
            colsofinterest = [
                self.basic_analyusis_config.encounter_col,
                self.basic_analyusis_config.billing_sepsis_col,
                f"POA_Criteria_{col}",
                "severity_score"
            ]
            df_poa1 = df_poa1.select(colsofinterest)
            df_poa2 = df_poa2.select(colsofinterest)
            df_poa3 = df_poa3.select(colsofinterest)
            df_poa = pl.concat([df_poa1, df_poa2, df_poa3], how='vertical')
            df_poa = df_poa.group_by("EncounterEpicCsn").agg(pl.col("severity_score").max()).join(df_poa, on=self.basic_analyusis_config.encounter_col).drop('severity_score_right').with_columns(
                (pl.col(f"POA_Criteria_{col}").str.split('-').list.first()+'-'+pl.col("severity_score").cast(pl.String)).alias('max_POA_Criteria')
            ).drop(f"POA_Criteria_{col}").rename({"max_POA_Criteria": f"POA_Criteria_{col}"})
            display, raw = self._billing_vs_calculated(df_poa, f"POA_Criteria_{col}")
            results_display[col] = display
            results_raw[col] = raw
        return results_display, results_raw


    def _plot_billing_vs_calculated_heatmap(self, results, norm_direction="row"):
        """
        norm_direction options:
            - "row": % across billing columns per pipeline row (each row sums to 100%)
                    "Given pipeline says X, what does billing say?"
            - "col": % across pipeline rows per billing column (each column sums to 100%)
                    "Given billing says X, what does pipeline say?"
            - "total": % of total encounters (entire matrix sums to 100%)
            - "none": raw counts only, no percentages
        """
        import plotly.graph_objects as go

        figures = {}

        for criterion, ct in results.items():
            row_label_col = ct.columns[0]
            billing_cols = [c for c in ct.columns[1:] if c != "Total"]

            y_labels = ct[row_label_col].to_list()
            x_labels = billing_cols

            z_values = ct.select(billing_cols).to_numpy()

            # --- Compute percentages based on direction ---
            if norm_direction == "row":
                totals = z_values.sum(axis=1, keepdims=True)
                pct_values = np.where(totals > 0, z_values / totals * 100, 0)
                colorbar_title = "Row %"
            elif norm_direction == "col":
                totals = z_values.sum(axis=0, keepdims=True)
                pct_values = np.where(totals > 0, z_values / totals * 100, 0)
                colorbar_title = "Col %"
            elif norm_direction == "total":
                total = z_values.sum()
                pct_values = z_values / total * 100 if total > 0 else z_values * 0
                colorbar_title = "Total %"
            else:
                pct_values = None
                colorbar_title = "Count"

            # --- Build annotation text ---
            text_matrix = []
            for i in range(z_values.shape[0]):
                row_text = []
                for j in range(z_values.shape[1]):
                    if pct_values is not None:
                        row_text.append(f"{z_values[i][j]}<br>({pct_values[i][j]:.1f}%)")
                    else:
                        row_text.append(f"{z_values[i][j]}")
                text_matrix.append(row_text)

            # --- Heatmap color based on pct or raw counts ---
            z_color = pct_values if pct_values is not None else z_values

            fig = go.Figure(
                data=go.Heatmap(
                    z=z_color,
                    x=x_labels,
                    y=y_labels,
                    text=text_matrix,
                    texttemplate="%{text}",
                    colorscale="Blues",
                    showscale=True,
                    colorbar=dict(title=colorbar_title),
                )
            )

            fig.update_layout(
                title=f"Pipeline vs Billing Classification — {criterion}",
                xaxis_title="Billing Classification",
                yaxis_title="Pipeline Classification",
                height=500,
                width=800,
            )

            figures[criterion] = fig

        return figures


    def _plot_calculated_vs_billed_distribution(self, results_raw, norm=False, norm_direction="source"):
        import plotly.graph_objects as go
        figures = {}

        for criterion, ct in results_raw.items():
            row_label_col = ct.columns[0]
            billing_cols = [c for c in ct.columns[1:] if c != "Total"]

            pipeline_labels = ct[row_label_col].to_list()
            pipeline_counts = ct["Total"].to_list()

            billing_labels = billing_cols
            billing_counts = [ct[bcol].sum() for bcol in billing_cols]

            all_categories = sorted(set(pipeline_labels + billing_labels))
            pipeline_dict = dict(zip(pipeline_labels, pipeline_counts))
            billing_dict = dict(zip(billing_labels, billing_counts))

            aligned_pipeline = [pipeline_dict.get(cat, 0) for cat in all_categories]
            aligned_billing = [billing_dict.get(cat, 0) for cat in all_categories]

            if norm:
                if norm_direction == "source":
                    pipeline_total = sum(aligned_pipeline)
                    billing_total = sum(aligned_billing)
                    pipeline_values = [c / pipeline_total * 100 for c in aligned_pipeline]
                    billing_values = [c / billing_total * 100 for c in aligned_billing]
                    yaxis_title = "Percentage within source (%)"

                elif norm_direction == "category":
                    pipeline_values = []
                    billing_values = []
                    for p, b in zip(aligned_pipeline, aligned_billing):
                        cat_total = p + b
                        if cat_total > 0:
                            pipeline_values.append(p / cat_total * 100)
                            billing_values.append(b / cat_total * 100)
                        else:
                            pipeline_values.append(0)
                            billing_values.append(0)
                    yaxis_title = "Percentage across sources (%)"

                pipeline_text = [f"{v:.1f}% (n={c})" for v, c in zip(pipeline_values, aligned_pipeline)]
                billing_text = [f"{v:.1f}% (n={c})" for v, c in zip(billing_values, aligned_billing)]

            else:
                pipeline_values = aligned_pipeline
                billing_values = aligned_billing
                pipeline_text = [str(v) for v in pipeline_values]
                billing_text = [str(v) for v in billing_values]
                yaxis_title = "Number of Encounters"

            fig = go.Figure()

            fig.add_trace(go.Bar(
                x=all_categories,
                y=pipeline_values,
                name="Pipeline",
                text=pipeline_text,
                textposition="outside",
            ))

            fig.add_trace(go.Bar(
                x=all_categories,
                y=billing_values,
                name="Billing",
                text=billing_text,
                textposition="outside",
            ))

            fig.update_layout(
                barmode="group",
                title=f"Pipeline vs Billing Distribution — {criterion}",
                xaxis_title="Classification Category",
                yaxis_title=yaxis_title,
                height=500,
                width=900,
                legend=dict(title="Source"),
            )

            figures[criterion] = fig

        return figures
       
    def _get_matches_with_billing(self, df_combined, criterion_col, billing_col, value):
        df_value = df_combined.filter(pl.col(criterion_col) == value)
        df_value = df_value.with_columns(
            pl.when(pl.col(billing_col) == value)
            .then(pl.lit(f"Matched {value}"))
            .otherwise(pl.lit(f"Mismatched {value}"))
            .alias("agreement_group")
        )
        return df_value

    def _factor_analysis_npoa3(self, df_combined, criterion_col):
        billing_col = self.basic_analyusis_config.billing_sepsis_col

        # --- Build groups ---
        df_poa1 = self._get_matches_with_billing(df_combined, criterion_col, billing_col, "POA-1")
        df_poa2 = self._get_matches_with_billing(df_combined, criterion_col, billing_col, "POA-2")
        df_poa3 = self._get_matches_with_billing(df_combined, criterion_col, billing_col, "POA-3")
        df_npoa1 = self._get_matches_with_billing(df_combined, criterion_col, billing_col, "NPOA-1")
        df_npoa2 = self._get_matches_with_billing(df_combined, criterion_col, billing_col, "NPOA-2")
        df_npoa3 = self._get_matches_with_billing(df_combined, criterion_col, billing_col, "NPOA-3")

        # df_npoa3 = df_combined.filter(pl.col(criterion_col) == "NPOA-3")
        # df_npoa3 = df_npoa3.with_columns(
        #     pl.when(pl.col(billing_col) == "NPOA-3")
        #     .then(pl.lit("Matched NPOA-3"))
        #     .otherwise(pl.lit("Mismatched NPOA-3"))
        #     .alias("agreement_group")
        # )
        results_df = {}
        df_summary = {}
        for label, df in zip(["poa1", "poa2", "poa3", "npoa1", "npoa2", "npoa3"],[df_poa1, df_poa2, df_poa3, df_npoa1, df_npoa2, df_npoa3]):
            results = {}
            if len(df) == 0:
                continue

            # --- Categorical factors ---
            for col in self.basic_analyusis_config.categorical_factors:
                results[col] = self._analyze_categorical_factor(df, col)

            # --- Binary factors ---
            for col in self.basic_analyusis_config.binary_factors:
                if df.schema[col] == pl.Utf8:
                    df = df.with_columns(
                        pl.when(pl.col(col).str.to_lowercase().str.starts_with("y")).then(pl.lit(1)).otherwise(pl.lit(0)).alias(col)
                    ).fill_null(0)

                results[col] = self._analyze_binary_factor(df, col)

            # # --- Numerical factors ---
            # for col in self.basic_analyusis_config.numerical_factors:
            #     results[col] = self._analyze_numerical_factor(df, col)
            df_summary[label] = self._build_factor_summary(results)
            fig = self._plot_summary_table(df_summary[label], label)
            results_df[label] = results
            

        return results_df, df_summary

    def _plot_summary_table(self, summary: pl.DataFrame, label: str):
        import plotly.graph_objects as go

        # Clean up values
        factors = summary["Factor"].str.replace_all("_", " ").to_list()
        types = summary["Type"].to_list()
        tests = summary["Test"].to_list()
        p_vals = [
            "< 0.001" if p < 0.001 else f"{p:.3f}" 
            for p in summary["p-value"].to_list()
        ]
        effects = [f"{e:.3f}" for e in summary["Effect Size"].to_list()]
        metrics = summary["Effect Metric"].to_list()
        interps = summary["Interpretation"].to_list()

        # Color-code interpretation
        interp_colors = []
        for interp in interps:
            if interp == "Large":
                interp_colors.append("#d62728")
            elif interp == "Medium":
                interp_colors.append("#ff7f0e")
            elif interp == "Small":
                interp_colors.append("#2ca02c")
            else:
                interp_colors.append("#999999")

        # Build row fill colors based on interpretation
        row_fills = []
        for interp in interps:
            if interp == "Large":
                row_fills.append("#fff0f0")
            elif interp == "Medium":
                row_fills.append("#fff8f0")
            elif interp == "Small":
                row_fills.append("#f0fff0")
            else:
                row_fills.append("#f5f5f5")

        fig = go.Figure(data=[go.Table(
            header=dict(
                values=["<b>Factor</b>", "<b>Type</b>", "<b>Test</b>", 
                        "<b>p-value</b>", "<b>Effect Size</b>", 
                        "<b>Effect Metric</b>", "<b>Interpretation</b>"],
                fill_color="#2c3e50",
                font=dict(color="white", size=14),
                align="left",
                height=35,
            ),
            cells=dict(
                values=[factors, types, tests, p_vals, effects, metrics, interps],
                fill_color=[row_fills] * 7,
                font=dict(size=13),
                align="left",
                height=30,
            ),
        )])

        fig.update_layout(
            title=f"Factor Analysis Summary: Matched vs Mismatched {label}",
            height=350,
            width=1100,
            margin=dict(l=20, r=20, t=50, b=20),
        )

        return fig


    def _analyze_categorical_factor_old(
        self, 
        df_grouped: pl.DataFrame, 
        factor_col: str, 
        group_col: str = "agreement_group",
        top_n: int = 20,
    ):
        """
        Compare a categorical factor across agreement groups.
        
        Args:
            df_grouped: dataframe with agreement_group column already created
            factor_col: categorical column to analyze (e.g., principal_problem, admission_source)
            group_col: column defining the groups
            top_n: keep top N most frequent values, rest becomes "Other"
        
        Returns:
            dict with keys: "table", "chi2_result", "figure"
        """
        results = {}
        groups = df_grouped[group_col].unique().sort().to_list()

        # --- Group low-frequency values into "Other" ---
        top_values = (
            df_grouped
            .group_by(factor_col)
            .len()
            .sort("len", descending=True)
            .head(top_n)
            [factor_col]
            .to_list()
        )

        df_work = df_grouped.with_columns(
            pl.when(pl.col(factor_col).is_in(top_values))
            .then(pl.col(factor_col))
            .otherwise(pl.lit("Other"))
            .alias(f"{factor_col}_grouped")
        )

        grouped_col = f"{factor_col}_grouped"

        # --- Cross-tabulation ---
        ct = (
            df_work
            .group_by([grouped_col, group_col])
            .len()
            .pivot(on=group_col, index=grouped_col, values="len")
            .fill_null(0)
        )

        for g in groups:
            if g not in ct.columns:
                ct = ct.with_columns(pl.lit(0).alias(g))

        # --- Add percentages within each group ---
        ct_display = ct.select([grouped_col] + groups)
        for g in groups:
            g_total = ct_display[g].sum()
            ct_display = ct_display.with_columns(
                (pl.col(g) / g_total * 100).round(1).alias(f"{g} %")
            )

        ct_display = ct_display.sort(groups[0], descending=True)
        results["table"] = ct_display

        # --- Chi-square test ---
        contingency = ct_display.select(groups).to_numpy()
        chi2, p_value, dof, expected = chi2_contingency(contingency)
        results["chi2_result"] = {"chi2": chi2, "p_value": p_value, "dof": dof}

        # --- Figure: horizontal grouped bar chart of percentages ---
        pct_cols = [f"{g} %" for g in groups]
        labels = ct_display[grouped_col].to_list()

        fig = go.Figure()
        for g, pct_col in zip(groups, pct_cols):
            values = ct_display[pct_col].to_list()
            fig.add_trace(go.Bar(
                y=labels,
                x=values,
                name=g,
                orientation="h",
                text=[f"{v:.1f}%" for v in values],
                textposition="outside",
            ))

        fig.update_layout(
            barmode="group",
            title=f"{factor_col} by Agreement Group<br><sup>Chi-square p={p_value:.4f}</sup>",
            xaxis_title="Percentage within group (%)",
            yaxis_title=factor_col,
            height=max(400, len(labels) * 30),
            width=1000,
            legend=dict(title="Group"),
            yaxis=dict(autorange="reversed"),
        )
        results["figure"] = fig

        return results

    def _analyze_categorical_factor(
        self,
        df_grouped: pl.DataFrame,
        factor_col: str,
        group_col: str = "agreement_group",
        top_n: int = 20,
    ):
        results = {}
        groups = df_grouped[group_col].unique().sort().to_list()

        # --- Group low-frequency values into "Other" ---
        top_values = (
            df_grouped
            .group_by(factor_col)
            .len()
            .sort("len", descending=True)
            .head(top_n)
            [factor_col]
            .to_list()
        )

        df_work = df_grouped.with_columns(
            pl.when(pl.col(factor_col).is_in(top_values))
            .then(pl.col(factor_col))
            .otherwise(pl.lit("Other"))
            .alias(f"{factor_col}_grouped")
        )

        grouped_col = f"{factor_col}_grouped"

        # --- Cross-tabulation (raw counts) ---
        ct = (
            df_work
            .group_by([grouped_col, group_col])
            .len()
            .pivot(on=group_col, index=grouped_col, values="len")
            .fill_null(0)
        )

        for g in groups:
            if g not in ct.columns:
                ct = ct.with_columns(pl.lit(0).alias(g))

        ct = ct.select([grouped_col] + groups)

        # --- Chi-square on raw counts ---
        contingency = ct.select(groups).to_numpy()
        chi2, p_value, dof, expected = chi2_contingency(contingency)
        n = contingency.sum()
        k = min(contingency.shape) - 1
        cramers_v = np.sqrt(chi2 / (n * k)) if (n * k) > 0 else 0

        results["chi2_result"] = {"chi2": chi2, "p_value": p_value, "dof": dof, "cramers_v": cramers_v}

        # --- ROW-WISE percentages: for each factor value, % matched vs mismatched ---
        ct = ct.with_columns(
            pl.sum_horizontal(groups).alias("row_total")
        )

        for g in groups:
            ct = ct.with_columns(
                (pl.col(g) / pl.col("row_total") * 100).round(1).alias(f"{g} %")
            )

        ct = ct.sort("row_total", descending=True)
        results["table"] = ct

        # --- Figure: horizontal grouped bar showing % matched vs mismatched per factor value ---
        labels = ct[grouped_col].to_list()
        pct_cols = [f"{g} %" for g in groups]

        fig = go.Figure()
        for g, pct_col in zip(groups, pct_cols):
            values = ct[pct_col].to_list()
            counts = ct[g].to_list()
            fig.add_trace(go.Bar(
                y=labels,
                x=values,
                name=g,
                orientation="h",
                text=[f"{v:.1f}% (n={c})" for v, c in zip(values, counts)],
                textposition="outside",
            ))

        fig.update_layout(
            barmode="group",
            title=f"{factor_col}: Match vs Mismatch Rate per Category<br>"
                f"<sup>Chi-square p={p_value:.4f}</sup>",
            xaxis_title="Percentage (%)",
            yaxis_title=factor_col,
            autosize=True,
            # height=max(400, len(labels) * 30),
            # width=1000,
            legend=dict(title="Group"),
            yaxis=dict(autorange="reversed"),
        )
        results["figure"] = fig

        return results

    def _analyze_binary_factor(
        self,
        df_grouped: pl.DataFrame,
        factor_col: str,
        positive_label: str = None,
        group_col: str = "agreement_group",
    ):
        results = {}
        groups = df_grouped[group_col].unique().sort().to_list()
        label = positive_label or factor_col

        # --- Cross-tabulation ---
        ct = (
            df_grouped
            .group_by([factor_col, group_col])
            .len()
            .pivot(on=group_col, index=factor_col, values="len")
            .fill_null(0)
        )

        for g in groups:
            if g not in ct.columns:
                ct = ct.with_columns(pl.lit(0).alias(g))

        for val in [0, 1]:
            if val not in ct[factor_col].to_list():
                missing_row = {factor_col: val}
                for g in groups:
                    missing_row[g] = 0
                ct = pl.concat([ct, pl.DataFrame([missing_row])]).sort(factor_col)

        ct = ct.select([factor_col] + groups)

        ct = ct.sort(factor_col, descending=True)

        # --- Row-wise percentages: for each factor value, % matched vs mismatched ---
        ct = ct.with_columns(
            pl.sum_horizontal(groups).alias("row_total")
        )
        for g in groups:
            ct = ct.with_columns(
                (pl.col(g) / pl.col("row_total") * 100).round(1).alias(f"{g} %")
            )

        results["table"] = ct

        # --- Statistical test ---
        contingency = ct.select(groups).to_numpy()
        if contingency.min() < 5:
            odds_ratio, p_value = fisher_exact(contingency)
            test_name = "Fisher's exact"
        else:
            chi2, p_value, dof, expected = chi2_contingency(contingency)
            test_name = "Chi-square"
        
        # Always compute OR
        a, b = contingency[0]
        c, d = contingency[1]
        odds_ratio = (a * d) / (b * c) if (b * c) > 0 else None

        results["test_result"] = {
            "test": test_name,
            "p_value": p_value,
            "odds_ratio": odds_ratio,
        }

        # --- Figure: grouped bar showing % matched vs mismatched per factor value ---
        factor_labels = [f"{label} = {v}" for v in ct[factor_col].to_list()]
        row_totals = ct["row_total"].to_list()
        display_labels = [f"{fl} (N={n})" for fl, n in zip(factor_labels, row_totals)]

        fig = go.Figure()
        for g in groups:
            pcts = ct[f"{g} %"].to_list()
            counts = ct[g].to_list()
            fig.add_trace(go.Bar(
                y=display_labels,
                x=pcts,
                name=g,
                orientation="h",
                text=[f"{p:.1f}% (n={c})" for p, c in zip(pcts, counts)],
                textposition="outside",
            ))

        fig.update_layout(
            barmode="group",
            title=f"{label}: Match vs Mismatch Rate<br><sup>{test_name} p={p_value:.4f}</sup>",
            xaxis_title="Percentage (%)",
            yaxis_title=label,
            height=400,
            width=900,
            legend=dict(title="Group"),
            yaxis=dict(autorange="reversed"),
        )
        results["figure"] = fig

        return results


    def _build_factor_summary(self, all_results):
        def _interpret_cramers_v(v):
            if v < 0.1:
                return "Negligible"
            elif v < 0.3:
                return "Small"
            elif v < 0.5:
                return "Medium"
            else:
                return "Large"


        def _interpret_odds_ratio(or_val):
            if or_val is None:
                return "N/A"
            log_or = abs(np.log(or_val))
            if log_or < 0.3:
                return "Negligible"
            elif log_or < 0.8:
                return "Small"
            elif log_or < 1.5:
                return "Medium"
            else:
                return "Large"
        rows = []
        for factor_name, result in all_results.items():
            if "chi2_result" in result:
                rows.append({
                    "Factor": factor_name,
                    "Type": "Categorical",
                    "Test": "Chi-square",
                    "p-value": result["chi2_result"]["p_value"],
                    "Effect Size": result["chi2_result"]["cramers_v"],
                    "Effect Metric": "Cramér's V",
                    "Interpretation": _interpret_cramers_v(result["chi2_result"]["cramers_v"]),
                })
            elif "test_result" in result:
                test_info = result["test_result"]
                or_val = test_info.get("odds_ratio")
                rows.append({
                    "Factor": factor_name,
                    "Type": "Binary",
                    "Test": test_info["test"],
                    "p-value": test_info["p_value"],
                    "Effect Size": or_val,
                    "Effect Metric": "Odds Ratio",
                    "Interpretation": _interpret_odds_ratio(or_val),
                })

        summary = pl.DataFrame(rows)

        # Sort within each type separately
        categorical = summary.filter(pl.col("Type") == "Categorical").sort("Effect Size", descending=True)
        binary = summary.filter(pl.col("Type") == "Binary").sort(
            pl.col("Effect Size").map_elements(lambda x: abs(np.log(x)) if x and x > 0 else 0, return_dtype=pl.Float64),
            descending=True
        )
        numerical = summary.filter(pl.col("Type") == "Numerical").sort("Effect Size", descending=True)

        return pl.concat([categorical, binary, numerical])



    def _analyze_numerical_factor(
        self,
        df_grouped: pl.DataFrame,
        factor_col: str,
        group_col: str = "agreement_group",
    ):
        """
        Compare a numerical factor across agreement groups.
        Uses Mann-Whitney U for 2 groups, Kruskal-Wallis for 3+ groups.
        
        Args:
            df_grouped: dataframe with agreement_group column already created
            factor_col: numerical column to analyze (e.g., SBP, WBC, Creatinine)
            group_col: column defining the groups
        
        Returns:
            dict with keys: "table", "test_result", "figure"
        """
        from scipy.stats import mannwhitneyu, kruskal

        results = {}
        groups = df_grouped[group_col].unique().sort().to_list()

        # --- Descriptive statistics per group ---
        stats = (
            df_grouped
            .group_by(group_col)
            .agg(
                pl.col(factor_col).count().alias("n"),
                pl.col(factor_col).mean().round(2).alias("mean"),
                pl.col(factor_col).std().round(2).alias("std"),
                pl.col(factor_col).median().alias("median"),
                pl.col(factor_col).quantile(0.25).alias("Q1"),
                pl.col(factor_col).quantile(0.75).alias("Q3"),
                pl.col(factor_col).min().alias("min"),
                pl.col(factor_col).max().alias("max"),
            )
            .sort(group_col)
        )
        results["table"] = stats

        # --- Statistical test ---
        group_values = []
        for g in groups:
            vals = (
                df_grouped
                .filter(pl.col(group_col) == g)
                [factor_col]
                .drop_nulls()
                .to_numpy()
            )
            group_values.append(vals)

        if len(groups) == 2:
            stat, p_value = mannwhitneyu(group_values[0], group_values[1], alternative="two-sided")
            test_name = "Mann-Whitney U"
        else:
            stat, p_value = kruskal(*group_values)
            test_name = "Kruskal-Wallis"

        results["test_result"] = {"test": test_name, "statistic": stat, "p_value": p_value}

        # --- Figure: box plot per group ---
        fig = go.Figure()
        colors = ["#636EFA", "#EF553B", "#00CC96", "#AB63FA"]

        for i, g in enumerate(groups):
            vals = group_values[i]
            fig.add_trace(go.Box(
                y=vals,
                name=g,
                marker_color=colors[i % len(colors)],
                boxmean=True,  # show mean as dashed line
            ))

        fig.update_layout(
            title=f"{factor_col} by Agreement Group<br><sup>{test_name} p={p_value:.4f}</sup>",
            yaxis_title=factor_col,
            height=500,
            width=700,
            showlegend=False,
        )
        results["figure"] = fig

        return results

    def _merge_poas(self, df_poa_1, df_poa_2, df_poa_3, col, agg='max'):
        df_poa1 = self._convert_sepsis_to_score(df_poa_1, f"POA_Criteria_{col}", "severity_score")
        df_poa2 = self._convert_sepsis_to_score(df_poa_2, f"POA_Criteria_{col}", "severity_score")
        df_poa3 = self._convert_sepsis_to_score(df_poa_3, f"POA_Criteria_{col}", "severity_score")
        df_poa = pl.concat([df_poa1, df_poa2, df_poa3], how='vertical')
        if agg == 'max':
            df_poa = df_poa.group_by("EncounterEpicCsn").agg(pl.col("severity_score").max()).join(df_poa, on=self.basic_analyusis_config.encounter_col).drop('severity_score_right').with_columns(
                (pl.col(f"POA_Criteria_{col}").str.split('-').list.first()+'-'+pl.col("severity_score").cast(pl.String)).alias('max_POA_Criteria')
            ).drop(f"POA_Criteria_{col}").rename({"max_POA_Criteria": f"POA_Criteria_{col}"})
            df_poa = df_poa.group_by("EncounterEpicCsn").last()
        elif agg == 'first':
            df_poa = df_poa.group_by("EncounterEpicCsn").agg(pl.col("earliest_sepsis1_instance").first(), pl.col("earliest_sepsis2_instance").first(), pl.col("earliest_sepsis3_instance").first()).join(df_poa, on=self.basic_analyusis_config.encounter_col).drop('severity_score_right').with_columns(
                (pl.col(f"POA_Criteria_{col}").str.split('-').list.first()+'-'+pl.col("severity_score").cast(pl.String)).alias('max_POA_Criteria')
            ).drop(f"POA_Criteria_{col}").rename({"max_POA_Criteria": f"POA_Criteria_{col}"})
            df_poa = df_poa.group_by("EncounterEpicCsn").last()

        return df_poa

    def _filter_cofounding_factors(self, df: pl.DataFrame | List[pl.DataFrame]):
        def filter_confounding_ondf(df):
            for col in self.basic_analyusis_config.cofounding_factors:
                df = df.filter(pl.col(col) == 'N')
            return df

        if isinstance(df, list):
            for i in range(len(df)):
                df[i] = filter_confounding_ondf(df[i])
            return df
        else:
            return filter_confounding_ondf(df)

    import polars as pl
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    import numpy as np

    def plot_time_to_sepsis_by_score(
        self,
        df: pl.DataFrame,
        time_col: str = "minutes_arrival_to_first_sepsis",
        label: str='arrival',
        sepsis_col: str= "sepsis_score"
    ):
        # --- 1. Prepare data ---
        pdf = (
            df.select([sepsis_col, time_col])
            .to_pandas()
            .assign(hours=lambda x: x[time_col] / 60)
            .dropna(subset=[sepsis_col, "hours"])
        )

        groups = ["POA-1", "POA-2", "POA-3", "NPOA-1", "NPOA-2", "NPOA-3"]
        base_colors = {1: "55, 100, 180", 2: "221, 132, 82", 3: "85, 168, 104"}
        style = {
            "POA-1":  {"fill": f"rgba({base_colors[1]}, 0.75)", "line": f"rgba({base_colors[1]}, 1.0)"},
            "POA-2":  {"fill": f"rgba({base_colors[2]}, 0.75)", "line": f"rgba({base_colors[2]}, 1.0)"},
            "POA-3":  {"fill": f"rgba({base_colors[3]}, 0.75)", "line": f"rgba({base_colors[3]}, 1.0)"},
            "NPOA-1": {"fill": f"rgba({base_colors[1]}, 0.25)", "line": f"rgba({base_colors[1]}, 0.5)"},
            "NPOA-2": {"fill": f"rgba({base_colors[2]}, 0.25)", "line": f"rgba({base_colors[2]}, 0.5)"},
            "NPOA-3": {"fill": f"rgba({base_colors[3]}, 0.25)", "line": f"rgba({base_colors[3]}, 0.5)"},
        }

        # --- 2. Build figure ---
        fig = make_subplots(
            rows=1, cols=2,
            subplot_titles=("Distribution Shape (Violin)", "Summary + Individual Patients (Box + Strip)"),
            horizontal_spacing=0.12
        )

        for group in groups:
            subset = pdf[pdf[sepsis_col] == group]["hours"]  # <-- changed from "group" col to "sepsis_score"
            n = len(subset)
            s = style[group]

            fig.add_trace(
                go.Violin(
                    y=subset,
                    name=group,
                    legendgroup=group,
                    showlegend=True,
                    line_color=s["line"],
                    fillcolor=s["fill"],
                    opacity=1.0,
                    box_visible=True,
                    meanline_visible=True,
                    points=False,
                    hovertemplate=f"<b>{group}</b><br>Hours: %{{y:.1f}}<br>N={n}<extra></extra>"
                ),
                row=1, col=1
            )

            fig.add_trace(
                go.Box(
                    y=subset,
                    name=group,
                    legendgroup=group,
                    showlegend=False,
                    marker_color=s["line"],
                    line_color=s["line"],
                    fillcolor="rgba(255,255,255,0.8)",
                    boxmean="sd",
                    boxpoints="all",
                    jitter=0.35,
                    pointpos=0,
                    marker=dict(size=4, opacity=0.4, color=s["fill"], line=dict(width=0.5, color="white")),
                    hovertemplate=f"<b>{group}</b><br>Hours: %{{y:.1f}}<extra></extra>"
                ),
                row=1, col=2
            )

        for i, group in enumerate(groups):
            subset = pdf[pdf[sepsis_col] == group]["hours"]
            n = len(subset)
            fig.add_annotation(
                x=group,
                y=subset.max(),
                text=f"n={n}",
                showarrow=False,
                font=dict(size=11, color=style[group]["line"]),
                yshift=10,          # pushes the label slightly above the max value
                xref="x2",          # x2 = second panel's x-axis
                yref="y2",          # y2 = second panel's y-axis
                row=1, col=2
            )

        # --- 3. Layout (unchanged) ---
        fig.update_layout(
            title=dict(
                text=f"Time from Arrival to First Sepsis Instance — POA vs NPOA by {'Billing diagnosis' if sepsis_col == 'Sepsis_Category' else 'Pipeline'}",
                font=dict(size=16, family="Arial"),
                x=0.5
            ),
            height=600, width=1200,
            plot_bgcolor="white", paper_bgcolor="white",
            violinmode="group", boxmode="group",
            legend=dict(title="Group", orientation="v", x=1.02, y=0.5, tracegroupgap=4),
            font=dict(family="Arial", size=12),
        )
        fig.update_yaxes(title_text="Hours from Arrival to First Sepsis", gridcolor="#eeeeee", zerolinecolor="#cccccc", row=1, col=1)
        fig.update_yaxes(title_text="Hours from Arrival to First Sepsis", gridcolor="#eeeeee", zerolinecolor="#cccccc", row=1, col=2)
        fig.update_xaxes(showgrid=False)

        return fig


    def _get_time_from_arrival_to_first_sepsis(self, df_list: List[pl.DataFrame], col_name: str, period_hrs:int,  label: str):
        sepsis_cols = ['earliest_sepsis1_instance', 'earliest_sepsis2_instance', 'earliest_sepsis3_instance']
        
        # Step 1: Ensure all sepsis columns exist in every df
        for i in range(len(df_list)):
            for col in sepsis_cols:
                if col not in df_list[i].columns:
                    df_list[i] = df_list[i].with_columns(pl.lit(None).cast(pl.Datetime).alias(col))
        
        # Step 2: Keep only relevant columns and concat
        for i in range(len(df_list)):
            df_list[i] = df_list[i].select(["EncounterEpicCsn"] + sepsis_cols + [col_name] + ["Sepsis_Category"])
        df_all = pl.concat(df_list, how='vertical')
        
        # Step 3: Collapse to one row per encounter — take the min of each sepsis col and arrival
        # (in case the same encounter spans multiple dfs)
        df_collapsed = df_all.group_by("EncounterEpicCsn").agg([
            pl.col("earliest_sepsis1_instance").min(),
            pl.col("earliest_sepsis2_instance").min(),
            pl.col("earliest_sepsis3_instance").min(),
            pl.col("Sepsis_Category").first(),
            pl.col(col_name).min(),  # arrival time — min is safe if it's the same value
        ])

        # Step 4: Find the earliest sepsis instance across all 3 types
        df_result = df_collapsed.with_columns(
            pl.min_horizontal("earliest_sepsis1_instance",
                            "earliest_sepsis2_instance",
                            "earliest_sepsis3_instance").alias("first_sepsis_time")
        )
        
        # Step 5: Identify which sepsis type fired first
        df_result = df_result.with_columns(
            pl.when(pl.col("first_sepsis_time") == pl.col("earliest_sepsis1_instance")).then(pl.lit(1))
            .when(pl.col("first_sepsis_time") == pl.col("earliest_sepsis2_instance")).then(pl.lit(2))
            .when(pl.col("first_sepsis_time") == pl.col("earliest_sepsis3_instance")).then(pl.lit(3))
            .otherwise(pl.lit(None))
            .alias("first_sepsis_score")
        )
        
        # Step 6: Compute time delta from arrival to first sepsis
        df_result = df_result.with_columns(
            (pl.col("first_sepsis_time") - pl.col(col_name))
            .dt.total_hours(fractional=True)  # or .total_seconds(), .total_hours()
            .alias(f"hours_{label}_to_first_sepsis")
        )
        
        df_result = df_result.with_columns(
            pl.when(pl.col("first_sepsis_time") <= (pl.col(col_name)+pl.duration(hours=period_hrs))).then(pl.lit("POA")).otherwise(pl.lit("NPOA")).alias("POA_class")
        ).with_columns(
            sepsis_score=pl.col("POA_class")+'-'+pl.col("first_sepsis_score").cast(pl.String)
        )
        # Step 7: Drop rows where no sepsis was ever recorded
        df_result = df_result.drop_nulls(subset=["first_sepsis_time"])
        
        return df_result
        x = 0


    def _analyze_factor_simple(
        self,
        df_sepsis1: pl.DataFrame,
        df_sepsis2: pl.DataFrame,
        df_sepsis3: pl.DataFrame,
        factor_col: str,
        criterion_col: str,
        top_n: int = 20,
    ):
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots

        results = {}

        # --- Step 1: Select required columns and concat ---
        required_cols = [
            self.basic_analyusis_config.encounter_col,
            criterion_col,
            factor_col,
        ]

        dfs = []
        for df in [df_sepsis1, df_sepsis2, df_sepsis3]:
            dfs.append(df.select(required_cols))

        df_all = pl.concat(dfs)

        # --- Step 2: Group low-frequency factor values into "Other" ---
        top_values = (
            df_all
            .group_by(factor_col)
            .len()
            .sort("len", descending=True)
            .head(top_n)
            [factor_col]
            .to_list()
        )

        df_all = df_all.with_columns(
            pl.when(pl.col(factor_col).is_in(top_values))
            .then(pl.col(factor_col))
            .otherwise(pl.lit("Other"))
            .alias("factor_grouped")
        )

        # --- Step 3: Count per (factor_value, criterion_value) ---
        ct = (
            df_all
            .group_by(["factor_grouped", criterion_col])
            .len()
        )

        totals = (
            ct
            .group_by("factor_grouped")
            .agg(pl.col("len").sum().alias("total"))
        )

        ct = ct.join(totals, on="factor_grouped")
        ct = ct.with_columns(
            (pl.col("len") / pl.col("total") * 100).round(1).alias("pct")
        )

        results["table"] = ct

        # --- Step 4: Prepare labels ---
        factor_values = (
            df_all
            .group_by("factor_grouped")
            .len()
            .sort("len", descending=True)
            ["factor_grouped"]
            .to_list()
        )

        factor_totals = dict(
            df_all
            .group_by("factor_grouped")
            .len()
            .iter_rows()
        )
        display_labels = [f"{v} (N={factor_totals.get(v, 0)})" for v in factor_values]

        # --- Step 5: Build side-by-side subplots ---
        criterion_values = sorted(df_all[criterion_col].unique().to_list())

        fig = make_subplots(
            rows=1, cols=2,
            subplot_titles=["Count", "Percentage (%)"],
            shared_yaxes=True,
            horizontal_spacing=0.1,
        )

        for crit_val in criterion_values:
            counts = []
            pcts = []
            for fv in factor_values:
                row = ct.filter(
                    (pl.col("factor_grouped") == fv)
                    & (pl.col(criterion_col) == crit_val)
                )
                if row.height > 0:
                    counts.append(row["len"][0])
                    pcts.append(row["pct"][0])
                else:
                    counts.append(0)
                    pcts.append(0.0)

            count_text = [str(c) for c in counts]
            pct_text = [f"{p:.1f}% (n={c})" for p, c in zip(pcts, counts)]

            # Count subplot (left)
            fig.add_trace(
                go.Bar(
                    y=display_labels,
                    x=counts,
                    name=crit_val,
                    orientation="h",
                    text=count_text,
                    textposition="outside",
                    legendgroup=crit_val,
                ),
                row=1, col=1,
            )

            # Percentage subplot (right)
            fig.add_trace(
                go.Bar(
                    y=display_labels,
                    x=pcts,
                    name=crit_val,
                    orientation="h",
                    text=pct_text,
                    textposition="outside",
                    legendgroup=crit_val,
                    showlegend=False,
                ),
                row=1, col=2,
            )

        fig.update_layout(
            barmode="group",
            title=f"{factor_col} Distribution by Classification — {criterion_col}",
            height=max(500, len(factor_values) * 50),
            width=1600,
            legend=dict(title="Classification"),
        )

        fig.update_yaxes(autorange="reversed", row=1, col=1)
        fig.update_yaxes(autorange="reversed", row=1, col=2)
        fig.update_xaxes(title_text="Count", row=1, col=1)
        fig.update_xaxes(title_text="Percentage (%)", row=1, col=2)

        results["figure"] = fig
        return results

    def _analyze_factor_match_simple(
        self,
        df_sepsis1: pl.DataFrame,
        df_sepsis2: pl.DataFrame,
        df_sepsis3: pl.DataFrame,
        factor_col: str,
        criterion_col: str,
        top_n: int = 20,
    ):
        """
        For each factor value, show % matched vs mismatched
        where billing is the reference:
            - Matched: pipeline agrees with billing's POA/NPOA prefix
            - Mismatched: pipeline disagrees with billing's POA/NPOA prefix
        Uses stacked bars so each factor value sums to 100%.
        """
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots

        billing_col = self.basic_analyusis_config.billing_sepsis_col
        results = {}

        # --- Step 1: Select required columns and concat ---
        required_cols = [
            self.basic_analyusis_config.encounter_col,
            criterion_col,
            billing_col,
            factor_col,
        ]

        dfs = []
        for df in [df_sepsis1, df_sepsis2, df_sepsis3]:
            dfs.append(df.select(required_cols))

        df_all = pl.concat(dfs)

        # --- Step 2: Extract POA/NPOA prefix from both columns ---
        df_all = df_all.with_columns(
            pl.col(criterion_col).str.split("-").list.first().alias("pipeline_group"),
            pl.col(billing_col).str.split("-").list.first().alias("billing_group"),
        )

        # --- Step 3: Create agreement categories (billing as reference) ---
        df_all = df_all.with_columns(
            pl.when(
                (pl.col("billing_group") == "POA") & (pl.col("pipeline_group") == "POA")
            ).then(pl.lit("Billing POA — Pipeline Agrees"))
            .when(
                (pl.col("billing_group") == "POA") & (pl.col("pipeline_group") != "POA")
            ).then(pl.lit("Billing POA — Pipeline Disagrees"))
            .when(
                (pl.col("billing_group") == "NPOA") & (pl.col("pipeline_group") == "NPOA")
            ).then(pl.lit("Billing NPOA — Pipeline Agrees"))
            .when(
                (pl.col("billing_group") == "NPOA") & (pl.col("pipeline_group") != "NPOA")
            ).then(pl.lit("Billing NPOA — Pipeline Disagrees"))
            .when(
                (pl.col("billing_group") == "UPOA") & (pl.col("pipeline_group") == "POA")
            ).then(pl.lit("Billing UPOA — Pipeline says POA"))
            .when(
                (pl.col("billing_group") == "UPOA") & (pl.col("pipeline_group") == "NPOA")
            ).then(pl.lit("Billing UPOA — Pipeline says NPOA"))
            .otherwise(pl.lit("Other"))
            .alias("agreement")
        )

        # --- Step 4: Group low-frequency factor values into "Other" ---
        top_values = (
            df_all
            .group_by(factor_col)
            .len()
            .sort("len", descending=True)
            .head(top_n)
            [factor_col]
            .to_list()
        )

        df_all = df_all.with_columns(
            pl.when(pl.col(factor_col).is_in(top_values))
            .then(pl.col(factor_col))
            .otherwise(pl.lit("Other"))
            .alias("factor_grouped")
        )

        # --- Step 5: Count per (factor_value, agreement) ---
        ct = (
            df_all
            .group_by(["factor_grouped", "agreement"])
            .len()
        )

        totals = (
            ct
            .group_by("factor_grouped")
            .agg(pl.col("len").sum().alias("total"))
        )

        ct = ct.join(totals, on="factor_grouped")
        ct = ct.with_columns(
            (pl.col("len") / pl.col("total") * 100).round(1).alias("pct")
        )

        results["table"] = ct

        # --- Step 6: Prepare labels ---
        factor_values = (
            df_all
            .group_by("factor_grouped")
            .len()
            .sort("len", descending=True)
            ["factor_grouped"]
            .to_list()
        )

        factor_totals = dict(
            df_all
            .group_by("factor_grouped")
            .len()
            .iter_rows()
        )
        display_labels = [f"{v} (N={factor_totals.get(v, 0)})" for v in factor_values]

        # --- Step 7: Build stacked bar subplots ---
        agreement_values = [
            "Billing POA — Pipeline Agrees",
            "Billing POA — Pipeline Disagrees",
            "Billing NPOA — Pipeline Agrees",
            "Billing NPOA — Pipeline Disagrees",
            "Billing UPOA — Pipeline says POA",
            "Billing UPOA — Pipeline says NPOA",
        ]

        colors = {
            "Billing POA — Pipeline Agrees": "#2ca02c",
            "Billing POA — Pipeline Disagrees": "#d62728",
            "Billing NPOA — Pipeline Agrees": "#1f77b4",
            "Billing NPOA — Pipeline Disagrees": "#ff7f0e",
            "Billing UPOA — Pipeline says POA": "#9467bd",
            "Billing UPOA — Pipeline says NPOA": "#8c564b",
        }

        fig = make_subplots(
            rows=1, cols=2,
            subplot_titles=["Count", "Percentage (%)"],
            shared_yaxes=True,
            horizontal_spacing=0.1,
        )

        for ag in agreement_values:
            counts = []
            pcts = []
            for fv in factor_values:
                row = ct.filter(
                    (pl.col("factor_grouped") == fv)
                    & (pl.col("agreement") == ag)
                )
                if row.height > 0:
                    counts.append(row["len"][0])
                    pcts.append(row["pct"][0])
                else:
                    counts.append(0)
                    pcts.append(0.0)

            count_text = [str(c) for c in counts]
            pct_text = [f"{p:.1f}%" for p in pcts]

            fig.add_trace(
                go.Bar(
                    y=display_labels,
                    x=counts,
                    name=ag,
                    orientation="h",
                    text=count_text,
                    textposition="inside",
                    marker_color=colors.get(ag),
                    legendgroup=ag,
                ),
                row=1, col=1,
            )

            fig.add_trace(
                go.Bar(
                    y=display_labels,
                    x=pcts,
                    name=ag,
                    orientation="h",
                    text=pct_text,
                    textposition="inside",
                    marker_color=colors.get(ag),
                    legendgroup=ag,
                    showlegend=False,
                ),
                row=1, col=2,
            )

        fig.update_layout(
            barmode="stack",
            title=f"{factor_col}: Billing vs Pipeline Agreement — {criterion_col}",
            height=max(500, len(factor_values) * 50),
            width=1600,
            legend=dict(title="Agreement (Billing Reference)"),
        )

        fig.update_yaxes(autorange="reversed", row=1, col=1)
        fig.update_yaxes(autorange="reversed", row=1, col=2)
        fig.update_xaxes(title_text="Count", row=1, col=1)
        fig.update_xaxes(title_text="Percentage (%)", row=1, col=2)

        results["figure"] = fig
        return results


    # def _analyze_factor_match_simple_1(
    #     self,
    #     df_sepsis1: pl.DataFrame,
    #     df_sepsis2: pl.DataFrame,
    #     df_sepsis3: pl.DataFrame,
    #     factor_col: str,
    #     criterion_col: str,
    #     top_n: int = 20,
    # ):
    #     """
    #     For each factor value, show % matched vs mismatched
    #     where match is defined as: both pipeline and billing agree on
    #     POA vs NPOA (ignoring the severity suffix 1, 2, 3).
    #     """
    #     import plotly.graph_objects as go
    #     from plotly.subplots import make_subplots

    #     billing_col = self.basic_analyusis_config.billing_sepsis_col
    #     results = {}

    #     # --- Step 1: Select required columns and concat ---
    #     required_cols = [
    #         self.basic_analyusis_config.encounter_col,
    #         criterion_col,
    #         billing_col,
    #         factor_col,
    #     ]

    #     dfs = []
    #     for df in [df_sepsis1, df_sepsis2, df_sepsis3]:
    #         dfs.append(df.select(required_cols))

    #     df_all = pl.concat(dfs)

    #     # --- Step 2: Extract POA/NPOA prefix from both columns ---
    #     df_all = df_all.with_columns(
    #         pl.col(criterion_col).str.split("-").list.first().alias("pipeline_group"),
    #         pl.col(billing_col).str.split("-").list.first().alias("billing_group"),
    #     )

    #     # --- Step 3: Create agreement categories ---
    #     # Matched POA:  pipeline=POA  & billing=POA
    #     # Matched NPOA: pipeline=NPOA & billing=NPOA
    #     # Pipeline POA / Billing NPOA: pipeline=POA & billing=NPOA (or UPOA)
    #     # Pipeline NPOA / Billing POA: pipeline=NPOA & billing=POA (or UPOA)
    #     df_all = df_all.with_columns(
    #         pl.when(
    #             (pl.col("pipeline_group") == "POA") & (pl.col("billing_group") == "POA")
    #         ).then(pl.lit("Matched POA"))
    #         .when(
    #             (pl.col("pipeline_group") == "NPOA") & (pl.col("billing_group") == "NPOA")
    #         ).then(pl.lit("Matched NPOA"))
    #         .when(
    #             (pl.col("pipeline_group") == "POA") & (pl.col("billing_group") != "POA")
    #         ).then(pl.lit("Pipeline POA / Billing Disagrees"))
    #         .when(
    #             (pl.col("pipeline_group") == "NPOA") & (pl.col("billing_group") != "NPOA")
    #         ).then(pl.lit("Pipeline NPOA / Billing Disagrees"))
    #         .otherwise(pl.lit("Other"))
    #         .alias("agreement")
    #     )

    #     # --- Step 4: Group low-frequency factor values into "Other" ---
    #     top_values = (
    #         df_all
    #         .group_by(factor_col)
    #         .len()
    #         .sort("len", descending=True)
    #         .head(top_n)
    #         [factor_col]
    #         .to_list()
    #     )

    #     df_all = df_all.with_columns(
    #         pl.when(pl.col(factor_col).is_in(top_values))
    #         .then(pl.col(factor_col))
    #         .otherwise(pl.lit("Other"))
    #         .alias("factor_grouped")
    #     )

    #     # --- Step 5: Count per (factor_value, agreement) ---
    #     ct = (
    #         df_all
    #         .group_by(["factor_grouped", "agreement"])
    #         .len()
    #     )

    #     totals = (
    #         ct
    #         .group_by("factor_grouped")
    #         .agg(pl.col("len").sum().alias("total"))
    #     )

    #     ct = ct.join(totals, on="factor_grouped")
    #     ct = ct.with_columns(
    #         (pl.col("len") / pl.col("total") * 100).round(1).alias("pct")
    #     )

    #     results["table"] = ct

    #     # --- Step 6: Prepare labels ---
    #     factor_values = (
    #         df_all
    #         .group_by("factor_grouped")
    #         .len()
    #         .sort("len", descending=True)
    #         ["factor_grouped"]
    #         .to_list()
    #     )

    #     factor_totals = dict(
    #         df_all
    #         .group_by("factor_grouped")
    #         .len()
    #         .iter_rows()
    #     )
    #     display_labels = [f"{v} (N={factor_totals.get(v, 0)})" for v in factor_values]

    #     # --- Step 7: Build side-by-side subplots ---
    #     agreement_values = [
    #         "Matched POA",
    #         "Matched NPOA",
    #         "Pipeline POA / Billing Disagrees",
    #         "Pipeline NPOA / Billing Disagrees",
    #     ]

    #     colors = {
    #         "Matched POA": "#636EFA",
    #         "Matched NPOA": "#00CC96",
    #         "Pipeline POA / Billing Disagrees": "#EF553B",
    #         "Pipeline NPOA / Billing Disagrees": "#AB63FA",
    #     }

    #     fig = make_subplots(
    #         rows=1, cols=2,
    #         subplot_titles=["Count", "Percentage (%)"],
    #         shared_yaxes=True,
    #         horizontal_spacing=0.1,
    #     )

    #     for ag in agreement_values:
    #         counts = []
    #         pcts = []
    #         for fv in factor_values:
    #             row = ct.filter(
    #                 (pl.col("factor_grouped") == fv)
    #                 & (pl.col("agreement") == ag)
    #             )
    #             if row.height > 0:
    #                 counts.append(row["len"][0])
    #                 pcts.append(row["pct"][0])
    #             else:
    #                 counts.append(0)
    #                 pcts.append(0.0)

    #         count_text = [str(c) for c in counts]
    #         pct_text = [f"{p:.1f}% (n={c})" for p, c in zip(pcts, counts)]

    #         fig.add_trace(
    #             go.Bar(
    #                 y=display_labels,
    #                 x=counts,
    #                 name=ag,
    #                 orientation="h",
    #                 text=count_text,
    #                 textposition="outside",
    #                 marker_color=colors.get(ag),
    #                 legendgroup=ag,
    #             ),
    #             row=1, col=1,
    #         )

    #         fig.add_trace(
    #             go.Bar(
    #                 y=display_labels,
    #                 x=pcts,
    #                 name=ag,
    #                 orientation="h",
    #                 text=pct_text,
    #                 textposition="outside",
    #                 marker_color=colors.get(ag),
    #                 legendgroup=ag,
    #                 showlegend=False,
    #             ),
    #             row=1, col=2,
    #         )

    #     fig.update_layout(
    #         barmode="group",
    #         title=f"{factor_col}: Match vs Mismatch (POA/NPOA) — {criterion_col}",
    #         height=max(500, len(factor_values) * 50),
    #         width=1600,
    #         legend=dict(title="Agreement"),
    #     )

    #     fig.update_yaxes(autorange="reversed", row=1, col=1)
    #     fig.update_yaxes(autorange="reversed", row=1, col=2)
    #     fig.update_xaxes(title_text="Count", row=1, col=1)
    #     fig.update_xaxes(title_text="Percentage (%)", row=1, col=2)

    #     results["figure"] = fig
    #     return results


    def _poa_rate_by_factor(
        self,
        df_sepsis1: pl.DataFrame,
        df_sepsis2: pl.DataFrame,
        df_sepsis3: pl.DataFrame,
        factor_col: str,
        criterion_col: str,
        top_n: int = 20,
    ):
        """
        For each factor value, count how many encounters are POA vs NPOA
        (ignoring severity suffix) under the given criterion.

        Rows = factor values (e.g., ED Admission, Direct Admission)
        Columns = POA count, NPOA count, POA %, NPOA %
        """
        billing_col = self.basic_analyusis_config.billing_sepsis_col
        encounter_col = self.basic_analyusis_config.encounter_col

        # --- Step 1: Select, concat, deduplicate ---
        required_cols = [
            encounter_col,
            criterion_col,
            billing_col,
            factor_col,
        ]

        dfs = []
        for df in [df_sepsis1, df_sepsis2, df_sepsis3]:
            dfs.append(df.select(required_cols))

        df_all = pl.concat(dfs)

        # Deduplicate: one row per encounter, keep last (highest severity)
        df_all = df_all.sort(criterion_col).group_by(encounter_col).last()

        # --- Step 2: Extract POA/NPOA prefix ---
        df_all = df_all.with_columns(
            pl.col(criterion_col).str.split("-").list.first().alias("pipeline_group"),
            pl.col(billing_col).str.split("-").list.first().alias("billing_group"),
        )

        # --- Step 3: Group low-frequency factor values ---
        top_values = (
            df_all
            .group_by(factor_col)
            .len()
            .sort("len", descending=True)
            .head(top_n)
            [factor_col]
            .to_list()
        )

        df_all = df_all.with_columns(
            pl.when(pl.col(factor_col).is_in(top_values))
            .then(pl.col(factor_col))
            .otherwise(pl.lit("Other"))
            .alias("factor_grouped")
        )

        # --- Step 4: Count per (factor_value, group) for pipeline and billing ---
        def _build_table(df, group_col, label):
            ct = (
                df
                .group_by(["factor_grouped", group_col])
                .len()
                .pivot(on=group_col, index="factor_grouped", values="len")
                .fill_null(0)
            )

            for g in ["POA", "NPOA", "UPOA"]:
                if g not in ct.columns:
                    ct = ct.with_columns(pl.lit(0).alias(g))

            total = pl.sum_horizontal(["POA", "NPOA", "UPOA"]).alias("N")
            ct = ct.with_columns(total)

            ct = ct.with_columns(
                (pl.col("POA") / pl.col("N") * 100).round(1).alias(f"{label} POA %"),
                (pl.col("NPOA") / pl.col("N") * 100).round(1).alias(f"{label} NPOA %"),
            )

            ct = ct.rename({
                "POA": f"{label} POA",
                "NPOA": f"{label} NPOA",
            })

            return ct.select([
                "factor_grouped", "N",
                f"{label} POA", f"{label} POA %",
                f"{label} NPOA", f"{label} NPOA %",
            ])

        pipeline_table = _build_table(df_all, "pipeline_group", "Pipeline")
        billing_table = _build_table(df_all, "billing_group", "Billing")

        # --- Step 5: Join pipeline and billing tables ---
        result = pipeline_table.join(
            billing_table.drop("N"),
            on="factor_grouped",
            how="left",
        )

        result = (
            result
            .sort("N", descending=True)
            .rename({"factor_grouped": factor_col})
        )

        return result


    def _poa_rate_by_factor_1(
        self,
        df_sepsis1: pl.DataFrame,
        df_sepsis2: pl.DataFrame,
        df_sepsis3: pl.DataFrame,
        factor_col: str,
        top_n: int = 20,
    ):
        billing_col = self.basic_analyusis_config.billing_sepsis_col
        encounter_col = self.basic_analyusis_config.encounter_col
        criteria = self.basic_analyusis_config.poa_config.time_columns
        criterion_cols = [f"POA_Criteria_{col}" for col in criteria]

        # --- Step 1: Select common columns needed ---
        common_cols = [
            encounter_col,
            billing_col,
            factor_col,
        ] + criterion_cols

        df1 = df_sepsis1.select([c for c in common_cols if c in df_sepsis1.columns])
        df2 = df_sepsis2.select([c for c in common_cols if c in df_sepsis2.columns])
        df3 = df_sepsis3.select([c for c in common_cols if c in df_sepsis3.columns])

        # --- Step 2: Merge with max severity per criterion ---
        first_col = criteria[0]
        df_merged = self._merge_poas(df1, df2, df3, first_col)

        for col in criteria[1:]:
            df_col = self._merge_poas(df1, df2, df3, col)
            df_col = df_col.select([
                encounter_col,
                f"POA_Criteria_{col}",
            ])
            df_merged = df_merged.join(
                df_col,
                on=encounter_col,
                how="left",
            )

        # --- Step 3: Group low-frequency factor values ---
        top_values = (
            df_merged
            .group_by(factor_col)
            .len()
            .sort("len", descending=True)
            .head(top_n)
            [factor_col]
            .to_list()
        )

        df_merged = df_merged.with_columns(
            pl.when(pl.col(factor_col).is_in(top_values))
            .then(pl.col(factor_col))
            .otherwise(pl.lit("Other"))
            .alias("factor_grouped")
        )

        # --- Step 4: Compute POA rate per factor value per criterion ---
        all_poa_cols = criterion_cols + [billing_col]
        all_poa_labels = criteria + ["Billing"]

        totals = (
            df_merged
            .group_by("factor_grouped")
            .len()
            .rename({"len": "N"})
        )

        result = totals.clone()

        for poa_col, label in zip(all_poa_cols, all_poa_labels):
            poa_counts = (
                df_merged
                .filter(pl.col(poa_col).str.starts_with("POA"))
                .group_by("factor_grouped")
                .len()
                .rename({"len": f"{label}_poa_count"})
            )

            result = result.join(poa_counts, on="factor_grouped", how="left")
            result = result.with_columns(
                pl.col(f"{label}_poa_count").fill_null(0)
            )

            result = result.with_columns(
                (
                    (pl.col(f"{label}_poa_count") / pl.col("N") * 100).round(1).cast(pl.Utf8)
                    + pl.lit("% (n=")
                    + pl.col(f"{label}_poa_count").cast(pl.Utf8)
                    + pl.lit(")")
                ).alias(label)
            ).drop(f"{label}_poa_count")

        # --- Step 5: Clean up and sort ---
        result = (
            result
            .select(["factor_grouped", "N"] + all_poa_labels)
            .sort("N", descending=True)
            .rename({"factor_grouped": factor_col})
        )

        return result

    def plot_poa_rate_by_factor_1(self, result_df: pl.DataFrame, factor_col: str) -> go.Figure:
        """
        Visualizes the POA rate table produced by _poa_rate_by_factor().

        Args:
            result_df: Polars DataFrame with columns:
                    [factor_col, 'N', 'Arrival_Instant', 'FirstAdmissionOrderInstant',
                        'InpatientAdmissionInstant', 'Billing']
            factor_col: The name of the grouping column (e.g. 'AdmissionOrigin')

        Returns:
            A Plotly Figure (grouped bar chart)
        """
        import re

        # --- Step 1: Identify which columns are criterion columns ---
        # Everything except the factor and N columns
        skip_cols = {factor_col, "N"}
        criterion_cols = [c for c in result_df.columns if c not in skip_cols]

        # --- Step 2: Parse "XX.X% (n=YYYY)" strings into floats ---
        # We'll build a dict: { criterion_label -> list of (pct, n, raw_string) }
        def parse_pct_string(s: str):
            """Extracts percentage and count from strings like '92.6% (n=2935)'"""
            match = re.match(r"([\d.]+)%\s*\(n=([\d]+)\)", s)
            if match:
                return float(match.group(1)), int(match.group(2))
            return 0.0, 0  # fallback for malformed entries

        # --- Step 3: Extract axis labels and total N ---
        # Convert to pandas for easier row iteration (or stay in polars — your choice)
        df = result_df.to_pandas()

        x_labels = df[factor_col].tolist()          # e.g. ['ED Admission', 'Transfer Center...']
        n_totals = df["N"].tolist()                  # e.g. [3170, 385, ...]

        # x-axis tick labels: include N so the reader knows the denominator
        x_display = [f"{label}<br><sub>N={n}</sub>" for label, n in zip(x_labels, n_totals)]

        # --- Step 4: Build one Bar trace per criterion column ---
        # Color palette — one color per criterion
        colors = ["#4C78A8", "#F58518", "#54A24B", "#B279A2"]

        traces = []
        for i, col in enumerate(criterion_cols):
            pcts = []
            hover_texts = []

            for raw_val in df[col]:
                pct, n = parse_pct_string(str(raw_val))
                pcts.append(pct)
                hover_texts.append(f"{col}<br>{raw_val}")  # e.g. "Billing<br>87.5% (n=2773)"

            trace = go.Bar(
                name=col,                      # Legend label
                x=x_display,                  # Grouped x-axis
                y=pcts,                        # Bar height = percentage
                text=[f"{p}%" for p in pcts], # Label on top of each bar
                textposition="outside",
                hovertext=hover_texts,
                hoverinfo="x+text",           # Show x label + our custom hover
                marker_color=colors[i % len(colors)],
            )
            traces.append(trace)

        # --- Step 5: Build the figure ---
        fig = go.Figure(data=traces)

        fig.update_layout(
            barmode="group",                   # Side-by-side bars
            title=f"POA Rate by {factor_col}",
            xaxis_title=factor_col,
            yaxis_title="POA Rate (%)",
            yaxis=dict(range=[0, 115]),        # Give headroom for "outside" text labels
            legend_title="Criterion",
            template="plotly_white",
            height=550,
            bargap=0.2,                        # Gap between groups
            bargroupgap=0.05,                  # Gap within a group
        )

        return fig


    def plot_poa_rate_by_factor(self, result_df: pl.DataFrame, factor_col: str) -> go.Figure:
        """
        Visualizes POA rate table as a faceted bar chart — one subplot per admission origin.
        Each subplot shows the 4 criteria as bars, making within-group patterns clear.
        """

        # --- Step 1: Parse "XX.X% (n=YYYY)" → (float, int) ---
        import re
        def parse_pct_string(s: str):
            match = re.match(r"([\d.]+)%\s*\(n=([\d]+)\)", str(s))
            if match:
                return float(match.group(1)), int(match.group(2))
            return 0.0, 0

        # --- Step 2: Identify criterion columns ---
        skip_cols = {factor_col, "N"}
        criterion_cols = [c for c in result_df.columns if c not in skip_cols]

        df = result_df.to_pandas()

        # --- Step 3: Build subplot grid ---
        # Filter out "Other" group with all zeros to keep chart clean
        df = df[df["N"] > 0].reset_index(drop=True)

        n_groups = len(df)
        n_cols = 3                                      # 3 subplots per row
        n_rows = (n_groups + n_cols - 1) // n_cols      # ceiling division

        # Shorten long criterion names for x-axis readability inside small subplots
        label_map = {
            "Arrival_Instant": "Arrival",
            "FirstAdmissionOrderInstant": "First Order",
            "InpatientAdmissionInstant": "Inpatient",
            "Billing": "Billing",
        }
        short_labels = [label_map.get(c, c) for c in criterion_cols]

        colors = ["#4C78A8", "#F58518", "#54A24B", "#B279A2"]

        # --- Step 4: Create subplots ---
        fig = make_subplots(
            rows=n_rows,
            cols=n_cols,
            subplot_titles=[
                f"{row[factor_col]}<br><sup>N={row['N']}</sup>"
                for _, row in df.iterrows()
            ],
            shared_yaxes=True,      # Same y-scale across all subplots — critical for comparison
            vertical_spacing=0.18,
            horizontal_spacing=0.06,
        )

        # --- Step 5: Add bars for each origin group ---
        for i, (_, row) in enumerate(df.iterrows()):
            subplot_row = i // n_cols + 1
            subplot_col = i % n_cols + 1

            pcts = []
            hover_texts = []
            bar_colors = []

            for j, col in enumerate(criterion_cols):
                pct, n = parse_pct_string(row[col])
                pcts.append(pct)
                hover_texts.append(f"<b>{col}</b><br>POA Rate: {pct}%<br>n={n} / N={row['N']}")
                bar_colors.append(colors[j % len(colors)])

            fig.add_trace(
                go.Bar(
                    x=short_labels,
                    y=pcts,
                    marker_color=bar_colors,
                    text=[f"{p}%" for p in pcts],
                    textposition="outside",
                    textfont=dict(size=10),
                    hovertext=hover_texts,
                    hoverinfo="text",
                    showlegend=(i == 0),    # Only show legend once (from first subplot)
                    name="",                # We'll add manual legend below
                ),
                row=subplot_row,
                col=subplot_col,
            )

        # --- Step 6: Add a clean manual legend using invisible scatter traces ---
        for j, (col, color) in enumerate(zip(criterion_cols, colors)):
            fig.add_trace(
                go.Bar(
                    x=[None], y=[None],
                    name=label_map.get(col, col),
                    marker_color=color,
                    showlegend=True,
                )
            )

        # --- Step 7: Layout polish ---
        fig.update_layout(
            title=dict(
                text=f"POA Capture Rate by {factor_col}",
                font=dict(size=16),
            ),
            yaxis=dict(range=[0, 120]),     # Headroom for "outside" text labels
            template="plotly_white",
            height=280 * n_rows,
            showlegend=True,
            legend=dict(
                title="Criterion",
                orientation="h",
                y=-0.08,                    # Below the chart
                x=0.5,
                xanchor="center",
            ),
            bargap=0.25,
        )

        # Apply shared y-axis range to all subplots
        for i in range(1, n_rows * n_cols + 1):
            fig.update_layout(**{f"yaxis{i if i > 1 else ''}": dict(range=[0, 120])})

        return fig


    def analyze(self):
        # Combine 3 spesis1, 2, 3
        # Get the earliest instance 
        # Label NPOA v POA
        df_poa1 = self._detect_POA1()
        df_poa2 = self._detect_POA2()
        df_poa3 = self._detect_POA3()

        colname = self.basic_analyusis_config.poa_config.time_columns[0]
        label = 'arrival'
        df_times = self._get_time_from_arrival_to_first_sepsis([df_poa1, df_poa2, df_poa3], col_name=colname,
                                                                period_hrs=self.basic_analyusis_config.poa_config.period_constraints[colname],
                                                                label="arrival")
        # Usage
        fig_billing = self.plot_time_to_sepsis_by_score(df_times, time_col=f"hours_{label}_to_first_sepsis", sepsis_col="Sepsis_Category")
        fig_pipeline = self.plot_time_to_sepsis_by_score(df_times, time_col=f"hours_{label}_to_first_sepsis", sepsis_col="sepsis_score")
        # fig_billing.show()
        # fig_pipeline.show()
        # fig.write_html("sepsis_poa_report.html")
        # fig.write_image("sepsis_poa_report.png", scale=2)
        # x = 0
        # df_poa1 = self._filter_cofounding_factors(df_poa1)
        # df_poa2 = self._filter_cofounding_factors(df_poa2)
        # df_poa3 = self._filter_cofounding_factors(df_poa3)

        # df_analyze = self._analyze_factor_simple(df_poa1, df_poa2, df_poa3, factor_col=self.basic_analyusis_config.categorical_factors[0],
        #                                           criterion_col=f"POA_Criteria_{self.basic_analyusis_config.poa_config.time_columns[0]}")

        # df_analyze_match = self._analyze_factor_match_simple(df_poa1, df_poa2, df_poa3, factor_col=self.basic_analyusis_config.categorical_factors[0],
        #                                           criterion_col=f"POA_Criteria_{self.basic_analyusis_config.poa_config.time_columns[0]}")

        # df_poa = self._poa_rate_by_factor(df_poa1, df_poa2, df_poa3, factor_col=self.basic_analyusis_config.categorical_factors[0], top_n=10)
        # fig = self.plot_poa_rate_by_factor(df_poa, factor_col="AdmissionOrigin")
        # fig.show()

        results_display, results_raw = self._analyze_billing_vs_calculated(df_poa1, df_poa2, df_poa3)
        old_keys = list(results_display.keys())
        for key in old_keys:
            results_raw[f'{key} + {self.basic_analyusis_config.poa_config.period_constraints[key]} hours'] = results_raw[key]
        for k in old_keys:
            del results_raw[k] 
        
        figures_heat = self._plot_billing_vs_calculated_heatmap(results_raw, 'col')
        figures_distr = self._plot_calculated_vs_billed_distribution(results_raw, False, "category")

        for c in self.basic_analyusis_config.poa_config.time_columns:
            analysis2_cols = [self.basic_analyusis_config.encounter_col]+self.basic_analyusis_config.categorical_factors+self.basic_analyusis_config.binary_factors+[self.basic_analyusis_config.billing_sepsis_col]+[f"POA_Criteria_{c}"]
        
            df_poa1_analysis2 = df_poa1.select(analysis2_cols)
            df_poa2_analysis2 = df_poa2.select(analysis2_cols)
            df_poa3_analysis2 = df_poa3.select(analysis2_cols)

            df_poaall_analysis2 = self._merge_poas(df_poa1_analysis2, df_poa2_analysis2, df_poa3_analysis2, c, 'max')
            df_poaall_analysis2.with_columns(
                pl.col() - pl.col(c) 
            )
            x=0

        results1 = self._factor_analysis_npoa3(df_poaall_analysis2, f"POA_Criteria_{self.basic_analyusis_config.poa_config.time_columns[0]}")
        results2 = self._factor_analysis_npoa3(df_poaall_analysis2, f"POA_Criteria_{self.basic_analyusis_config.poa_config.time_columns[1]}")
        results3 = self._factor_analysis_npoa3(df_poaall_analysis2, f"POA_Criteria_{self.basic_analyusis_config.poa_config.time_columns[2]}")
        x = 0
        
        
    def save_data(self, df: pl.DataFrame, filename: str):
        file_path = self.data_dir / filename
        df.write_csv(file_path)

