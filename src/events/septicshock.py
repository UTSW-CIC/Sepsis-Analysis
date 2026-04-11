import polars as pl
# from src.config import SepticShockConfig, septicshock_config
from src.utils.logger import get_logger
from src.configs.septicshock import SepticShockConfig

logger = get_logger(__name__)


class SepticShockCalculator:
    def __init__(self, df_agg: pl.DataFrame, septicshock_config: SepticShockConfig) -> None:
        self.df_agg = df_agg
        self.config = septicshock_config
    
    def _calculate_sbp90_flag(self) -> pl.Expr:
        logger.info("Calculating SBP<90 flag for septic shock criteria.")
        return (
            (pl.col(self.config.sbp90_criteria.baseline_sbp_col).is_null())&
            (pl.col(self.config.sbp90_criteria.sbp_col) < self.config.sbp90_criteria.sbp_threshold)
        ).cast(pl.Int64).alias(self.config.sbp90_criteria.flag_col)

    def _calculate_sbpdelta40_flag(self) -> pl.Expr:
        logger.info("Calculating SBP delta>40 flag for septic shock criteria.")
        logger.info('-----------------------------------------------------------------------------------')
        return (
            (pl.col(self.config.sbpdelta40_criteria.baseline_sbp_col).is_not_null())&
            ( (pl.col(self.config.sbpdelta40_criteria.baseline_sbp_col)-pl.col(self.config.sbpdelta40_criteria.sbp_col)) > self.config.sbpdelta40_criteria.sbp_delta_threshold)
        ).cast(pl.Int64).alias(self.config.sbpdelta40_criteria.flag_col)

    
    def _calculate_map65_flag(self) -> pl.Expr:
        logger.info("Calculating MAP<65 flag for septic shock criteria.")
        logger.info('-----------------------------------------------------------------------------------')
        return (
            pl.col(self.config.map65_criteria.map_col) < self.config.map65_criteria.map_threshold
        ).cast(pl.Int64).alias(self.config.map65_criteria.flag_col)
    
    def _calculate_lactate4_flag(self) -> pl.Expr:
        logger.info("Calculating lactate>4 flag for septic shock criteria.")
        logger.info('-----------------------------------------------------------------------------------')
        return (
            pl.col(self.config.lactate4_criteria.lactate_col) > self.config.lactate4_criteria.lactate_threshold
        ).cast(pl.Int64).alias(self.config.lactate4_criteria.flag_col)
    
    def _calculate_vasopressor_flag(self) -> pl.Expr:
        logger.info("Calculating vasopressor flag for septic shock criteria.")
        logger.info('-----------------------------------------------------------------------------------')
        vasopressor_exprs = [pl.col(col) > 0 for col in self.config.vasopressor_criteria.vasopressor_cols]
        return (
            pl.any_horizontal(vasopressor_exprs)
        ).cast(pl.Int64).alias(self.config.vasopressor_criteria.flag_col)

    def calculate(self) -> pl.DataFrame:
        logger.info("Calculating septic shock criteria.")
        return self.df_agg.with_columns([
            self._calculate_sbp90_flag(),
            self._calculate_sbpdelta40_flag(),
            self._calculate_map65_flag(),
            self._calculate_lactate4_flag(),
            self._calculate_vasopressor_flag()
        ]).with_columns(
            (
                (pl.col(self.config.sbp90_criteria.flag_col))|
                (pl.col(self.config.sbpdelta40_criteria.flag_col))|
                (pl.col(self.config.map65_criteria.flag_col))|
                (pl.col(self.config.lactate4_criteria.flag_col))|
                (pl.col(self.config.vasopressor_criteria.flag_col))
            ).alias(self.config.flag_col)
        ).with_columns(
            pl.col(self.config.flag_col).fill_null(0).cast(pl.Int64)
        )

