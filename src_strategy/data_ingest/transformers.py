from typing import Protocol, List
import polars as pl
from ..utils.utils import cast_cols, extract_sys_dia_from_flowsheets
from ..configs.dataconfig import bp_config
from ..configs.outlierdetection.extremeoutliers import flowsheet_bounds_config, lab_bounds_config, PhysiologicalBoundsConfig
from ..outlierdetection.layer1 import Layer1PhysiologicalBound

class Transform(Protocol):
    name: str
    def apply(self, df: pl.DataFrame, logger=None) -> pl.DataFrame:
        ...
    
class CastColumns:
    name = 'cast'
    def __init__(self, schema: dict): self.schema = schema
    def apply(self, df: pl.DataFrame, logger=None) -> pl.DataFrame:
        if logger:
            logger.info('casting columns ...')
        return cast_cols(df, self.schema)

class ExtractSysDia:
    name='sys_dia'
    def __init__(self, bp_config): self.bp_config = bp_config
    def apply(self, df: pl.DataFrame, logger=None):
        if logger:
            logger.info('extracting systolic and diastolic blood pressure ...')
        return extract_sys_dia_from_flowsheets(df, self.bp_config)

class SysDiaAnomalies:
    name='sys_dia_anomalies'
    def __init__(self, expr: pl.Expr):
        self.expr = expr
    def apply(self, df: pl.DataFrame, logger=None):
        df_l = df.with_columns(
            self.expr
        )
        if logger:
            logger.info('')
        return df_l

class ApplyBounds:
    name = "outliers"
    def __init__(self, bounds_config: PhysiologicalBoundsConfig,
                outliers_replace_value:float|str=None,
                outlier_column_name:str=None,
                sort_by:None|str|List[str]=None, inplace:bool=False):
        self.bounds_config = bounds_config
        self.sort_by = sort_by
        self.inplace = inplace
        self.outliers_replace_value = outliers_replace_value
        self.outlier_column_name = outlier_column_name 
    
    def count_nulls(self, df:pl.DataFrame):
        pass

    def apply(self, df:pl.DataFrame, logger=None):
        if logger:
            logger.info('applying physiological bounds ...')

        df_detected= Layer1PhysiologicalBound(self.bounds_config, self.sort_by).apply(
            df, outliers_replace_value=self.outliers_replace_value,
            outlier_column_name=self.outlier_column_name, inplace=self.inplace
        )
        return df_detected

class TransformPipeline:
    """Pipes and Filters: run an ordered, configurable list of transforms."""
    def __init__(self, transforms: List[Transform]):
        self.transforms = transforms
    def run(self, df: pl.DataFrame, logger=None) -> pl.DataFrame:
        if logger:
            logger.info(f'Applying transformations {[t.name for t in self.transforms]}...')
        for t in self.transforms:
            df = t.apply(df)
        if logger:
            logger.info('-'*50)
        return df


# per-source wiring lives in the composition root, beside build_pipelines():
# flowsheet_pipeline = TransformPipeline([
#     CastColumns(),
#     ExtractSysDia(bp_config),
#     ApplyBounds(flowsheet_bounds_config),
# ])
# lab_pipeline = TransformPipeline([CastColumns(), ApplyBounds(lab_bounds_config)])
# plain_pipeline = TransformPipeline([CastColumns()])   # meds, procedures, diagnoses