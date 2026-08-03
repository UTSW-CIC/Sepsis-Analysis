from typing import Protocol, List
import polars as pl
from ..utils.utils import (cast_cols,
                           extract_sys_dia_from_flowsheets,
                           extract_arterial_blood_pressure_mean_from_flowsheets,
                           calculate_pf_ratio)
from ..configs.dataconfig import DataConfig, BloodPressureConfig
from ..configs.pulmonarydysfunction import PFConfig
from ..configs.outlierdetection.extremeoutliers import PhysiologicalBoundsConfig
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

# class ExtractSysDia:
#     name='sys_dia'
#     def __init__(self, bp_config): self.bp_config = bp_config
#     def apply(self, df: pl.DataFrame, logger=None):
#         if logger:
#             logger.info('extracting systolic and diastolic blood pressure ...')
#         return extract_sys_dia_from_flowsheets(df, self.bp_config)

# class SysDiaAnomalies:
#     name='sys_dia_anomalies'
#     def __init__(self, expr: pl.Expr):
#         self.expr = expr
#     def apply(self, df: pl.DataFrame, logger=None):
#         df_l = df.with_columns(
#             self.expr
#         )
#         if logger:
#             logger.info('')
#         return df_l

class BloodPressureExtractor:
    name='bp'
    def __init__(self, bp_config: DataConfig):
         self.bp_config = bp_config
    def apply(self, df: pl.DataFrame, logger=None):
        if logger:
            logger.info('extracting blood pressure ...')
        df = extract_sys_dia_from_flowsheets(df, self.bp_config)
        df = extract_arterial_blood_pressure_mean_from_flowsheets(df, self.bp_config)
        return df


class PFRatioCalculator:
    name='pfratio'
    def __init__(self, pf_config: PFConfig):
        self.pf_config = pf_config
    def apply(self, df:pl.DataFrame, logger=None):
        if logger:
            logger.info('calculating calculating pf ratio ...')
        df = calculate_pf_ratio(df, self.pf_config)
        return df


class BloodPressureBounds:
    name='bp_bounds'
    def __init__(self, bp_config: BloodPressureConfig, bp_bounds_config: PhysiologicalBoundsConfig,
                # outliers_replace_value:float|str=None,
                outlier_column_name:str=None,
                 ):
        self.bp_bounds_config = bp_bounds_config
        self.bp_config = bp_config
        # self.outliers_replace_value = outliers_replace_value
        self.outlier_column_name = outlier_column_name

    def _get_sys_expr(self):
        # Detect outlier in systolic blood pressure
        expr_sys = pl.col(self.bp_config.sys_col)
        expr_sys = pl.when(
            pl.col(self.bp_config.sys_col).is_not_null()
            &
            (
                (pl.col(self.bp_config.sys_col)<self.bp_bounds_config.thresholds[self.bp_config.sys_col].lower_bound)
                |
                (pl.col(self.bp_config.sys_col)>self.bp_bounds_config.thresholds[self.bp_config.sys_col].upper_bound)
            )
            # ).then(pl.lit(self.outliers_replace_value)).otherwise(expr_sys).alias(self.outlier_column_name+'_sys')
            ).then(pl.lit(self.bp_bounds_config.thresholds[self.bp_config.sys_col].outlier_holder)).otherwise(expr_sys).alias(self.outlier_column_name+'_sys')
        return expr_sys

    def _get_dia_expr(self):
        # Detect outlier in diastolic blood pressure
        expr_dia = pl.col(self.bp_config.dia_col)
        expr_dia = pl.when(
            pl.col(self.bp_config.dia_col).is_not_null()
            &
            (
                (pl.col(self.bp_config.dia_col)<self.bp_bounds_config.thresholds[self.bp_config.dia_col].lower_bound)
                |
                (pl.col(self.bp_config.dia_col)>self.bp_bounds_config.thresholds[self.bp_config.dia_col].upper_bound)
                |
                (pl.col(self.bp_config.dia_col)>=pl.col(self.bp_config.sys_col))
            )
            # ).then(pl.lit(self.outliers_replace_value)).otherwise(expr_dia).alias(self.outlier_column_name+'_dia')
            ).then(pl.lit(self.bp_bounds_config.thresholds[self.bp_config.dia_col].outlier_holder)).otherwise(expr_dia).alias(self.outlier_column_name+'_dia')
        return expr_dia 

    def _get_map_expr(self):
        # Detect outlier in mean arterial blood pressure
        expr_map = pl.col(self.bp_config.map_col)
        expr_map = pl.when(
            pl.col(self.bp_config.map_col).is_not_null()
            &
            (
                (pl.col(self.bp_config.map_col)<self.bp_bounds_config.thresholds[self.bp_config.map_col].lower_bound)
                |
                (pl.col(self.bp_config.map_col)>self.bp_bounds_config.thresholds[self.bp_config.map_col].upper_bound)
            )
            # ).then(pl.lit(self.outliers_replace_value)).otherwise(expr_map).alias(self.outlier_column_name+'_map')
            ).then(pl.lit(self.bp_bounds_config.thresholds[self.bp_config.map_col].outlier_holder)).otherwise(expr_map).alias(self.outlier_column_name+'_map')
        return expr_map

    def apply(self, df: pl.DataFrame, logger=None):
        if logger:
            logger.info('applying blood pressure bounds ...')
        
        expr_sys = self._get_sys_expr()
        expr_dia = self._get_dia_expr()
        expr_map = self._get_map_expr()

        df_detected = df.with_columns(
            expr_sys,
            expr_dia,
            expr_map
        )
        
        return df_detected

class ApplyBounds:
    name = "outliers"
    def __init__(self, bounds_config: PhysiologicalBoundsConfig,
                outlier_column_name:str=None,
                sort_by:None|str|List[str]=None, inplace:bool=False):
        self.bounds_config = bounds_config
        self.sort_by = sort_by
        self.inplace = inplace
        self.outlier_column_name = outlier_column_name 
    
    def apply(self, df:pl.DataFrame, logger=None):
        if logger:
            logger.info('applying physiological bounds ...')

        df_detected= Layer1PhysiologicalBound(self.bounds_config, self.sort_by).apply(
            df,
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