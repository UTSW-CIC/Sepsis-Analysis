import logging
from typing import Any, Mapping

import polars as pl

from ..configs.dataconfig import DataConfig


class ValidationLogger:
    """
    Generate and log non-blocking diagnostic summaries for pipeline datasets.

    The class reports descriptive information and warnings. It does not enforce
    validation rules or intentionally terminate the pipeline when expected
    columns are missing.
    """

    def __init__(
        self,
        data_config: DataConfig,
        logger: logging.Logger | None = None,
        top_n: int = 10,
    ) -> None:
        if top_n < 1:
            raise ValueError("top_n must be at least 1.")

        self.data_config = data_config
        self.logger = logger
        self.top_n = top_n

    def _emit(
        self,
        message: str,
        logger: logging.Logger | None = None,
    ) -> None:
        """Write to the supplied logger, instance logger, or stdout."""
        active_logger = logger if logger is not None else self.logger

        if active_logger is not None:
            active_logger.info(message)
        else:
            print(message)

    @staticmethod
    def _schema_as_strings(df: pl.DataFrame) -> dict[str, str]:
        """Return a serialization-friendly representation of the schema."""
        return {
            column_name: str(dtype)
            for column_name, dtype in df.schema.items()
        }

    def _group_summary(
        self,
        df: pl.DataFrame,
        group_col: str,
        value_cols: list[str],
    ) -> pl.DataFrame:
        """
        Calculate row counts and null statistics for one grouping column.

        Only value columns present in the DataFrame should be supplied.
        """
        aggregations: list[pl.Expr] = [
            pl.len().alias("n_rows"),
        ]

        for value_col in value_cols:
            aggregations.extend(
                [
                    pl.col(value_col)
                    .null_count()
                    .alias(f"{value_col}_null_count"),

                    (
                        100
                        * pl.col(value_col).null_count()
                        / pl.len()
                    )
                    .round(2)
                    .alias(f"{value_col}_null_pct"),
                ]
            )

        return (
            df.group_by(group_col)
            .agg(aggregations)
            .sort("n_rows", descending=True)
        )

    def _base_info(
        self,
        df: pl.DataFrame,
        dataset_name: str,
        logger: logging.Logger | None = None,
    ) -> dict[str, Any]:
        """
        Generate a summary for an event-level transactional DataFrame.

        Missing configured columns are reported as warnings rather than causing
        the whole summary to fail.
        """
        config = self.data_config

        configured_columns = {
            "encounter": config.encounter_col,
            "grouper": config.grouper_col,
            "type": config.type_col,
            "event_name": config.event_name_col,
            "raw_value": config.raw_val_col,
            "value": config.val_col,
        }

        missing_columns = sorted(
            {
                column_name
                for column_name in configured_columns.values()
                if column_name not in df.columns
            }
        )

        summary: dict[str, Any] = {
            "dataset_name": dataset_name,
            "shape": df.shape,
            "schema": self._schema_as_strings(df),
            "missing_columns": missing_columns,
        }

        # Calculate all scalar statistics in one select operation.
        scalar_expressions: list[pl.Expr] = [
            pl.len().alias("n_rows"),
        ]

        unique_column_specs = {
            "n_encounters": config.encounter_col,
            "n_event_groupers": config.grouper_col,
            "n_types": config.type_col,
            "n_event_names": config.event_name_col,
        }

        for metric_name, column_name in unique_column_specs.items():
            if column_name in df.columns:
                scalar_expressions.append(
                    pl.col(column_name)
                    .n_unique()
                    .alias(metric_name)
                )

        null_column_specs = {
            "n_raw_value_nulls": config.raw_val_col,
            "n_value_nulls": config.val_col,
        }

        for metric_name, column_name in null_column_specs.items():
            if column_name in df.columns:
                scalar_expressions.append(
                    pl.col(column_name)
                    .null_count()
                    .alias(metric_name)
                )

        scalar_summary = df.select(scalar_expressions).row(
            0,
            named=True,
        )
        summary.update(scalar_summary)

        existing_value_cols = [
            column_name
            for column_name in [config.raw_val_col, config.val_col]
            if column_name in df.columns
        ]

        group_specs = {
            "grouper_summary": config.grouper_col,
            "type_summary": config.type_col,
            "event_name_summary": config.event_name_col,
        }

        for summary_name, group_col in group_specs.items():
            if group_col not in df.columns:
                continue

            summary[summary_name] = self._group_summary(
                df=df,
                group_col=group_col,
                value_cols=existing_value_cols,
            )

        self._log_event_summary(summary, logger)

        return summary

    def _log_event_summary(
        self,
        summary: Mapping[str, Any],
        logger: logging.Logger | None = None,
    ) -> None:
        """Log the readable portion of an event-level summary."""
        dataset_name = summary["dataset_name"]

        self._emit(
            f"{dataset_name}: shape={summary['shape']}",
            logger,
        )

        self._emit(
            f"{dataset_name}: schema={summary['schema']}",
            logger,
        )

        scalar_metrics = [
            "n_rows",
            "n_encounters",
            "n_event_groupers",
            "n_types",
            "n_event_names",
            "n_raw_value_nulls",
            "n_value_nulls",
        ]

        scalar_text = ", ".join(
            f"{metric}={summary[metric]}"
            for metric in scalar_metrics
            if metric in summary
        )

        self._emit(
            f"{dataset_name}: {scalar_text}",
            logger,
        )

        missing_columns = summary.get("missing_columns", [])

        if missing_columns:
            self._emit(
                f"{dataset_name}: missing configured columns: "
                f"{missing_columns}",
                logger,
            )

        table_labels = {
            "grouper_summary": "event grouper",
            "type_summary": "event type",
            "event_name_summary": "event name",
        }

        for summary_key, display_name in table_labels.items():
            table = summary.get(summary_key)

            if table is not None:
                self._emit(
                    f"{dataset_name}: top {self.top_n} {display_name} "
                    f"groups:\n{table.head(self.top_n)}",
                    logger,
                )

    def log_raw_data(
        self,
        df: pl.DataFrame,
        logger: logging.Logger | None = None,
    ) -> dict[str, Any]:
        return self._base_info(
            df=df,
            dataset_name="Raw data",
            logger=logger,
        )

    def log_preprocessed_data(
        self,
        df: pl.DataFrame,
        logger: logging.Logger | None = None,
    ) -> dict[str, Any]:
        return self._base_info(
            df=df,
            dataset_name="Preprocessed data",
            logger=logger,
        )

    def log_outlier_detection(
        self,
        df: pl.DataFrame,
        outlier_cols_dict: Mapping[str, tuple[str, Any]],
        logger: logging.Logger | None = None,
    ) -> dict[str, Any]:
        """
        Compare original columns with outlier-processed columns.

        Parameters
        ----------
        outlier_cols_dict:
            Mapping of:

                original_column: (
                    processed_column,
                    outlier_value_holder,
                )
        """
        expressions: list[pl.Expr] = []
        valid_specs: list[tuple[int, str, str, Any]] = []
        warnings: list[str] = []

        for index, (
            original_col,
            (outlier_col, outlier_value_holder),
        ) in enumerate(outlier_cols_dict.items()):
            missing = [
                column_name
                for column_name in [original_col, outlier_col]
                if column_name not in df.columns
            ]

            if missing:
                warning = (
                    f"Cannot summarize {original_col}: "
                    f"missing columns {missing}"
                )
                warnings.append(warning)
                self._emit(warning, logger)
                continue

            mismatch_expression = (
                ~pl.col(original_col).eq_missing(pl.col(outlier_col))
            )

            if outlier_value_holder is None:
                outlier_expression = pl.col(outlier_col).is_null()
            else:
                outlier_expression = (
                    pl.col(outlier_col)
                    .eq(outlier_value_holder)
                    .fill_null(False)
                )

            expressions.extend(
                [
                    mismatch_expression
                    .sum()
                    .alias(f"mismatch_{index}"),

                    outlier_expression
                    .sum()
                    .alias(f"outlier_{index}"),
                ]
            )

            valid_specs.append(
                (
                    index,
                    original_col,
                    outlier_col,
                    outlier_value_holder,
                )
            )

        result: dict[str, Any] = {
            "n_rows": df.height,
            "results": {},
            "warnings": warnings,
        }

        if not expressions:
            return result

        aggregated = df.select(expressions).row(0, named=True)

        for (
            index,
            original_col,
            outlier_col,
            outlier_value_holder,
        ) in valid_specs:
            n_mismatches = int(aggregated[f"mismatch_{index}"])
            n_outliers = int(aggregated[f"outlier_{index}"])

            mismatch_pct = (
                round(100 * n_mismatches / df.height, 2)
                if df.height > 0
                else 0.0
            )

            outlier_pct = (
                round(100 * n_outliers / df.height, 2)
                if df.height > 0
                else 0.0
            )

            result["results"][original_col] = {
                "processed_col": outlier_col,
                "outlier_value_holder": outlier_value_holder,
                "n_mismatches": n_mismatches,
                "mismatch_pct": mismatch_pct,
                "n_outliers": n_outliers,
                "outlier_pct": outlier_pct,
            }

            self._emit(
                (
                    f"{original_col}: "
                    f"{n_mismatches:,} changed values "
                    f"({mismatch_pct:.2f}%), "
                    f"{n_outliers:,} outliers "
                    f"({outlier_pct:.2f}%)."
                ),
                logger,
            )

        return result

    def log_encounter_data(
        self,
        df: pl.DataFrame,
        logger: logging.Logger | None = None,
    ) -> dict[str, Any]:
        """
        Summarize a table expected to contain one row per encounter.
        """
        encounter_col = self.data_config.encounter_col

        summary: dict[str, Any] = {
            "dataset_name": "Encounter-level data",
            "shape": df.shape,
            "schema": self._schema_as_strings(df),
            "missing_columns": [],
        }

        if encounter_col in df.columns:
            encounter_stats = df.select(
                pl.len().alias("n_rows"),
                pl.col(encounter_col)
                .drop_nulls()
                .n_unique()
                .alias("n_unique_encounters"),
                pl.col(encounter_col)
                .null_count()
                .alias("n_null_encounter_ids"),
            ).row(0, named=True)

            summary.update(encounter_stats)

            n_non_null_rows = (
                encounter_stats["n_rows"]
                - encounter_stats["n_null_encounter_ids"]
            )

            summary["n_duplicate_encounter_rows"] = max(
                n_non_null_rows
                - encounter_stats["n_unique_encounters"],
                0,
            )
        else:
            summary["n_rows"] = df.height
            summary["missing_columns"].append(encounter_col)

        null_counts = (
            df.null_count().row(0, named=True)
            if df.width > 0
            else {}
        )

        null_summary = pl.DataFrame(
            {
                "column": list(null_counts.keys()),
                "null_count": list(null_counts.values()),
                "null_pct": [
                    round(100 * count / df.height, 2)
                    if df.height > 0
                    else 0.0
                    for count in null_counts.values()
                ],
            }
        ).sort(
            "null_pct",
            descending=True,
        )

        summary["null_summary"] = null_summary

        self._emit(
            f"Encounter-level data: shape={df.shape}",
            logger,
        )

        self._emit(
            f"Encounter-level data: schema={summary['schema']}",
            logger,
        )

        if encounter_col in df.columns:
            self._emit(
                (
                    "Encounter-level data: "
                    f"unique encounters="
                    f"{summary['n_unique_encounters']:,}, "
                    f"null encounter IDs="
                    f"{summary['n_null_encounter_ids']:,}, "
                    f"duplicate encounter rows="
                    f"{summary['n_duplicate_encounter_rows']:,}."
                ),
                logger,
            )
        else:
            self._emit(
                (
                    "Encounter-level data: configured encounter column "
                    f"'{encounter_col}' is missing."
                ),
                logger,
            )

        self._emit(
            (
                f"Encounter-level data: top {self.top_n} columns by "
                f"missingness:\n{null_summary.head(self.top_n)}"
            ),
            logger,
        )

        return summary