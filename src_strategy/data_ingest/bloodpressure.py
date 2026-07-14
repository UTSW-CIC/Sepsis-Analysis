import polars as pl
from src_strategy.configs.dataconfig import bp_config, BloodPressureConfig 
from src_strategy.configs.outlierdetection.extremeoutliers import bp_bounds_config, BloodPressureBoundsConfig
from src_strategy.utils.utils import extract_arterial_blood_pressure_mean_from_flowsheets, extract_sys_dia_from_flowsheets
from src_strategy.outlierdetection.layer1 import Layer1PhysiologicalBound

class BloodPressureProcessor:
    def __init__(self, bp_config: BloodPressureConfig, bp_bounds_config: BloodPressureBoundsConfig):
        self.bp_config = bp_config
        self.bp_bounds_config = bp_bounds_config
    
    def detect_anomalies(self, flowsheets: pl.DataFrame):


    def process(self, flowsheets: pl.DataFrame):
        flowsheets = extract_sys_dia_from_flowsheets(flowsheets, self.bp_config)
        flowsheets = extract_arterial_blood_pressure_mean_from_flowsheets(flowsheets, self.bp_config)
        expr = pl.col(self.bp_config.map_col)
        flowsheets_1 = flowsheets.with_columns(
            pl.when(pl.col(self.bp.grouper_col) == self.bp_config.map_event_grouper)
            .then(pl.col(self.bp_config.map_col)).otherwise(expr).alias(self.bp_config.map_col)
        )
        flowsheets_detected = Layer1PhysiologicalBound(self.bp_bounds_config).apply(flowsheets, outliers_replace_value=-1,
                                                               outlier_column_name="bp_outlier", inplace=True)
        return flowsheets_detected
        return flowsheets_2

    