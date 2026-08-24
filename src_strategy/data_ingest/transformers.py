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
    def __init__(self, bp_config: BloodPressureConfig, bp_bounds_config: PhysiologicalBoundsConfig):
        self.bp_bounds_config = bp_bounds_config
        self.bp_config = bp_config

    def _get_sys_expr(self):
        # Detect outlier in systolic blood pressure
        column = self.bp_config.sys_col
        bounds = self.bp_bounds_config.thresholds[column]
        return (
            pl.when(
                pl.col(column).is_not_null()
                & (
                    (pl.col(column) < bounds.lower_bound)
                    | (pl.col(column) > bounds.upper_bound)
                )
            )
            .then(pl.lit(True))
            .otherwise(pl.lit(False))
            .alias(f"{column}_is_outlier")
        )

    def _get_dia_expr(self):
        # Detect outlier in diastolic blood pressure
        dia_column = self.bp_config.dia_col
        sys_column = self.bp_config.sys_col
        bounds = self.bp_bounds_config.thresholds[dia_column]
        return (
            pl.when(
                pl.col(dia_column).is_not_null()
                & (
                    (pl.col(dia_column) < bounds.lower_bound)
                    | (pl.col(dia_column) > bounds.upper_bound)
                    | (pl.col(dia_column) >= pl.col(sys_column))
                )
            )
            .then(pl.lit(True))
            .otherwise(pl.lit(False))
            .alias(f"{dia_column}_is_outlier")
        )

    def _get_map_expr(self):
        # Detect outlier in mean arterial blood pressure
        column = self.bp_config.map_col
        bounds = self.bp_bounds_config.thresholds[column]
        return (
            pl.when(
                pl.col(column).is_not_null()
                & (
                    (pl.col(column) < bounds.lower_bound)
                    | (pl.col(column) > bounds.upper_bound)
                )
            )
            .then(pl.lit(True))
            .otherwise(pl.lit(False))
            .alias(f"{column}_is_outlier")
        )

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
