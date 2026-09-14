"""Pulmonary dysfunction criterion strategies."""

import polars as pl

from ...configs.pulmonarydysfunction import PulmonaryDysfunctionConfig
from ...pipeline import Criterion


def _require_columns(
    available: set[str],
    required: set[str],
    criterion_name: str,
) -> None:
    missing = sorted(required.difference(available))
    if missing:
        raise ValueError(
            f"{criterion_name} input is missing required columns: {missing}"
        )


class VentDocumentationStartCriterion(Criterion):
    config: PulmonaryDysfunctionConfig

    @property
    def flag_col(self) -> str:
        return self.config.vent_documentation.start_flag_col

    def expressions(self, available: set[str]) -> list[pl.Expr]:
        grouper_col = self.config.grouper_col
        _require_columns(
            available,
            {grouper_col},
            "Vent-documentation start criterion",
        )
        return [
            (
                pl.col(grouper_col)
                == self.config.vent_documentation.start_grouper
            )
            .cast(pl.Int8)
            .alias(self.flag_col)
        ]


class VentOnOffStartCriterion(Criterion):
    config: PulmonaryDysfunctionConfig

    @property
    def flag_col(self) -> str:
        return self.config.vent_onoff.start_flag_col

    def expressions(self, available: set[str]) -> list[pl.Expr]:
        grouper_col = self.config.grouper_col
        value_col = self.config.raw_val_col
        _require_columns(
            available,
            {grouper_col, value_col},
            "Vent On/Off start criterion",
        )
        return [
            (
                (pl.col(grouper_col) == self.config.vent_onoff.grouper)
                & pl.col(value_col).is_in(self.config.vent_onoff.start_values)
            )
            .cast(pl.Int8)
            .alias(self.flag_col)
        ]


class MechanicalO2StartCriterion(Criterion):
    config: PulmonaryDysfunctionConfig

    @property
    def flag_col(self) -> str:
        return self.config.o2_delivery.start_flag_col

    def expressions(self, available: set[str]) -> list[pl.Expr]:
        grouper_col = self.config.grouper_col
        value_col = self.config.raw_val_col
        _require_columns(
            available,
            {grouper_col, value_col},
            "Mechanical-O2 start criterion",
        )
        return [
            (
                (
                    pl.col(grouper_col)
                    == self.config.o2_delivery.mechanical_grouper
                )
                & pl.col(value_col).is_in(
                    self.config.o2_delivery.mechanical_start_values
                )
            )
            .cast(pl.Int8)
            .alias(self.flag_col)
        ]


class PFRatioStartCriterion(Criterion):
    config: PulmonaryDysfunctionConfig

    @property
    def flag_col(self) -> str:
        return self.config.pf.start_flag_col

    def expressions(self, available: set[str]) -> list[pl.Expr]:
        pf = self.config.pf
        _require_columns(
            available,
            {pf.pf_ratio_col, pf.pair_status_col},
            "P/F-ratio start criterion",
        )
        return [
            pl.when(
                (pl.col(pf.pair_status_col) != pf.paired_status)
                | pl.col(pf.pf_ratio_col).is_null()
            )
            .then(pl.lit(None, dtype=pl.Int8))
            .otherwise(
                (pl.col(pf.pf_ratio_col) < pf.threshold).cast(pl.Int8)
            )
            .alias(self.flag_col)
        ]


class VentDocumentationTerminationCriterion(Criterion):
    config: PulmonaryDysfunctionConfig

    @property
    def flag_col(self) -> str:
        return self.config.vent_documentation.termination_flag_col

    def expressions(self, available: set[str]) -> list[pl.Expr]:
        grouper_col = self.config.grouper_col
        _require_columns(
            available,
            {grouper_col},
            "Vent-documentation termination criterion",
        )
        return [
            (
                pl.col(grouper_col)
                == self.config.vent_documentation.termination_grouper
            )
            .cast(pl.Int8)
            .alias(self.flag_col)
        ]


class VentOnOffTerminationCriterion(Criterion):
    config: PulmonaryDysfunctionConfig

    @property
    def flag_col(self) -> str:
        return self.config.vent_onoff.termination_flag_col

    def expressions(self, available: set[str]) -> list[pl.Expr]:
        grouper_col = self.config.grouper_col
        value_col = self.config.raw_val_col
        vent = self.config.vent_onoff
        _require_columns(
            available,
            {grouper_col, value_col},
            "Vent On/Off termination criterion",
        )
        termination_value = pl.col(value_col).is_in(vent.termination_values)
        if vent.null_value_terminates:
            termination_value = termination_value | pl.col(value_col).is_null()
        return [
            (
                (pl.col(grouper_col) == vent.grouper)
                & termination_value
            )
            .cast(pl.Int8)
            .alias(self.flag_col)
        ]


class O2DeliveryTerminationCriterion(Criterion):
    config: PulmonaryDysfunctionConfig

    @property
    def flag_col(self) -> str:
        return self.config.o2_delivery.termination_flag_col

    def expressions(self, available: set[str]) -> list[pl.Expr]:
        grouper_col = self.config.grouper_col
        _require_columns(
            available,
            {grouper_col},
            "O2-delivery termination criterion",
        )
        return [
            pl.col(grouper_col)
            .is_in(self.config.o2_delivery.termination_groupers)
            .cast(pl.Int8)
            .alias(self.flag_col)
        ]


class PFRatioTerminationCriterion(Criterion):
    config: PulmonaryDysfunctionConfig

    @property
    def flag_col(self) -> str:
        return self.config.pf.termination_flag_col

    def expressions(self, available: set[str]) -> list[pl.Expr]:
        pf = self.config.pf
        _require_columns(
            available,
            {pf.pf_ratio_col, pf.pair_status_col},
            "P/F-ratio termination criterion",
        )
        return [
            pl.when(
                (pl.col(pf.pair_status_col) != pf.paired_status)
                | pl.col(pf.pf_ratio_col).is_null()
            )
            .then(pl.lit(None, dtype=pl.Int8))
            .otherwise(
                (pl.col(pf.pf_ratio_col) > pf.threshold).cast(pl.Int8)
            )
            .alias(self.flag_col)
        ]
