"""Pulmonary criterion registries and evidence pipelines."""

import polars as pl

from ...configs.pulmonarydysfunction import (
    PulmonaryDysfunctionConfig,
    PulmonaryStartCriterionName,
    PulmonaryTerminationCriterionName,
    pulmonary_dysfunction_config,
)
from ...pipeline import Pipeline
from .criteria import (
    MechanicalO2StartCriterion,
    PFRatioStartCriterion,
    PFRatioTerminationCriterion,
    O2DeliveryTerminationCriterion,
    VentDocumentationStartCriterion,
    VentDocumentationTerminationCriterion,
    VentOnOffStartCriterion,
    VentOnOffTerminationCriterion,
)


class _AnyPositiveReducer:
    """Combine nullable evidence flags without hiding missing evidence."""

    def __init__(self, flag_col: str):
        self.flag_col = flag_col

    def reduce(
        self,
        df: pl.DataFrame,
        positive_cols: list[str],
        termination_col: str | None = None,
    ) -> pl.DataFrame:
        any_positive = pl.any_horizontal(
            [pl.col(column) == 1 for column in positive_cols]
        )
        all_missing = pl.all_horizontal(
            [pl.col(column).is_null() for column in positive_cols]
        )
        return df.with_columns(
            pl.when(any_positive)
            .then(pl.lit(1, dtype=pl.Int8))
            .when(all_missing)
            .then(pl.lit(None, dtype=pl.Int8))
            .otherwise(pl.lit(0, dtype=pl.Int8))
            .alias(self.flag_col)
        )


RAW_START_CRITERION_REGISTRY = {
    PulmonaryStartCriterionName.VENT_DOCUMENTATION: (
        VentDocumentationStartCriterion
    ),
    PulmonaryStartCriterionName.VENT_ON_OFF: VentOnOffStartCriterion,
    PulmonaryStartCriterionName.MECHANICAL_O2: MechanicalO2StartCriterion,
}

PF_START_CRITERION_REGISTRY = {
    PulmonaryStartCriterionName.PF_RATIO: PFRatioStartCriterion,
}

RAW_TERMINATION_CRITERION_REGISTRY = {
    PulmonaryTerminationCriterionName.VENT_DOCUMENTATION: (
        VentDocumentationTerminationCriterion
    ),
    PulmonaryTerminationCriterionName.VENT_ON_OFF: (
        VentOnOffTerminationCriterion
    ),
    PulmonaryTerminationCriterionName.O2_DELIVERY: (
        O2DeliveryTerminationCriterion
    ),
}

PF_TERMINATION_CRITERION_REGISTRY = {
    # PulmonaryTerminationCriterionName.PF_RATIO: PFRatioTerminationCriterion,
}


def build_pulmonary_raw_start_pipeline(
    config: PulmonaryDysfunctionConfig = pulmonary_dysfunction_config,
) -> Pipeline:
    criteria = [
        RAW_START_CRITERION_REGISTRY[name](config)
        for name in config.selected_start
        if name in RAW_START_CRITERION_REGISTRY
    ]
    return Pipeline(config, criteria, _AnyPositiveReducer(config.start_flag_col))


def build_pulmonary_pf_start_pipeline(
    config: PulmonaryDysfunctionConfig = pulmonary_dysfunction_config,
) -> Pipeline:
    criteria = [
        PF_START_CRITERION_REGISTRY[name](config)
        for name in config.selected_start
        if name in PF_START_CRITERION_REGISTRY
    ]
    return Pipeline(config, criteria, _AnyPositiveReducer(config.start_flag_col))


def build_pulmonary_raw_termination_pipeline(
    config: PulmonaryDysfunctionConfig = pulmonary_dysfunction_config,
) -> Pipeline:
    criteria = [
        RAW_TERMINATION_CRITERION_REGISTRY[name](config)
        for name in config.selected_termination
        if name in RAW_TERMINATION_CRITERION_REGISTRY
    ]
    return Pipeline(
        config,
        criteria,
        _AnyPositiveReducer(config.termination_flag_col),
    )


def build_pulmonary_pf_termination_pipeline(
    config: PulmonaryDysfunctionConfig = pulmonary_dysfunction_config,
) -> Pipeline:
    criteria = [
        PF_TERMINATION_CRITERION_REGISTRY[name](config)
        for name in config.selected_termination
        if name in PF_TERMINATION_CRITERION_REGISTRY
    ]
    return Pipeline(
        config,
        criteria,
        _AnyPositiveReducer(config.termination_flag_col),
    )
