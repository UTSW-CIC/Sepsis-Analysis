import polars as pl

from src.configs.outlierdetection.layer1 import Layer1Config

class Layer1PhysiologicalBound:
    def __init__(self, config: Layer1Config):
        self.config = config
    
    def apply(self, df: pl.DataFrame, inplace=False):
        if inplace:
            df_clone = df
        else:
            df_clone = df.clone()

        expr = pl.col(self.config.val_col)
        for signal, bounds in self.config.thresholds.items():   
            expr = (
                    pl.when(
                        (pl.col(self.config.grouper_col) == signal) &
                        ((pl.col(self.config.val_col) < bounds.lower_bound) |
                        (pl.col(self.config.val_col) > bounds.upper_bound))
                    )
                    .then(None)
                    .otherwise(expr)
                )

        df_clone = df_clone.with_columns(
            expr.alias(self.config.val_col)
        )
        return df_clone
    

