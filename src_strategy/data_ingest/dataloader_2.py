from pathlib import Path
from typing import Mapping

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
from src_strategy.configs.pulmonarydysfunction import PFConfig
from src_strategy.utils.logger import get_logger

from .datainject import DataInjectMonitor, SORT_BY
from .outlier_monitor import OutlierMonitor
from .transformers import (
    ApplyBounds,
    BloodPressureBounds,
    BloodPressureExtractor,
    CastColumns,
    PFRatioCalculator,
    TransformPipeline,
)

logger = get_logger(__name__)


class DataLoader:
    """Load and prepare EHR source tables for the strategy pipeline."""

    TRANSACTIONAL_SOURCES = (
        "flowsheets",
        "labs",
        "meds",
        "procedures",
        "diagnoses",
    )

    def __init__(
        self,
        input_output_dataconfig: DataInputOutputConfig,
        data_config: DataConfig,
        bp_config: BloodPressureConfig,
        physiological_bounds_config: FlowsheetBoundsConfig = None,
        lab_bounds_config: LabBoundsConfig = None,
        bp_bounds_config: BloodPressureBoundsConfig = None,
        pf_config: PFConfig = None,
    ) -> None:
        # The optional annotations match V1. The active composition currently
        # supplies every bounds config and PF config.
        self.input_output_dataconfig = input_output_dataconfig
        self.data_config = data_config
        self.bp_config = bp_config
        self.physiological_bounds_config = physiological_bounds_config
        self.lab_bounds_config = lab_bounds_config
        self.bp_bounds_config = bp_bounds_config
        self.pf_config = pf_config

    def _read_csv(self, filename: str) -> pl.DataFrame:
        input_path = Path(self.input_output_dataconfig.data_path) / filename
        return pl.read_csv(
            input_path,
            infer_schema=False,
            null_values=["Null", "NULL", "null"],
        )

    def _read_sources(self) -> dict[str, pl.DataFrame]:
        filenames = self.input_output_dataconfig.input_file_names
        return {
            "flowsheets": self._read_csv(filenames.FLOWSHEETS),
            "labs": self._read_csv(filenames.LABS),
            "meds": self._read_csv(filenames.MEDS),
            "procedures": self._read_csv(filenames.PROCEDURES),
            "diagnoses": self._read_csv(filenames.DIAGNOSIS),
            "encounters": self._read_csv(filenames.ENCOUNTER_BASELINE_SCORES),
        }

    def _deduplicate_sources(
        self,
        sources: Mapping[str, pl.DataFrame],
    ) -> dict[str, pl.DataFrame]:
        deduplicated = dict(sources)
        subset = self.data_config.unique_subset_with_all

        for name in self.TRANSACTIONAL_SOURCES:
            source = sources[name]
            logger.info(f"{name}: Removing duplicates using {subset} ...")
            logger.info(f"{name}: Original shape: {source.shape}")
            deduplicated[name] = source.unique(subset=subset)
            logger.info(f"{name}: New shape: {deduplicated[name].shape}")

        encounters = sources["encounters"]
        unique_encounters = encounters.unique(
            subset=[self.data_config.encounter_col]
        )
        assert encounters.height == unique_encounters.height, (
            "Encounters dataframe has duplicates"
        )
        deduplicated["encounters"] = unique_encounters
        return deduplicated

    def _build_transformation_pipelines(
        self,
    ) -> dict[str, TransformPipeline]:
        schema = self.input_output_dataconfig.cast_schema
        flowsheet_transforms = [
            CastColumns(schema),
            BloodPressureExtractor(self.bp_config),
        ]
        if self.physiological_bounds_config:
            flowsheet_transforms.extend(
                [
                    ApplyBounds(
                        self.physiological_bounds_config,
                        outlier_column_name="flowsheet_outlier",
                    ),
                    BloodPressureBounds(
                        self.bp_config,
                        self.bp_bounds_config,
                    ),
                ]
            )

        lab_transforms = [CastColumns(schema)]
        if self.lab_bounds_config:
            lab_transforms.append(
                ApplyBounds(
                    self.lab_bounds_config,
                    outlier_column_name="lab_outlier",
                )
            )
        if self.pf_config:
            lab_transforms.append(PFRatioCalculator(self.pf_config))

        return {
            "flowsheets": TransformPipeline(flowsheet_transforms),
            "labs": TransformPipeline(lab_transforms),
            "meds": TransformPipeline([CastColumns(schema)]),
            "procedures": TransformPipeline([CastColumns(schema)]),
            "diagnoses": TransformPipeline([CastColumns(schema)]),
            "encounters": TransformPipeline([CastColumns(schema)]),
        }

    def _transform_sources(
        self,
        sources: Mapping[str, pl.DataFrame],
    ) -> dict[str, pl.DataFrame]:
        transformed = dict(sources)
        pipelines = self._build_transformation_pipelines()

        logger.info("Running transformation pipelines on the loaded data ...")
        logger.info("-" * 50)
        for name, pipeline in pipelines.items():
            logger.info(f"Transforming {name} ...")
            transformed[name] = pipeline.run(transformed[name])
        logger.info("-" * 50)
        return transformed

    def _build_outlier_monitor(self) -> OutlierMonitor:
        return OutlierMonitor(
            input_output_config=self.input_output_dataconfig,
            data_config=self.data_config,
            bp_config=self.bp_config,
            flowsheet_bounds_config=self.physiological_bounds_config,
            lab_bounds_config=self.lab_bounds_config,
            bp_bounds_config=self.bp_bounds_config,
            logger=logger,
        )

    @staticmethod
    def _outlier_holders(bounds_config) -> set[float]:
        return {
            bounds.outlier_holder
            for bounds in bounds_config.thresholds.values()
        }

    def _clean_bp_outliers(self, flowsheets: pl.DataFrame) -> pl.DataFrame:
        sys_col = self.bp_config.sys_col
        dia_col = self.bp_config.dia_col
        map_col = self.bp_config.map_col
        invalid_bp_pair = (
            (pl.col(self.data_config.grouper_col) == self.bp_config.bp_grouper_val)
            & (
                pl.col(sys_col).is_null()
                | pl.col(dia_col).is_null()
                | pl.col(f"{sys_col}_is_outlier")
                | pl.col(f"{dia_col}_is_outlier")
            )
        )

        return flowsheets.with_columns(
            pl.when(invalid_bp_pair)
            .then(None)
            .otherwise(pl.col(sys_col))
            .alias(f"{sys_col}_temp"),
            pl.when(invalid_bp_pair)
            .then(None)
            .otherwise(pl.col(dia_col))
            .alias(f"{dia_col}_temp"),
            pl.when(pl.col(f"{map_col}_is_outlier"))
            .then(None)
            .otherwise(pl.col(map_col))
            .alias(f"{map_col}_temp"),
        )

    def _clean_flowsheet_outliers(
        self,
        flowsheets: pl.DataFrame,
    ) -> pl.DataFrame:
        holders = self._outlier_holders(self.physiological_bounds_config)
        analytic_col = f"{self.data_config.val_col}_flowsheet"
        return flowsheets.with_columns(
            pl.when(pl.col("flowsheet_outlier").is_in(holders))
            .then(None)
            .otherwise(pl.col(self.data_config.val_col))
            .alias(analytic_col)
        )

    def _clean_lab_outliers(self, labs: pl.DataFrame) -> pl.DataFrame:
        holders = self._outlier_holders(self.lab_bounds_config)
        analytic_col = f"{self.data_config.val_col}_labs"
        return labs.with_columns(
            pl.when(pl.col("lab_outlier").is_in(holders))
            .then(None)
            .otherwise(pl.col(self.data_config.val_col))
            .alias(analytic_col)
        )

    def _audit_and_clean_sources(
        self,
        sources: Mapping[str, pl.DataFrame],
    ) -> dict[str, pl.DataFrame]:
        cleaned = dict(sources)
        monitor = self._build_outlier_monitor()
        monitor.record_detected(cleaned["flowsheets"], cleaned["labs"])

        cleaned["flowsheets"] = self._clean_bp_outliers(
            cleaned["flowsheets"]
        )
        cleaned["flowsheets"] = self._clean_flowsheet_outliers(
            cleaned["flowsheets"]
        )
        cleaned["labs"] = self._clean_lab_outliers(cleaned["labs"])

        monitor.validate_cleaned(cleaned["flowsheets"], cleaned["labs"])
        return cleaned

    def _finalize_source_columns(
        self,
        sources: Mapping[str, pl.DataFrame],
    ) -> tuple[dict[str, pl.DataFrame], pl.DataFrame]:
        finalized = {
            name: frame
            for name, frame in sources.items()
            if name != "encounters"
        }
        encounters = sources["encounters"]

        sys_col = self.bp_config.sys_col
        dia_col = self.bp_config.dia_col
        map_col = self.bp_config.map_col
        flowsheet_value_col = f"{self.data_config.val_col}_flowsheet"
        finalized["flowsheets"] = (
            finalized["flowsheets"]
            .with_columns(
                pl.col(flowsheet_value_col).alias(self.data_config.val_col),
                pl.col(f"{sys_col}_temp").alias(sys_col),
                pl.col(f"{dia_col}_temp").alias(dia_col),
                pl.col(f"{map_col}_temp").alias(map_col),
            )
            .drop(
                [
                    flowsheet_value_col,
                    f"{sys_col}_temp",
                    f"{dia_col}_temp",
                    f"{map_col}_temp",
                ]
            )
        )

        lab_value_col = f"{self.data_config.val_col}_labs"
        finalized["labs"] = (
            finalized["labs"]
            .with_columns(
                pl.col(lab_value_col).alias(self.data_config.val_col)
            )
            .drop(lab_value_col)
        )
        return finalized, encounters

    def _combine_event_sources(
        self,
        sources: Mapping[str, pl.DataFrame],
    ) -> pl.DataFrame:
        logger.info("Combining all tables...")
        event_tables = [
            sources[name].select(self.data_config.base_cols)
            for name in self.TRANSACTIONAL_SOURCES
        ]
        return pl.concat(event_tables, how="vertical").drop_nulls(
            subset=[
                self.data_config.encounter_col,
                self.data_config.event_dt_col,
                self.data_config.event_name_col,
            ]
        )

    def _attach_source_features(
        self,
        events: pl.DataFrame,
        sources: Mapping[str, pl.DataFrame],
    ) -> pl.DataFrame:
        join_keys = [
            self.data_config.encounter_col,
            self.data_config.event_dt_col,
            self.data_config.event_name_col,
        ]
        events = events.join(
            sources["flowsheets"].select(
                self.data_config.base_cols
                + [
                    self.bp_config.sys_col,
                    self.bp_config.dia_col,
                    self.bp_config.map_col,
                ]
            ),
            on=join_keys,
            how="left",
        ).join(
            sources["labs"].select(
                self.data_config.base_cols
                + [self.pf_config.pf_ratio_col, self.pf_config.pf_flag]
            ),
            on=join_keys,
            how="left",
            suffix="_labs",
        )

        for duplicate_col in [
            column for column in events.columns if column.endswith("_right")
        ]:
            original_col = "_".join(duplicate_col.split("_")[:-1])
            assert events.filter(
                pl.col(duplicate_col) != pl.col(original_col)
            ).height == 0, (
                f"Mismatch between {duplicate_col} and {original_col}"
            )

        return events.drop(
            [
                column
                for column in events.columns
                if column.endswith("_right") or column.endswith("_labs")
            ]
        )

    def _summarize_sources(
        self,
        sources: Mapping[str, pl.DataFrame],
    ) -> None:
        monitor = DataInjectMonitor(
            data_config=self.data_config,
            bp_config=self.bp_config,
            physiological_bounds_config=self.physiological_bounds_config,
            lab_bounds_config=self.lab_bounds_config,
            input_output_dataconfig=self.input_output_dataconfig,
            logger=logger,
        )
        for sort_by, descending in (
            (SORT_BY.NULL_PCT_VALUE, True),
            (SORT_BY.N_ROWS, False),
        ):
            monitor.summarize_table(
                sources["flowsheets"],
                "flowsheet",
                sort_by,
                descending=descending,
            )
            monitor.summarize_table(
                sources["labs"],
                "labs",
                sort_by,
                descending=descending,
            )

    def load_data(self) -> tuple[pl.DataFrame, pl.DataFrame]:
        """Return the unified event table and the encounter baseline table."""
        logger.info(
            f"Loading data from {self.input_output_dataconfig.data_path}"
        )
        sources = self._read_sources()
        sources = self._deduplicate_sources(sources)
        sources = self._transform_sources(sources)
        sources = self._audit_and_clean_sources(sources)
        sources, encounters = self._finalize_source_columns(sources)

        events = self._combine_event_sources(sources)
        events = self._attach_source_features(events, sources)
        self._summarize_sources(sources)
        return events, encounters
