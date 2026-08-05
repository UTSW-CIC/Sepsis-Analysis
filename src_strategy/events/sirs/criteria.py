import polars as pl

from ...configs.sirscalculator import SIRSConfig
from ...pipeline import Criterion


class _SIRSCriterion(Criterion):
    config: SIRSConfig

    @property
    def input_col(self) -> str:
        raise NotImplementedError

    def _missing_input_expression(self) -> pl.Expr:
        return pl.lit(None, dtype=pl.Int8).alias(self.flag_col)


class TemperatureCriterion(_SIRSCriterion):
    @property
    def input_col(self) -> str:
        return self.config.temp_feature_col.value

    @property
    def flag_col(self) -> str:
        return self.config.temp_flag_col

    def expressions(self, available: set[str]) -> list[pl.Expr]:
        if self.input_col not in available:
            return [self._missing_input_expression()]
        abnormal = (
            (pl.col(self.input_col) < self.config.temp_lower_threshold)
            | (pl.col(self.input_col) > self.config.temp_upper_threshold)
        )
        return [
            pl.when(abnormal)
            .then(pl.lit(1, dtype=pl.Int8))
            .otherwise(pl.lit(None, dtype=pl.Int8))
            .alias(self.flag_col)
        ]


class HeartRateCriterion(_SIRSCriterion):
    @property
    def input_col(self) -> str:
        return self.config.hr_feature_col.value

    @property
    def flag_col(self) -> str:
        return self.config.hr_flag_col

    def expressions(self, available: set[str]) -> list[pl.Expr]:
        if self.input_col not in available:
            return [self._missing_input_expression()]
        return [
            pl.when(pl.col(self.input_col) > self.config.hr_upper_threshold)
            .then(pl.lit(1, dtype=pl.Int8))
            .otherwise(pl.lit(None, dtype=pl.Int8))
            .alias(self.flag_col)
        ]


class RespiratoryRateCriterion(_SIRSCriterion):
    @property
    def input_col(self) -> str:
        return self.config.resp_feature_col.value

    @property
    def flag_col(self) -> str:
        return self.config.resp_flag_col

    def expressions(self, available: set[str]) -> list[pl.Expr]:
        if self.input_col not in available:
            return [self._missing_input_expression()]
        return [
            pl.when(pl.col(self.input_col) > self.config.resp_upper_threshold)
            .then(pl.lit(1, dtype=pl.Int8))
            .otherwise(pl.lit(None, dtype=pl.Int8))
            .alias(self.flag_col)
        ]


class WBCCriterion(_SIRSCriterion):
    @property
    def input_col(self) -> str:
        return self.config.wbc_feature_col.value

    @property
    def flag_col(self) -> str:
        return self.config.wbc_flag_col

    def expressions(self, available: set[str]) -> list[pl.Expr]:
        if self.input_col not in available:
            return [self._missing_input_expression()]
        abnormal = (
            (pl.col(self.input_col) < self.config.wbc_lower_threshold)
            | (pl.col(self.input_col) > self.config.wbc_upper_threshold)
        )
        return [
            pl.when(abnormal)
            .then(pl.lit(1, dtype=pl.Int8))
            .otherwise(pl.lit(None, dtype=pl.Int8))
            .alias(self.flag_col)
        ]
