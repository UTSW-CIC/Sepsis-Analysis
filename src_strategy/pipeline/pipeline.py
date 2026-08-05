from typing import Any

import polars as pl

from .criterion import Criterion
from .reducers import Reducer


class Pipeline:
    """Run criterion strategies and delegate their composition to a reducer."""

    def __init__(
        self,
        config: Any,
        criteria: list[Criterion],
        reducer: Reducer,
    ):
        self.config = config
        self.criteria = [criterion for criterion in criteria if criterion.enabled]
        self.reducer = reducer

    def process(self, df: pl.DataFrame) -> pl.DataFrame:
        for criterion in self.criteria:
            df = criterion.prepare(df)

        available = set(df.columns)
        expressions = [
            expression
            for criterion in self.criteria
            for expression in criterion.expressions(available)
        ]
        if expressions:
            df = df.with_columns(expressions)

        positive_cols = [
            criterion.flag_col
            for criterion in self.criteria
            if criterion.role == "positive"
        ]
        termination_cols = [
            criterion.flag_col
            for criterion in self.criteria
            if criterion.role == "termination"
        ]
        if len(termination_cols) > 1:
            raise ValueError("A pipeline can have at most one termination criterion")

        termination_col = termination_cols[0] if termination_cols else None
        return self.reducer.reduce(df, positive_cols, termination_col)
