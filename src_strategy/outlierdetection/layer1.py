import polars as pl

# from src_strategy.configs.outlierdetection.layer1 import Layer1Config
from ..configs.outlierdetection.extremeoutliers import PhysiologicalBoundsConfig
from typing import List 

class Layer1PhysiologicalBound:
    def __init__(self, config: PhysiologicalBoundsConfig, sort_by:None|str|List[str]=None):
        self.config = config
        self.sort_by = sort_by
    
    def apply(self, df: pl.DataFrame,
              outliers_replace_value:float|str=None,
              outlier_column_name:str=None,
              inplace=False):
        if inplace:
            df_clone = df
        else:
            df_clone = df.clone()
        
        if self.sort_by is not None:
            df_clone = df_clone.sort(self.sort_by)

        expr = pl.col(self.config.val_col)
        for signal, bounds in self.config.thresholds.items():   
            expr = (
                    pl.when(
                        (pl.col(self.config.grouper_col) == signal) &
                        ((pl.col(self.config.val_col) < bounds.lower_bound) |
                        (pl.col(self.config.val_col) > bounds.upper_bound))
                    )
                    .then(outliers_replace_value)
                    .otherwise(expr)
                )

        df_clone = df_clone.with_columns(
            expr.alias(self.config.val_col if outlier_column_name is None else outlier_column_name)
        )
        return df_clone
    

