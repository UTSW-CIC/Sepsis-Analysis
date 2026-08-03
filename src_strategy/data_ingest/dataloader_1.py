import polars as pl
import duckdb
import os
from pathlib import Path
from src_strategy.utils.logger import get_logger
from .transformers import (Transform, TransformPipeline, CastColumns,
                           BloodPressureExtractor, ApplyBounds, BloodPressureBounds, PFRatioCalculator)

from src_strategy.configs.dataconfig import DataInputOutputConfig, DataConfig, BloodPressureConfig
from .bloodpressure import BloodPressureProcessor

from src_strategy.configs.outlierdetection.extremeoutliers import (
    FlowsheetBoundsConfig, LabBoundsConfig, BloodPressureBoundsConfig
    )
from ..configs.pulmonarydysfunction import PFConfig

from .data_inject_validation import ValidationLogger
from .datainject import DataInjectMonitor, SORT_BY
from typing import List, Mapping

logger = get_logger(__name__)

class DataLoader:
    def __init__(self, input_output_dataconfig: DataInputOutputConfig,
                data_config: DataConfig, bp_config: BloodPressureConfig,
                physiological_bounds_config: FlowsheetBoundsConfig = None,
                lab_bounds_config: LabBoundsConfig = None,
                bp_bounds_config: BloodPressureBoundsConfig = None, pf_config: PFConfig = None):
        self.input_output_dataconfig = input_output_dataconfig
        self.data_config = data_config
        self.bp_config = bp_config
        self.physiological_bounds_config = physiological_bounds_config
        self.lab_bounds_config = lab_bounds_config
        self.bp_bounds_config = bp_bounds_config
        self.pf_config = pf_config
        

    def _load_labs(self) -> pl.DataFrame:
        return pl.read_csv(self.input_output_dataconfig.data_path/Path(self.input_output_dataconfig.input_file_names.LABS), infer_schema=False, null_values=['Null', "NULL", 'null'])
    def _load_encounters(self) -> pl.DataFrame:
        return pl.read_csv(self.input_output_dataconfig.data_path/Path(self.input_output_dataconfig.input_file_names.ENCOUNTER_BASELINE_SCORES), infer_schema=False, null_values=['Null', "NULL", 'null'])
    def _load_meds(self) -> pl.DataFrame:
        return pl.read_csv(self.input_output_dataconfig.data_path/Path(self.input_output_dataconfig.input_file_names.MEDS), infer_schema=False, null_values=['Null', "NULL", 'null'])
    def _load_procedures(self) -> pl.DataFrame:
        return pl.read_csv(self.input_output_dataconfig.data_path/Path(self.input_output_dataconfig.input_file_names.PROCEDURES), infer_schema=False, null_values=['Null', "NULL", 'null'])
    def _load_diagnoses(self) -> pl.DataFrame:
        return pl.read_csv(self.input_output_dataconfig.data_path/Path(self.input_output_dataconfig.input_file_names.DIAGNOSIS), infer_schema=False, null_values=['Null', "NULL", 'null'])
    def _load_flowsheets(self) -> pl.DataFrame:
        return pl.read_csv(self.input_output_dataconfig.data_path/Path(self.input_output_dataconfig.input_file_names.FLOWSHEETS), infer_schema=False, null_values=['Null', "NULL", 'null'])

    def _define_transformation_pipelines(self) -> dict[Transform]:
        schema = self.input_output_dataconfig.cast_schema
        flowsheets_pipeline = [CastColumns(schema), BloodPressureExtractor(self.bp_config)]
        if self.physiological_bounds_config:
            flowsheets_pipeline.append(ApplyBounds(self.physiological_bounds_config,
                                                    outlier_column_name="flowsheet_outlier"))
            # flowsheets_pipeline.append(BloodPressureBounds(self.bp_config, self.bp_bounds_config, outliers_replace_value=-1, outlier_column_name="bp_outlier"))
            flowsheets_pipeline.append(BloodPressureBounds(self.bp_config, self.bp_bounds_config, outlier_column_name="bp_outlier"))
        
        labs_pipeline = [CastColumns(schema)]
        if self.lab_bounds_config:
            # labs_pipeline.append(ApplyBounds(self.lab_bounds_config, outliers_replace_value=-1, outlier_column_name="lab_outlier"))
            labs_pipeline.append(ApplyBounds(self.lab_bounds_config, outlier_column_name="lab_outlier"))

        if self.pf_config:
            # labs_pipeline.append(ApplyBounds(self.pf_config, outliers_replace_value=-1, outlier_column_name="pf_outlier"))
            labs_pipeline.append(PFRatioCalculator(self.pf_config))

        return {
            "flowsheets": TransformPipeline(flowsheets_pipeline),
            "labs": TransformPipeline(labs_pipeline),
            "meds": TransformPipeline([CastColumns(schema)]),
            "procedures": TransformPipeline([CastColumns(schema)]),
            "diagnoses": TransformPipeline([CastColumns(schema)]),
            "encounters": TransformPipeline([CastColumns(schema)]),
        }

    def monitor_same_instant_collision(self, df_list: List[pl.DataFrame] | Mapping[str, pl.DataFrame] | pl.DataFrame) -> bool:
        di = DataInjectMonitor(self.bp_config, self.physiological_bounds_config, self.lab_bounds_config, logger=logger)
        if isinstance(df_list, List):
            for df in df_list:
                di.summarize_same_instant_events(df,
                                                encounter_id=self.data_config.encounter_id,
                                                event_dt=self.data_config.event_dt,
                                                event_grouper_col=self.data_config.event_grouper_col)
        elif isinstance(df_list, pl.DataFrame):
            di.summarize_same_instant_events(df_list,
                                             encounter_id=self.data_config.encounter_id,
                                             event_dt=self.data_config.event_dt,
                                             event_grouper_col=self.data_config.event_grouper_col)
        elif isinstance(df_list, Mapping):
            for name, df in df_list.items():
                di.summarize_same_instant_events(df,
                                                encounter_id=self.data_config.encounter_col,
                                                event_dt=self.data_config.event_dt_col,
                                                event_grouper_col=self.data_config.grouper_col, name=name)
                                        
    def _remove_duplicates_from_df(self, df: pl.DataFrame, name:str=None, by:str=None) -> pl.DataFrame:
        if name is None:
            name = ""
        else:
            name = name + ": "

        if by is None or by.lower() == 'grouper':
            by = self.data_config.unique_subset_with_grouper        
        elif by.lower() == 'type':
            by = self.data_config.unique_subset_with_type        
        elif 'name' in by.lower():
            by = self.data_config.unique_subset_with_eventname
        elif by.lower() == 'all':
            by = self.data_config.unique_subset_with_all

        logger.info(f"{name}Removing duplicates using {by} ...")
        logger.info(f"{name}Original shape: {df.shape}")
        df = df.unique(subset=by)
        logger.info(f"{name}New shape: {df.shape}")
        return df

    def remove_duplicates(self, df_list: List[pl.DataFrame] | Mapping[str, pl.DataFrame] | pl.DataFrame, by: str=None):
        if isinstance(df_list, List):
            for idx in range(len(df_list)):
                df_list[idx] = self._remove_duplicates_from_df(df_list[idx], by=by) # Logger is available here
        elif isinstance(df_list, pl.DataFrame):
            df_list = self._remove_duplicates_from_df(df_list, by=by)
        elif isinstance(df_list, Mapping):
            for name, df in df_list.items():
                df_list[name] = self._remove_duplicates_from_df(df, name=name, by=by)
        return df_list

    def combine_all_tables(self, df_list: List[pl.DataFrame] | Mapping[str, pl.DataFrame] | pl.DataFrame) -> pl.DataFrame:
        common_cols = self.data_config.base_cols
        logger.info("Combining all tables...")
        if isinstance(df_list, List):
            df_list = [df.select(common_cols) for df in df_list]
            return pl.concat(df_list, how='vertical')
        elif isinstance(df_list, pl.DataFrame):
            return df_list.select(common_cols)
        elif isinstance(df_list, Mapping):
            df_list = {name: df.select(common_cols) for name, df in df_list.items()}
            return pl.concat(list(df_list.values()), how='vertical')

    def record_outliers_bp(self, flowsheets_preprocessed: pl.DataFrame):
        for key, bounds in self.bp_bounds_config.thresholds.items():
            flowsheets_preprocessed.filter(
                pl.col(f"bp_outlier_{key}") == bounds.outlier_holder
            ).select(
                self.data_config.base_cols + [f"bp_outlier_{key}"]
            ).write_csv(f"{self.input_output_dataconfig.meta_outlier_path}/bp_outliers_{key}.csv")
        d = {
                k: [v.lower_bound, v.upper_bound, v.outlier_holder] for k, v in self.bp_bounds_config.thresholds.items()
            }
        d.update(
                {"key":['lower_bound', 'upper_bound', 'outlier_holder']}
            )
        pl.DataFrame(
            d
        ).write_csv(f"{self.input_output_dataconfig.meta_outlier_path}/bp_bounds.csv")

    def record_outliers_flowsheets(self, flowsheets_preprocessed: pl.DataFrame):
        all_bounds = []
        for _, bounds in self.physiological_bounds_config.thresholds.items():
            all_bounds.append(bounds.outlier_holder)
        all_bounds = set(all_bounds)
        flowsheets_preprocessed.filter(
            pl.col(f"flowsheet_outlier").is_in(all_bounds)
        ).select(
            self.data_config.base_cols + [f"flowsheet_outlier"]
        ).write_csv(f"{self.input_output_dataconfig.meta_outlier_path}/flowsheet_outliers.csv")
        d = {
                k: [v.lower_bound, v.upper_bound, v.outlier_holder] for k, v in self.physiological_bounds_config.thresholds.items()
            }
        d.update(
                {"key":['lower_bound', 'upper_bound', 'outlier_holder']}
            )
        pl.DataFrame(
            d
        ).write_csv(f"{self.input_output_dataconfig.meta_outlier_path}/flowsheet_bounds.csv")

    def record_outliers_labs(self, labs_preprocessed: pl.DataFrame):
        all_bounds = []
        for _, bounds in self.lab_bounds_config.thresholds.items():
            all_bounds.append(bounds.outlier_holder)
        all_bounds = set(all_bounds)
        labs_preprocessed.filter(
            pl.col(f"lab_outlier").is_in(all_bounds)
        ).select(
            self.data_config.base_cols + [f"lab_outlier"]
        ).write_csv(f"{self.input_output_dataconfig.meta_outlier_path}/lab_outliers.csv")
        d = {
                k: [v.lower_bound, v.upper_bound, v.outlier_holder] for k, v in self.lab_bounds_config.thresholds.items()
            }
        d.update(
                {"key":['lower_bound', 'upper_bound', 'outlier_holder']}
            )
        pl.DataFrame(
            d
        ).write_csv(f"{self.input_output_dataconfig.meta_outlier_path}/labs_bounds.csv")

    def record_outliers_flowsheets_mismatch(self, flowsheets_preprocessed: pl.DataFrame):
        all_bounds = []
        for _, bounds in self.physiological_bounds_config.thresholds.items():
            all_bounds.append(bounds.outlier_holder)
        all_bounds = set(all_bounds)
        flowsheet_mismatch = flowsheets_preprocessed.filter(
            pl.col(self.data_config.val_col).is_not_null()&
            pl.col(f"{self.data_config.val_col}_flowsheet").is_null()&
            (~pl.col("flowsheet_outlier").is_in(all_bounds))
        ).select(self.data_config.base_cols+[f"{self.data_config.val_col}_flowsheet", 'flowsheet_outlier'])
        if len(flowsheet_mismatch)>0:
            logger.info(f'There are {len(flowsheet_mismatch)} mismatches between flowsheets outlier column and original value columns ')
            flowsheet_mismatch.write_csv(f"{self.input_output_dataconfig.meta_outlier_path}/flowsheet_mismatch.csv")
            raise ValueError(f'There are {len(flowsheet_mismatch)} mismatches between flowsheets outlier column and original value columns ')

    def merge_outlier_col_to_flowsheets(self, flowsheets_preprocessed: pl.DataFrame):
        all_bounds = []
        for _, bounds in self.physiological_bounds_config.thresholds.items():
            all_bounds.append(bounds.outlier_holder)
        all_bounds = set(all_bounds)
        return flowsheets_preprocessed.with_columns(
            pl.when(pl.col("flowsheet_outlier").is_in(all_bounds)).then(None).otherwise(pl.col("NumericValue")).alias("NumericValue_flowsheet")
        )

    def record_outliers_labs_mismatch(self, labs_preprocessed: pl.DataFrame):
        all_bounds = []
        for _, bounds in self.lab_bounds_config.thresholds.items():
            all_bounds.append(bounds.outlier_holder)
        all_bounds = set(all_bounds)
        lab_mismatch = labs_preprocessed.filter(
            pl.col(self.data_config.val_col).is_not_null()&
            pl.col(f"{self.data_config.val_col}_labs").is_null()&
            (~pl.col("lab_outlier").is_in(all_bounds))
        ).select(self.data_config.base_cols+[f"{self.data_config.val_col}_labs", 'lab_outlier'])
        if len(lab_mismatch)>0:
            logger.info(f'There are {len(lab_mismatch)} mismatches between lab outlier column and original value columns ')
            lab_mismatch.write_csv(f"{self.input_output_dataconfig.meta_outlier_path}/labs_mismatch.csv")
            raise ValueError(f'There are {len(lab_mismatch)} mismatches between lab outlier column and original value columns ')

    def merge_outlier_col_to_labs(self, labs_preprocessed: pl.DataFrame):
        all_bounds = []
        for _, bounds in self.lab_bounds_config.thresholds.items():
            all_bounds.append(bounds.outlier_holder)
        all_bounds = set(all_bounds)
        return labs_preprocessed.with_columns(
            pl.when(pl.col("lab_outlier").is_in(all_bounds)).then(None).otherwise(pl.col("NumericValue")).alias("NumericValue_labs")
        )

    def record_outliers_bp_mismatch(self, flowsheets_preprocessed: pl.DataFrame):
        sys_mismatch = flowsheets_preprocessed.filter(
            pl.col(self.bp_config.sys_col).is_not_null()&pl.col(f"{self.bp_config.sys_col}_temp").is_null()&(pl.col("bp_outlier_sys")!=self.bp_bounds_config.thresholds[self.bp_config.sys_col].outlier_holder)
        ).select(self.data_config.base_cols+['sys_temp', 'sys', 'bp_outlier_sys'])
        if len(sys_mismatch)>0:
            logger.info(f'There are {len(sys_mismatch)} systolic blood pressure mismatch between outlier column and original value column')
            sys_mismatch.write_csv(f"{self.input_output_dataconfig.meta_outlier_path}/bp_outlier_sys_mismatch.csv")

        dia_mismatch = flowsheets_preprocessed.filter(
            pl.col(self.bp_config.dia_col).is_not_null()&pl.col(f"{self.bp_config.dia_col}_temp").is_null()&(pl.col("bp_outlier_dia")!=self.bp_bounds_config.thresholds[self.bp_config.dia_col].outlier_holder)
        ).select(self.data_config.base_cols+['dia_temp', 'dia', 'bp_outlier_dia'])
        if len(dia_mismatch)>0:
            logger.info(f'There are {len(dia_mismatch)} diastolic blood pressure mismatch between outlier column and original value column')
            dia_mismatch.write_csv(f"{self.input_output_dataconfig.meta_outlier_path}/bp_outlier_dia_mismatch.csv")

        map_mismatch = flowsheets_preprocessed.filter(
            pl.col(self.bp_config.map_col).is_not_null()&pl.col(f"{self.bp_config.map_col}_temp").is_null()&(pl.col("bp_outlier_map")!=self.bp_bounds_config.thresholds[self.bp_config.map_col].outlier_holder)
        ).select(self.data_config.base_cols+['map_temp', 'map', 'bp_outlier_map'])
        if len(map_mismatch)>0:
            logger.info(f'There are {len(map_mismatch)} mean arterial blood pressure mismatch between outlier column and original value column')
            map_mismatch.write_csv(f"{self.input_output_dataconfig.meta_outlier_path}/bp_outlier_map_mismatch.csv")
        

    def merge_outlier_col_to_bp(self, flowsheets_preprocessed: pl.DataFrame):
        sys_col_expr = pl.col(self.bp_config.sys_col)
        flowsheets_preprocessed = flowsheets_preprocessed.with_columns(
            pl.when(pl.col("bp_outlier_sys")==self.bp_bounds_config.thresholds["sys"].outlier_holder).then(None).otherwise(sys_col_expr).alias(self.bp_config.sys_col+'_temp')
        )

        dia_col_expr = pl.col(self.bp_config.dia_col)
        flowsheets_preprocessed = flowsheets_preprocessed.with_columns(
            pl.when(pl.col("bp_outlier_dia")==self.bp_bounds_config.thresholds["dia"].outlier_holder).then(None).otherwise(dia_col_expr).alias(self.bp_config.dia_col+'_temp')
        )

        map_col_expr = pl.col(self.bp_config.map_col)
        flowsheets_preprocessed = flowsheets_preprocessed.with_columns(
            pl.when(pl.col("bp_outlier_map")==self.bp_bounds_config.thresholds["map"].outlier_holder).then(None).otherwise(map_col_expr).alias(self.bp_config.map_col+'_temp')
        )

        flowsheets_preprocessed = flowsheets_preprocessed.with_columns(
            [
                pl.when(
                    (pl.col(self.data_config.grouper_col) == self.bp_config.bp_grouper_val)&
                    pl.col(self.data_config.raw_val_col).is_not_null()&
                (pl.col(self.bp_config.sys_col+'_temp').is_null() | pl.col(self.bp_config.dia_col+'_temp').is_null() | pl.col(self.bp_config.map_col+'_temp').is_null())
                ).then(None).otherwise(pl.col(self.bp_config.sys_col+'_temp')).alias(self.bp_config.sys_col+'_temp'),
                pl.when(
                    (pl.col(self.data_config.grouper_col) == self.bp_config.bp_grouper_val)&
                    pl.col(self.data_config.raw_val_col).is_not_null()&
                (pl.col(self.bp_config.sys_col+'_temp').is_null() | pl.col(self.bp_config.dia_col+'_temp').is_null() | pl.col(self.bp_config.map_col+'_temp').is_null())
                ).then(None).otherwise(pl.col(self.bp_config.dia_col+'_temp')).alias(self.bp_config.dia_col+'_temp'),
                pl.when(
                    pl.col(self.data_config.grouper_col).is_in([self.bp_config.bp_grouper_val, self.bp_config.map_event_grouper])&
                    pl.col(self.data_config.raw_val_col).is_not_null()&
                (  (pl.col("bp_outlier_sys")==self.bp_bounds_config.thresholds['sys'].outlier_holder) |(pl.col("bp_outlier_dia")==self.bp_bounds_config.thresholds['dia'].outlier_holder) | pl.col(self.bp_config.map_col+'_temp').is_null())
                ).then(None).otherwise(pl.col(self.bp_config.map_col+'_temp')).alias(self.bp_config.map_col+'_temp'),
            ]
        )

        return flowsheets_preprocessed

    def apply_transformation(self, df_list: Mapping[str, pl.DataFrame], transform_pipeline: Mapping[str, Transform]):
        logger.info(f"Running transformation pipelines on the loaded data ...")
        logger.info('-'*50)
        for key, transformer in transform_pipeline.items():
            logger.info(f"Transforming {key} ...")
            df_list[key] = transformer.run(df_list[key])
        logger.info('-'*50)
        return df_list

    def load_data(self) -> pl.DataFrame:
        """
        Load data from the specified directory.

        Args:
            data_dir (Union[Path, str]): The directory containing the data files.
        Returns:
            pl.DataFrame: A Polars DataFrame containing the loaded data.
        """
        logger.info(f"Loading data from {self.input_output_dataconfig.data_path}")

        flowsheets = self._load_flowsheets()
        lab_res = self._load_labs()
        med_admin = self._load_meds()
        procedures = self._load_procedures()
        encounters = self._load_encounters()
        diagnosis = self._load_diagnoses()
        

        # Logger is available here, no need to log removing duplicates
        # Work only for dataframes with "Type, Event Grouper, Event_Name" . DONT APPLY IT TO ENCOUNTERS
        df_list = self.remove_duplicates(
            df_list={
                "flowsheets": flowsheets,
                "labs": lab_res,
                "meds": med_admin,
                "procedures": procedures,
                "diagnoses": diagnosis
            }, by='all'
        )

        eencounters = encounters.unique(subset=['EncounterEpicCsn'])
        assert encounters.height == eencounters.height, "Encounters dataframe has duplicates"
        encounters = eencounters
        

        di = DataInjectMonitor(
            data_config=self.data_config,
            bp_config = self.bp_config,
            physiological_bounds_config = self.physiological_bounds_config,
            lab_bounds_config = self.lab_bounds_config,
            input_output_dataconfig = self.input_output_dataconfig,
            logger = logger
        )

        transforms = self._define_transformation_pipelines()
        df_list.update({"encounters": encounters})
        df_list = self.apply_transformation(
            df_list, transforms
        )

        self.record_outliers_bp(df_list['flowsheets']) # flowsheets_preprocessed = self.merge_outlier_col_to_bp(flowsheets_preprocessed)
        self.record_outliers_flowsheets(df_list['flowsheets']) # flowsheets_preprocessed = self.merge_outlier_col_to_flowsheets(flowsheets_preprocessed)
        self.record_outliers_labs(df_list['labs']) # labs_preprocessed = self.merge_outlier_col_to_labs(labs_preprocessed)

        df_list['flowsheets'] = self.merge_outlier_col_to_bp(df_list['flowsheets'])
        self.record_outliers_bp_mismatch(df_list['flowsheets']) # flowsheets_preprocessed = self.merge_outlier_col_to_bp(flowsheets_preprocessed)
        df_list['flowsheets'] = self.merge_outlier_col_to_flowsheets(df_list['flowsheets']) # flowsheets_preprocessed = self.merge_outlier_col_to_flowsheets(flowsheets_preprocessed)
        self.record_outliers_flowsheets_mismatch(df_list['flowsheets'])
        df_list['labs'] = self.merge_outlier_col_to_labs(df_list['labs'])
        self.record_outliers_labs_mismatch(df_list['labs'])

        encounters =  df_list['encounters']
        del df_list['encounters']

        df_list['flowsheets'] = df_list['flowsheets'].with_columns(
            pl.col("NumericValue_flowsheet").alias("NumericValue")
        ).drop("NumericValue_flowsheet").with_columns(
            pl.col("sys_temp").alias("sys"),
            pl.col("dia_temp").alias("dia"),
            pl.col("map_temp").alias("map")
        ).drop(["sys_temp", "dia_temp", "map_temp"])

        df_list['labs'] = df_list['labs'].with_columns(
            pl.col("NumericValue_labs").alias("NumericValue")
        ).drop("NumericValue_labs")

        df_all = self.combine_all_tables(df_list)

        df_all = df_all.drop_nulls(subset=[self.data_config.encounter_col, self.data_config.event_dt_col, self.data_config.event_name_col])

        df_all_joined = df_all.join(
            df_list['flowsheets'].select(
                self.data_config.base_cols + [self.bp_config.sys_col, self.bp_config.dia_col, self.bp_config.map_col]
            ),
             on=[self.data_config.encounter_col, self.data_config.event_dt_col, self.data_config.event_name_col], how="left"
        ).join(
            df_list['labs'].select(
                self.data_config.base_cols + [self.pf_config.pf_ratio_col,  self.pf_config.pf_flag]
            ),
             on=[self.data_config.encounter_col, self.data_config.event_dt_col, self.data_config.event_name_col], how="left", suffix='_labs'
        )

        for c in [c for c in df_all_joined.columns if c.endswith('_right')]:
            assert df_all_joined.filter(pl.col(c)!=pl.col( '_'.join(c.split("_")[:-1]))).shape[0] == 0, f'Mismatch between {c} and {"_".join(c.split("_")[:-1])}'
        # for c in [c for c in df_all_joined.columns if c.endswith('_labs')]:
        #     assert df_all_joined.filter(pl.col(c)!=pl.col( '_'.join(c.split("_")[:-1]))).shape[0] == 0, f'Mismatch between {c} and {"_".join(c.split("_")[:-1])}'

        di.summarize_table(
            df_list['flowsheets'], "flowsheet", SORT_BY.NULL_PCT_VALUE
        )
        di.summarize_table(
            df_list['labs'], "labs", SORT_BY.NULL_PCT_VALUE
        )

        di.summarize_table(
            df_list['flowsheets'], "flowsheet", SORT_BY.N_ROWS, descending=False
        )
        di.summarize_table(
            df_list['labs'], "labs", SORT_BY.N_ROWS, descending=False
        )

        return df_all_joined.drop([c for c in df_all_joined.columns if c.endswith('_right') or c.endswith('_labs')]), encounters

        # logger.info(f"Running transformation pipelines on the loaded data ...")
        # logger.info('-'*50)
        # logger.info(f"Transforming Flowsheets ...")
        # # flowsheets_preprocessed = transforms['flowsheets'].run(df_list['flowsheets'], logger)
        # flowsheets_preprocessed = transforms['flowsheets'].run(flowsheets, logger)
        # logger.info(f"Transforming Labs ...")
        # # labs_preprocessed = transforms['labs'].run(df_list['labs'], logger)
        # labs_preprocessed = transforms['labs'].run(lab_res, logger)
        # logger.info(f"Transforming Meds ...")
        # # med_admin = transforms['meds'].run(df_list['meds'], logger)
        # med_admin = transforms['meds'].run(med_admin, logger)
        # logger.info(f"Transforming Procedures ...")
        # # procedures = transforms['procedures'].run(df_list['procedures'], logger)
        # procedures = transforms['procedures'].run(procedures, logger)
        # logger.info(f"Transforming Diagnosis ...")
        # # diagnosis = transforms['diagnoses'].run(df_list['diagnoses'], logger)
        # diagnosis = transforms['diagnoses'].run(diagnosis, logger)
        # logger.info(f"Transforming Encounters ...")
        # # encounters = transforms['encounters'].run(encounters, logger)
        # encounters = transforms['encounters'].run(encounters, logger)
        # logger.info('-'*50)
        # logger.info('-'*50)

        # self.record_outliers_bp(flowsheets_preprocessed)
        # self.record_outliers_flowsheets(flowsheets_preprocessed)
        # self.record_outliers_labs(labs_preprocessed)

        # flowsheets_preprocessed = self.merge_outlier_col_to_bp(flowsheets_preprocessed)
        # self.record_outliers_bp_mismatch(flowsheets_preprocessed)
        # flowsheets_preprocessed = self.merge_outlier_col_to_flowsheets(flowsheets_preprocessed)
        # self.record_outliers_flowsheets_mismatch(flowsheets_preprocessed)
        # labs_preprocessed = self.merge_outlier_col_to_labs(labs_preprocessed)
        # self.record_outliers_labs_mismatch(labs_preprocessed)

        #TODO: merge _temp columns with their correspondings         

        df_all = self.combine_all_tables(
            df_list={
                "flowsheets": flowsheets_preprocessed,
                "labs": labs_preprocessed,
                "meds": med_admin,
                "diagnosis": diagnosis,
                "procedure": procedures
            }
        )

        # TODO: Combine the sys, dia, map columns to the all columns
        df_all = df_all.join(
            flowsheets_preprocessed.select(
                self.data_config.base_cols+[pl.col(f'{self.bp_config.sys_col}_temp').alias(self.bp_config.sys_col), 'sys_temp',
                                            pl.col(f'{self.bp_config.dia_col}_temp').alias(self.bp_config.dia_col),
                                            pl.col(f'{self.bp_config.map_col}_temp').alias(self.bp_config.map_col)]
            ),
            how='left', on=[self.data_config.encounter_col, self.data_config.event_dt_col, self.data_config.event_name_col, self.data_config.raw_val_col]
        )

        di.compare_encounters_among_tables(
            {
                "flowsheet": flowsheets,
                "labs": lab_res,
                "meds":med_admin,
                "encounters": encounters,
                "diagnosis": diagnosis,
                "procedure": procedures
            }, show_encounters=False
        )


        return df_all
    
    def save_csv(self, output_dir: Path | str, filename: str = "infection_detection_result.csv"):
        """
        Save the full df_all DataFrame to a CSV file.

        Args:
            output_dir (Union[Path, str]): Directory where the CSV will be saved.
        
        Raises:
            ValueError: If load_data() has not been called yet.
        """
        if self.df_all is None:
            raise ValueError("No data loaded. Call load_data() before saving.")
        
        if isinstance(filename, str) and not filename.endswith(".csv"):
            filename += ".csv"
        
        logger.info(f"Saving df_all with shape {self.df_all.shape} to {output_dir}/{filename}")
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        output_path = output_dir / filename
        self.df_all.write_csv(output_path)

        logger.info(f"Finished saving data to {output_path}")