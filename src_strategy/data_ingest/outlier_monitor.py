from pathlib import Path

import polars as pl

from src_strategy.configs.dataconfig import (
    BloodPressureConfig,
    DataConfig,
    DataInputOutputConfig,
)
from src_strategy.configs.outlierdetection.extremeoutliers import (
    BloodPressureBoundsConfig,
    FlowsheetBoundsConfig,
    LabBoundsConfig,
)


class OutlierMonitor:
    """Write outlier audit artifacts and validate cleaned analytic values."""

    def __init__(
        self,
        input_output_config: DataInputOutputConfig,
        data_config: DataConfig,
        bp_config: BloodPressureConfig,
        flowsheet_bounds_config: FlowsheetBoundsConfig,
        lab_bounds_config: LabBoundsConfig,
        bp_bounds_config: BloodPressureBoundsConfig,
        logger,
    ) -> None:
        self.input_output_config = input_output_config
        self.data_config = data_config
        self.bp_config = bp_config
        self.flowsheet_bounds_config = flowsheet_bounds_config
        self.lab_bounds_config = lab_bounds_config
        self.bp_bounds_config = bp_bounds_config
        self.logger = logger

    @property
    def output_path(self) -> Path:
        return Path(self.input_output_config.meta_outlier_path)

    def record_detected(
        self,
        flowsheets: pl.DataFrame,
        labs: pl.DataFrame,
    ) -> None:
        """Persist detected BP, flowsheet, and lab outliers before cleaning."""
        self._record_bp_outliers(flowsheets)
        self._record_flowsheet_outliers(flowsheets)
        self._record_lab_outliers(labs)

    def validate_cleaned(
        self,
        flowsheets: pl.DataFrame,
        labs: pl.DataFrame,
    ) -> None:
        """Record unexplained differences between source and analytic values."""
        self._record_bp_mismatches(flowsheets)
        self._record_flowsheet_mismatches(flowsheets)
        self._record_lab_mismatches(labs)

    def _record_bp_outliers(self, flowsheets: pl.DataFrame) -> None:
        for column in self.bp_bounds_config.thresholds:
            flag_col = f"{column}_is_outlier"
            flowsheets.filter(pl.col(flag_col)).select(
                self.data_config.base_cols + [column, flag_col]
            ).write_csv(self.output_path / f"bp_outliers_{column}.csv")

        bounds = {
            column: [config.lower_bound, config.upper_bound]
            for column, config in self.bp_bounds_config.thresholds.items()
        }
        bounds["key"] = ["lower_bound", "upper_bound"]
        pl.DataFrame(bounds).write_csv(self.output_path / "bp_bounds.csv")

    def _record_flowsheet_outliers(self, flowsheets: pl.DataFrame) -> None:
        holders = {
            bounds.outlier_holder
            for bounds in self.flowsheet_bounds_config.thresholds.values()
        }
        flowsheets.filter(pl.col("flowsheet_outlier").is_in(holders)).select(
            self.data_config.base_cols + ["flowsheet_outlier"]
        ).write_csv(self.output_path / "flowsheet_outliers.csv")

        bounds = {
            column: [
                config.lower_bound,
                config.upper_bound,
                config.outlier_holder,
            ]
            for column, config in self.flowsheet_bounds_config.thresholds.items()
        }
        bounds["key"] = ["lower_bound", "upper_bound", "outlier_holder"]
        pl.DataFrame(bounds).write_csv(self.output_path / "flowsheet_bounds.csv")

    def _record_lab_outliers(self, labs: pl.DataFrame) -> None:
        holders = {
            bounds.outlier_holder
            for bounds in self.lab_bounds_config.thresholds.values()
        }
        labs.filter(pl.col("lab_outlier").is_in(holders)).select(
            self.data_config.base_cols + ["lab_outlier"]
        ).write_csv(self.output_path / "lab_outliers.csv")

        bounds = {
            column: [
                config.lower_bound,
                config.upper_bound,
                config.outlier_holder,
            ]
            for column, config in self.lab_bounds_config.thresholds.items()
        }
        bounds["key"] = ["lower_bound", "upper_bound", "outlier_holder"]
        pl.DataFrame(bounds).write_csv(self.output_path / "labs_bounds.csv")

    def _record_flowsheet_mismatches(self, flowsheets: pl.DataFrame) -> None:
        holders = {
            bounds.outlier_holder
            for bounds in self.flowsheet_bounds_config.thresholds.values()
        }
        analytic_col = f"{self.data_config.val_col}_flowsheet"
        mismatches = flowsheets.filter(
            pl.col(self.data_config.val_col).is_not_null()
            & pl.col(analytic_col).is_null()
            & (~pl.col("flowsheet_outlier").is_in(holders))
        ).select(
            self.data_config.base_cols + [analytic_col, "flowsheet_outlier"]
        )

        if len(mismatches) > 0:
            message = (
                f"There are {len(mismatches)} mismatches between flowsheets "
                "outlier column and original value columns "
            )
            self.logger.info(message)
            mismatches.write_csv(self.output_path / "flowsheet_mismatch.csv")
            raise ValueError(message)

    def _record_lab_mismatches(self, labs: pl.DataFrame) -> None:
        holders = {
            bounds.outlier_holder
            for bounds in self.lab_bounds_config.thresholds.values()
        }
        analytic_col = f"{self.data_config.val_col}_labs"
        mismatches = labs.filter(
            pl.col(self.data_config.val_col).is_not_null()
            & pl.col(analytic_col).is_null()
            & (~pl.col("lab_outlier").is_in(holders))
        ).select(self.data_config.base_cols + [analytic_col, "lab_outlier"])

        if len(mismatches) > 0:
            message = (
                f"There are {len(mismatches)} mismatches between lab outlier "
                "column and original value columns "
            )
            self.logger.info(message)
            mismatches.write_csv(self.output_path / "labs_mismatch.csv")
            raise ValueError(message)

    def _record_bp_mismatches(self, flowsheets: pl.DataFrame) -> None:
        sys_col = self.bp_config.sys_col
        dia_col = self.bp_config.dia_col
        map_col = self.bp_config.map_col
        sys_temp_col = f"{sys_col}_temp"
        dia_temp_col = f"{dia_col}_temp"
        map_temp_col = f"{map_col}_temp"
        sys_flag_col = f"{sys_col}_is_outlier"
        dia_flag_col = f"{dia_col}_is_outlier"
        map_flag_col = f"{map_col}_is_outlier"

        bp_row = (
            pl.col(self.data_config.grouper_col) == self.bp_config.bp_grouper_val
        )
        invalid_bp_pair = bp_row & (
            pl.col(sys_col).is_null()
            | pl.col(dia_col).is_null()
            | pl.col(sys_flag_col)
            | pl.col(dia_flag_col)
        )

        sys_mismatches = flowsheets.filter(
            bp_row
            & (
                (invalid_bp_pair & pl.col(sys_temp_col).is_not_null())
                | ((~invalid_bp_pair) & (pl.col(sys_temp_col) != pl.col(sys_col)))
            )
        ).select(
            self.data_config.base_cols
            + [sys_temp_col, sys_col, sys_flag_col, dia_flag_col]
        )
        if len(sys_mismatches) > 0:
            self.logger.info(
                f"There are {len(sys_mismatches)} systolic blood pressure "
                "mismatch between outlier column and original value column"
            )
            sys_mismatches.write_csv(
                self.output_path / "bp_outlier_sys_mismatch.csv"
            )

        dia_mismatches = flowsheets.filter(
            bp_row
            & (
                (invalid_bp_pair & pl.col(dia_temp_col).is_not_null())
                | ((~invalid_bp_pair) & (pl.col(dia_temp_col) != pl.col(dia_col)))
            )
        ).select(
            self.data_config.base_cols
            + [dia_temp_col, dia_col, sys_flag_col, dia_flag_col]
        )
        if len(dia_mismatches) > 0:
            self.logger.info(
                f"There are {len(dia_mismatches)} diastolic blood pressure "
                "mismatch between outlier column and original value column"
            )
            dia_mismatches.write_csv(
                self.output_path / "bp_outlier_dia_mismatch.csv"
            )

        map_row = (
            pl.col(self.data_config.grouper_col) == self.bp_config.map_event_grouper
        )
        invalid_map = pl.col(map_col).is_null() | pl.col(map_flag_col)
        unexpected_map_source = (~map_row) & (
            pl.col(map_col).is_not_null() | pl.col(map_temp_col).is_not_null()
        )
        map_mismatches = flowsheets.filter(
            unexpected_map_source
            | (
                map_row
                & (
                    (invalid_map & pl.col(map_temp_col).is_not_null())
                    | ((~invalid_map) & (pl.col(map_temp_col) != pl.col(map_col)))
                )
            )
        ).select(
            self.data_config.base_cols + [map_temp_col, map_col, map_flag_col]
        )
        if len(map_mismatches) > 0:
            self.logger.info(
                f"There are {len(map_mismatches)} mean arterial blood pressure "
                "mismatch between outlier column and original value column"
            )
            map_mismatches.write_csv(
                self.output_path / "bp_outlier_map_mismatch.csv"
            )
