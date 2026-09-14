import polars as pl

from ...configs.organdysfunction import OrganDysfunctionConfig
from ...pipeline import Criterion


class CardiovascularCriterion(Criterion):
    """Cardiovascular dysfunction from the most recent valid lactate."""

    config: OrganDysfunctionConfig

    @property
    def input_col(self) -> str:
        return self.config.cardiovascular.lactate_col.value

    @property
    def flag_col(self) -> str:
        return self.config.cardiovascular.flag_col

    def expressions(self, available: set[str]) -> list[pl.Expr]:
        if self.input_col not in available:
            raise ValueError(
                "Cardiovascular dysfunction input is missing required column: "
                f"{self.input_col!r}"
            )

        return [
            pl.when(pl.col(self.input_col).is_null())
            .then(pl.lit(None, dtype=pl.Int8))
            .when(
                pl.col(self.input_col)
                > self.config.cardiovascular.lactate_threshold
            )
            .then(pl.lit(1, dtype=pl.Int8))
            .otherwise(pl.lit(0, dtype=pl.Int8))
            .alias(self.flag_col)
        ]


class PulmonaryCriterion(Criterion):
    """Expose the reconstructed pulmonary state to organ composition."""

    config: OrganDysfunctionConfig

    @property
    def input_col(self) -> str:
        return self.config.pulmonary.input_flag_col

    @property
    def flag_col(self) -> str:
        return self.config.pulmonary.flag_col

    def expressions(self, available: set[str]) -> list[pl.Expr]:
        if self.input_col not in available:
            raise ValueError(
                "Pulmonary dysfunction input is missing required column: "
                f"{self.input_col!r}"
            )

        # Pulmonary start, termination, and exclusion decisions are resolved
        # before organ composition. This strategy preserves that nullable
        # state and does not reinterpret its underlying clinical evidence.
        return [
            pl.when(pl.col(self.input_col).is_null())
            .then(pl.lit(None, dtype=pl.Int8))
            .when(pl.col(self.input_col) == 1)
            .then(pl.lit(1, dtype=pl.Int8))
            .otherwise(pl.lit(0, dtype=pl.Int8))
            .alias(self.flag_col)
        ]


class RenalCriterion(Criterion):
    """Renal dysfunction from creatinine and eGFR changes."""

    config: OrganDysfunctionConfig

    @property
    def flag_col(self) -> str:
        return self.config.renal.flag_col

    def expressions(self, available: set[str]) -> list[pl.Expr]:
        renal = self.config.renal
        creatinine_col = renal.creatinine_col.value
        egfr_col = renal.egfr_col.value
        baseline_creatinine_col = renal.baseline_creatinine_col.value
        baseline_egfr_col = renal.baseline_egfr_col.value
        required = {
            creatinine_col,
            egfr_col,
            baseline_creatinine_col,
            baseline_egfr_col,
        }
        missing = sorted(required.difference(available))
        if missing:
            raise ValueError(
                "Renal dysfunction input is missing required columns: "
                f"{missing}"
            )

        creatinine2x = (
            pl.when(
                pl.col(creatinine_col).is_null()
                | pl.col(baseline_creatinine_col).is_null()
            )
            .then(pl.lit(None, dtype=pl.Int8))
            .when(
                pl.col(creatinine_col)
                > (
                    pl.col(baseline_creatinine_col)
                    * renal.creatinine_multiplier
                )
            )
            .then(pl.lit(1, dtype=pl.Int8))
            .otherwise(pl.lit(0, dtype=pl.Int8))
        )
        creatinine_gt2_no_baseline = (
            pl.when(pl.col(creatinine_col).is_null())
            .then(pl.lit(None, dtype=pl.Int8))
            .when(
                pl.col(baseline_creatinine_col).is_null()
                & (pl.col(creatinine_col) > renal.creatinine_threshold)
            )
            .then(pl.lit(1, dtype=pl.Int8))
            .otherwise(pl.lit(0, dtype=pl.Int8))
        )
        egfr50 = (
            pl.when(
                pl.col(egfr_col).is_null()
                | pl.col(baseline_egfr_col).is_null()
            )
            .then(pl.lit(None, dtype=pl.Int8))
            .when(
                pl.col(egfr_col)
                < (pl.col(baseline_egfr_col) * renal.egfr_multiplier)
            )
            .then(pl.lit(1, dtype=pl.Int8))
            .otherwise(pl.lit(0, dtype=pl.Int8))
        )
        renal_failure = (
            pl.when(
                (creatinine2x.fill_null(0) == 1)
                | (creatinine_gt2_no_baseline.fill_null(0) == 1)
                | (egfr50.fill_null(0) == 1)
            )
            .then(pl.lit(1, dtype=pl.Int8))
            .otherwise(pl.lit(0, dtype=pl.Int8))
        )

        return [
            creatinine2x.alias(renal.creatinine2x_flag),
            creatinine_gt2_no_baseline.alias(
                renal.creatinine_gt2_no_baseline_flag
            ),
            egfr50.alias(renal.egfr50_flag),
            renal_failure.alias(renal.flag_col),
        ]


class HepaticCriterion(Criterion):
    """Hepatic dysfunction from bilirubin and its encounter baseline."""

    config: OrganDysfunctionConfig

    @property
    def flag_col(self) -> str:
        return self.config.hepatic.flag_col

    def expressions(self, available: set[str]) -> list[pl.Expr]:
        hepatic = self.config.hepatic
        bilirubin_col = hepatic.bilirubin_col.value
        baseline_bilirubin_col = hepatic.baseline_bilirubin_col.value
        required = {bilirubin_col, baseline_bilirubin_col}
        missing = sorted(required.difference(available))
        if missing:
            raise ValueError(
                "Hepatic dysfunction input is missing required columns: "
                f"{missing}"
            )

        bilirubin2x = (
            pl.when(
                pl.col(bilirubin_col).is_null()
                | pl.col(baseline_bilirubin_col).is_null()
            )
            .then(pl.lit(None, dtype=pl.Int8))
            .when(
                (pl.col(bilirubin_col) > hepatic.bilirubin_threshold)
                & (
                    pl.col(bilirubin_col)
                    > (
                        pl.col(baseline_bilirubin_col)
                        * hepatic.bilirubin_multiplier
                    )
                )
            )
            .then(pl.lit(1, dtype=pl.Int8))
            .otherwise(pl.lit(0, dtype=pl.Int8))
        )
        bilirubin_gt2_no_baseline = (
            pl.when(pl.col(bilirubin_col).is_null())
            .then(pl.lit(None, dtype=pl.Int8))
            .when(
                pl.col(baseline_bilirubin_col).is_null()
                & (pl.col(bilirubin_col) > hepatic.bilirubin_threshold)
            )
            .then(pl.lit(1, dtype=pl.Int8))
            .otherwise(pl.lit(0, dtype=pl.Int8))
        )
        hepatic_failure = (
            pl.when(
                (bilirubin2x.fill_null(0) == 1)
                | (bilirubin_gt2_no_baseline.fill_null(0) == 1)
            )
            .then(pl.lit(1, dtype=pl.Int8))
            .otherwise(pl.lit(0, dtype=pl.Int8))
        )

        return [
            bilirubin2x.alias(hepatic.bilirubin2x_flag),
            bilirubin_gt2_no_baseline.alias(
                hepatic.bilirubin_gt2_no_baseline_flag
            ),
            hepatic_failure.alias(hepatic.flag_col),
        ]


class CoagulationCriterion(Criterion):
    """Coagulation dysfunction from platelets, INR, and aPTT."""

    config: OrganDysfunctionConfig

    @property
    def flag_col(self) -> str:
        return self.config.coagulation.flag_col

    def expressions(self, available: set[str]) -> list[pl.Expr]:
        coagulation = self.config.coagulation
        platelets_col = coagulation.platelets_col.value
        inr_col = coagulation.inr_col.value
        aptt_col = coagulation.aptt_col.value
        baseline_platelets_col = coagulation.baseline_platelets_col.value
        required = {
            platelets_col,
            inr_col,
            aptt_col,
            baseline_platelets_col,
        }
        missing = sorted(required.difference(available))
        if missing:
            raise ValueError(
                "Coagulation dysfunction input is missing required columns: "
                f"{missing}"
            )

        platelets50 = (
            pl.when(
                pl.col(platelets_col).is_null()
                | pl.col(baseline_platelets_col).is_null()
            )
            .then(pl.lit(None, dtype=pl.Int8))
            .when(
                (pl.col(platelets_col) < coagulation.platelets_threshold)
                & (
                    pl.col(baseline_platelets_col)
                    > coagulation.platelets_threshold
                )
                & (
                    pl.col(platelets_col)
                    < (
                        pl.col(baseline_platelets_col)
                        * coagulation.platelets_multiplier
                    )
                )
            )
            .then(pl.lit(1, dtype=pl.Int8))
            .otherwise(pl.lit(0, dtype=pl.Int8))
        )
        platelets100_no_baseline = (
            pl.when(pl.col(platelets_col).is_null())
            .then(pl.lit(None, dtype=pl.Int8))
            .when(
                pl.col(baseline_platelets_col).is_null()
                & (pl.col(platelets_col) < coagulation.platelets_threshold)
            )
            .then(pl.lit(1, dtype=pl.Int8))
            .otherwise(pl.lit(0, dtype=pl.Int8))
        )
        inr_no_baseline = (
            pl.when(pl.col(inr_col).is_null())
            .then(pl.lit(None, dtype=pl.Int8))
            .when(
                pl.col(baseline_platelets_col).is_null()
                & (pl.col(inr_col) > coagulation.inr_threshold)
            )
            .then(pl.lit(1, dtype=pl.Int8))
            .otherwise(pl.lit(0, dtype=pl.Int8))
        )
        aptt_no_baseline = (
            pl.when(pl.col(aptt_col).is_null())
            .then(pl.lit(None, dtype=pl.Int8))
            .when(
                pl.col(baseline_platelets_col).is_null()
                & (pl.col(aptt_col) > coagulation.aptt_threshold)
            )
            .then(pl.lit(1, dtype=pl.Int8))
            .otherwise(pl.lit(0, dtype=pl.Int8))
        )
        coagulation_failure = (
            pl.when(
                (platelets50.fill_null(0) == 1)
                | (platelets100_no_baseline.fill_null(0) == 1)
                | (inr_no_baseline.fill_null(0) == 1)
                | (aptt_no_baseline.fill_null(0) == 1)
            )
            .then(pl.lit(1, dtype=pl.Int8))
            .otherwise(pl.lit(0, dtype=pl.Int8))
        )

        return [
            inr_no_baseline.alias(coagulation.inr_flag),
            aptt_no_baseline.alias(coagulation.aptt_flag),
            platelets50.alias(coagulation.platelets50_flag),
            platelets100_no_baseline.alias(coagulation.platelets100_flag),
            coagulation_failure.alias(coagulation.flag_col),
        ]


class NeurologicalCriterion(Criterion):
    """Neurological dysfunction from the most recent valid GCS."""

    config: OrganDysfunctionConfig

    @property
    def input_col(self) -> str:
        return self.config.neurological.gcs_col.value

    @property
    def flag_col(self) -> str:
        return self.config.neurological.flag_col

    def expressions(self, available: set[str]) -> list[pl.Expr]:
        if self.input_col not in available:
            raise ValueError(
                "Neurological dysfunction input is missing required column: "
                f"{self.input_col!r}"
            )

        return [
            pl.when(pl.col(self.input_col).is_null())
            .then(pl.lit(None, dtype=pl.Int8))
            .when(
                pl.col(self.input_col)
                < self.config.neurological.gcs_threshold
            )
            .then(pl.lit(1, dtype=pl.Int8))
            .otherwise(pl.lit(0, dtype=pl.Int8))
            .alias(self.flag_col)
        ]
