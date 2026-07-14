import polars as pl
import duckdb
import os
from pathlib import Path
from src_strategy.utils.logger import get_logger
from .transformers import (Transform, TransformPipeline, CastColumns,
                           ExtractSysDia, ApplyBounds, SysDiaAnomalies)

from src_strategy.configs.dataconfig import DataInputOutputConfig, DataConfig, BloodPressureConfig

from src_strategy.configs.outlierdetection.extremeoutliers import (
    FlowsheetBoundsConfig, LabBoundsConfig
    )


logger = get_logger(__name__)

class DataLoader:
    def __init__(self, input_output_dataconfig: DataInputOutputConfig,
                  data_config: DataConfig, bp_config: BloodPressureConfig,
                  physiological_bounds_config: FlowsheetBoundsConfig = None,
                  lab_bounds_config: LabBoundsConfig = None):
        self.input_output_dataconfig = input_output_dataconfig
        self.data_config = data_config
        self.bp_config = bp_config
        self.physiological_bounds_config = physiological_bounds_config
        self.lab_bounds_config = lab_bounds_config

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
        flowsheets_pipeline = [CastColumns(schema), ExtractSysDia(self.bp_config)]
        if self.physiological_bounds_config:
            flowsheets_pipeline.append(ApplyBounds(self.physiological_bounds_config,
                                                   outliers_replace_value=-1, outlier_column_name="flowsheet_outlier"))
            expr_sys = pl.col(self.bp_config.sys_col)
            expr_dia = pl.col(self.bp_config.dia_col)
            expr_map = pl.col()
            flowsheets_pipeline.append(SysDiaAnomalies(
                pl.when(pl.col(self.bp_config.sys_col)<=pl.col(self.bp_config.dia_col))
            ))
        
        labs_pipeline = [CastColumns(schema)]
        if self.lab_bounds_config:
            labs_pipeline.append(ApplyBounds(self.lab_bounds_config, outliers_replace_value=-1, outlier_column_name="lab_outlier"))
        return {
            "flowsheets": TransformPipeline(flowsheets_pipeline),
            "labs": TransformPipeline(labs_pipeline),
            "meds": TransformPipeline([CastColumns(schema)]),
            "procedures": TransformPipeline([CastColumns(schema)]),
            "diagnoses": TransformPipeline([CastColumns(schema)]),
            "encounters": TransformPipeline([CastColumns(schema)]),
        }
    
    def _transactional_data_summary(self, df: pl.DataFrame) -> None:
        data_config = self.data_config
        n_encounters = df[data_config.encounter_col].n_unique()
        n_event_groupers = df[data_config.grouper_col].n_unique()
        if n_event_groupers <= 10:
            grouper_counts = df[data_config.grouper_col].value_counts(sort=True)

        n_types = df[data_config.type_col].n_unique()      
        if n_types <= 10:
            type_counts = df[data_config.type_col].value_counts(sort=True)
        
        n_event_names = df[data_config.event_name_col].n_unique()
        if n_event_names <= 10:
            event_name_counts = df[data_config.event_name_col].value_counts(sort=True)
        
        n_rawval_nulls = df[data_config.raw_val_col].is_null().sum() 
        n_val_nulls = df[data_config.val_col].is_null().sum() 

        nulls_per_groupers = df.group_by(data_config.grouper_col).agg(
            pl.col(data_config.raw_col_val).is_null().sum().alias(f"{data_config.raw_col_val}_nulls"),
            pl.col(data_config.val_col).is_null().sum().alias(f"{data_config.val_col}_nulls")
        )
        nulls_per_type = df.group_by(data_config.type_col).agg(
            pl.col(data_config.raw_col_val).is_null().sum().alias(f"{data_config.raw_col_val}_nulls"),
            pl.col(data_config.val_col).is_null().sum().alias(f"{data_config.val_col}_nulls")
        )
        nulls_per_ev_name = df.group_by(data_config.event_name_col).agg(
            pl.col(data_config.raw_col_val).is_null().sum().alias(f"{data_config.raw_col_val}_nulls"),
            pl.col(data_config.val_col).is_null().sum().alias(f"{data_config.val_col}_nulls")
        )

        
    def _encounter_data_summary(self, df: pl.DataFrame) -> None:
        data_config = self.data_config 
        n_encounters = df[data_config.encounter_col].n_unique()
        assert n_encounters == len(df), f"Number of encounters ({n_encounters}) is not equal to number of rows ({len(df)}) in the encounter table."
        baseline_null_counts = {}
        for c in [c for c in df.columns if c.startswith('Baseline_')]:
            baseline_null_counts[c] = df[c].null_count()

        yn_counts = {}
        for c in [c for c in df.columns if c.endswith('_YN')]:
            yn_counts[c] = df[c].sum()/len(df)


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

        transforms = self._define_transformation_pipelines()
        logger.info(f"Running transformation pipelines on the loaded data ...")
        logger.info('-'*50)
        logger.info(f"Transforming Flowsheets ...")
        flowsheets_preprocess = transforms['flowsheets'].run(flowsheets, logger)
        logger.info(f"Transforming Labs ...")
        labs_preprocess = transforms['labs'].run(lab_res, logger)
        logger.info(f"Transforming Meds ...")
        meds = transforms['meds'].run(med_admin, logger)
        logger.info(f"Transforming Procedures ...")
        procedures = transforms['procedures'].run(procedures, logger)
        logger.info(f"Transforming Diagnosis ...")
        diagnosis = transforms['diagnoses'].run(diagnosis, logger)
        logger.info(f"Transforming Encounters ...")
        encounters = transforms['encounters'].run(encounters, logger)
        logger.info('-'*50)
        logger.info('-'*50)
        

        logger.info("Data type casting completed.")
        df_all = pl.concat([
            lab_res, procedures, med_admin, flowsheets, diagnosis
        ], how='vertical')

        df_all = df_all.join(
            encounters,
            on='EncounterEpicCsn',
            how='outer'
        )
        logger.info(f"Concatenated all data into a single DataFrame with shape {df_all.shape} and columns {df_all.columns}")
        before_drop = df_all.shape[0]
        df_all = df_all.unique()
        after_drop = df_all.shape[0]
        logger.info(f"Dropped duplicate rows. Before: {before_drop}, After: {after_drop}, Dropped: {before_drop - after_drop}")

        logger.info("Filtering out rows with null EncounterEpicCsn or Event_DateTime")
        self.df_all = df_all.filter(
            pl.col("EncounterEpicCsn").is_not_null() & pl.col("Event_DateTime").is_not_null()
        )
        logger.info(f"After filtering, df_all has shape {self.df_all.shape}")
        
        # self.df_all = self._set_vasopressors_flags(self.df_all)
        return self.df_all
    
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