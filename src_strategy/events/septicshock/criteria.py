"""Strategy implementations for the five septic-shock criteria."""

from datetime import timedelta

import polars as pl

from ...configs.aggregator import FEATURE_REGISTRY, FeatureColumn
from ...configs.septicshock import SepticShockConfig
from ...pipeline import Criterion


def _require_columns(available: set[str], required: set[str], label: str) -> None:
    missing = sorted(required.difference(available))
    if missing:
        raise ValueError(f"{label} input is missing required columns: {missing}")


def _nullable_numeric_flag(
    evidence_missing: pl.Expr,
    condition: pl.Expr,
    output_col: str,
) -> pl.Expr:
    return (
        pl.when(evidence_missing)
        .then(pl.lit(None, dtype=pl.Int8))
        .when(condition)
        .then(pl.lit(1, dtype=pl.Int8))
        .otherwise(pl.lit(0, dtype=pl.Int8))
        .alias(output_col)
    )


def _feature_context(
    config: SepticShockConfig,
    feature_col: FeatureColumn,
    available: set[str],
    label: str,
) -> tuple[str, pl.Expr]:
    definition = FEATURE_REGISTRY[feature_col]
    if definition.lookback_period is None:
        raise ValueError(f"{label} feature requires a validity period")

    input_col = feature_col.value
    source_col = f"{definition.alias}_source_ts"
    _require_columns(
        available,
        {config.event_dt_col, input_col, source_col},
        label,
    )
    # Clinical-definition validity is half-open. At the exact expiration
    # instant, the source measurement no longer supports a shock flag even if
    # an older saved aggregate still carries the boundary value.
    evidence_missing = (
        pl.col(input_col).is_null()
        | pl.col(source_col).is_null()
        | (
            pl.col(config.event_dt_col)
            >= pl.col(source_col)
            + pl.lit(timedelta(minutes=definition.lookback_period))
        )
    )
    return input_col, evidence_missing


class SBP90Criterion(Criterion):
    """Shock evidence from most-recent valid SBP below 90 mmHg."""

    config: SepticShockConfig

    @property
    def flag_col(self) -> str:
        return self.config.sbp90_criteria.flag_col

    def expressions(self, available: set[str]) -> list[pl.Expr]:
        criterion = self.config.sbp90_criteria
        input_col, evidence_missing = _feature_context(
            self.config,
            criterion.sbp_col,
            available,
            "SBP <90 septic-shock",
        )
        return [
            _nullable_numeric_flag(
                evidence_missing,
                pl.col(input_col) < criterion.sbp_threshold,
                self.flag_col,
            )
        ]


class SBPDelta40Criterion(Criterion):
    """Shock evidence from baseline SBP minus current SBP above 40 mmHg."""

    config: SepticShockConfig

    @property
    def flag_col(self) -> str:
        return self.config.sbpdelta40_criteria.flag_col

    def expressions(self, available: set[str]) -> list[pl.Expr]:
        criterion = self.config.sbpdelta40_criteria
        sbp_col, evidence_missing = _feature_context(
            self.config,
            criterion.sbp_col,
            available,
            "SBP decline septic-shock",
        )
        baseline_col = criterion.baseline_sbp_col.value
        _require_columns(
            available,
            {baseline_col},
            "SBP decline septic-shock",
        )
        return [
            pl.when(
                evidence_missing | pl.col(baseline_col).is_null()
            )
            .then(pl.lit(None, dtype=pl.Int8))
            .when(
                (pl.col(baseline_col) - pl.col(sbp_col))
                > criterion.sbp_delta_threshold
            )
            .then(pl.lit(1, dtype=pl.Int8))
            .otherwise(pl.lit(0, dtype=pl.Int8))
            .alias(self.flag_col)
        ]


class MAP65Criterion(Criterion):
    """Shock evidence from most-recent valid measured MAP below 65 mmHg."""

    config: SepticShockConfig

    @property
    def flag_col(self) -> str:
        return self.config.map65_criteria.flag_col

    def expressions(self, available: set[str]) -> list[pl.Expr]:
        criterion = self.config.map65_criteria
        input_col, evidence_missing = _feature_context(
            self.config,
            criterion.map_col,
            available,
            "MAP <65 septic-shock",
        )
        return [
            _nullable_numeric_flag(
                evidence_missing,
                pl.col(input_col) < criterion.map_threshold,
                self.flag_col,
            )
        ]


class Lactate4Criterion(Criterion):
    """Shock evidence from most-recent valid lactate above 4 mmol/L."""

    config: SepticShockConfig

    @property
    def flag_col(self) -> str:
        return self.config.lactate4_criteria.flag_col

    def expressions(self, available: set[str]) -> list[pl.Expr]:
        criterion = self.config.lactate4_criteria
        input_col, evidence_missing = _feature_context(
            self.config,
            criterion.lactate_col,
            available,
            "Lactate >4 septic-shock",
        )
        return [
            _nullable_numeric_flag(
                evidence_missing,
                pl.col(input_col) > criterion.lactate_threshold,
                self.flag_col,
            )
        ]


class VasopressorCriterion(Criterion):
    """Shock evidence from a qualifying administered vasopressor dose."""

    config: SepticShockConfig

    @property
    def flag_col(self) -> str:
        return self.config.vasopressor_criteria.flag_col

    def expressions(self, available: set[str]) -> list[pl.Expr]:
        input_col = self.config.vasopressor_criteria.administered_flag_col
        _require_columns(available, {input_col}, "Vasopressor septic-shock")
        return [
            pl.when(pl.col(input_col) == 1)
            .then(pl.lit(1, dtype=pl.Int8))
            .otherwise(pl.lit(0, dtype=pl.Int8))
            .alias(self.flag_col)
        ]


class EffectiveHypotensionCriterion(Criterion):
    """Shock contribution from duration-filtered hypotension."""

    config: SepticShockConfig

    @property
    def flag_col(self) -> str:
        return self.config.effective_hypotension_flag_col

    def expressions(self, available: set[str]) -> list[pl.Expr]:
        input_col = self.config.effective_hypotension_flag_col
        _require_columns(available, {input_col}, "Effective hypotension")
        # The effective flag is prepared from the existing BP episode filter.
        # Preserve unknown evidence while validating the known states.
        return [
            pl.when(pl.col(input_col).is_null())
            .then(pl.lit(None, dtype=pl.Int8))
            .when(pl.col(input_col) == 1)
            .then(pl.lit(1, dtype=pl.Int8))
            .when(pl.col(input_col) == 0)
            .then(pl.lit(0, dtype=pl.Int8))
            .otherwise(pl.lit(None, dtype=pl.Int8))
            .alias(self.flag_col)
        ]
