from typing import Protocol

import polars as pl


class Reducer(Protocol):
    def reduce(
        self,
        df: pl.DataFrame,
        positive_cols: list[str],
        termination_col: str | None = None,
    ) -> pl.DataFrame: ...


class SumReducer:
    """Sum positive criterion flags into a raw severity score."""

    def __init__(self, score_col: str):
        self.score_col = score_col

    def reduce(
        self,
        df: pl.DataFrame,
        positive_cols: list[str],
        termination_col: str | None = None,
    ) -> pl.DataFrame:
        score = (
            pl.sum_horizontal(
                [pl.col(column).fill_null(0) for column in positive_cols]
            )
            if positive_cols
            else pl.lit(0)
        )
        return df.with_columns(
            score.cast(pl.Int64).alias(self.score_col)
        )


class AnyReducer:
    """Return 1 when any positive criterion flag is 1, otherwise 0."""

    def __init__(self, flag_col: str):
        self.flag_col = flag_col

    def reduce(
        self,
        df: pl.DataFrame,
        positive_cols: list[str],
        termination_col: str | None = None,
    ) -> pl.DataFrame:
        any_positive = (
            pl.any_horizontal(
                [pl.col(column).fill_null(0) == 1 for column in positive_cols]
            )
            if positive_cols
            else pl.lit(False)
        )
        return df.with_columns(
            any_positive.cast(pl.Int8).alias(self.flag_col)
        )
