"""Build auditable P/F ratio evidence from collision-free lab events."""

from datetime import timedelta

import polars as pl

from ..configs.pulmonarydysfunction import PFConfig, pf_config


_PAO2_ROW_ID = "_pf_pao2_row_id"
_PAIR_DISTANCE = "_pf_pair_distance"
_FIO2_IS_PRIOR = "_pf_fio2_is_prior"


class PFRatioBuilder:
    """Pair stabilized PaO2 and FiO2 measurements without changing input rows."""

    def __init__(self, config: PFConfig = pf_config):
        self.config = config

    def _output_schema(self, source_schema: pl.Schema) -> dict[str, pl.DataType]:
        config = self.config
        return {
            config.encounter_col: source_schema[config.encounter_col],
            config.pao2_value_col: pl.Float64,
            config.pao2_time_col: source_schema[config.event_dt_col],
            config.fio2_value_col: pl.Float64,
            config.fio2_fraction_col: pl.Float64,
            config.fio2_time_col: source_schema[config.event_dt_col],
            config.pf_ratio_col: pl.Float64,
            config.pf_ratio_time_col: source_schema[config.event_dt_col],
            config.pair_status_col: pl.String,
        }

    def build(self, df_events: pl.DataFrame) -> pl.DataFrame:
        """Return one auditable pairing result for each PaO2 event."""
        config = self.config
        required = {
            config.encounter_col,
            config.event_dt_col,
            config.grouper_col,
            config.val_col,
        }
        missing = sorted(required.difference(df_events.columns))
        if missing:
            raise ValueError(
                "P/F ratio input is missing required columns: "
                f"{missing}"
            )

        output_schema = self._output_schema(df_events.schema)
        relevant = df_events.filter(
            pl.col(config.grouper_col).is_in(
                [config.pao2_grouper_val, config.fio2_grouper_val]
            )
        )
        if relevant.is_empty():
            return pl.DataFrame(schema=output_schema)

        if relevant.select(
            pl.any_horizontal(
                pl.col([config.encounter_col, config.event_dt_col]).is_null()
            ).any()
        ).item():
            raise ValueError(
                "P/F ratio encounter identifiers and timestamps cannot be null"
            )

        duplicate_count = (
            relevant.group_by(
                config.encounter_col,
                config.event_dt_col,
                config.grouper_col,
            )
            .len()
            .filter(pl.col("len") > 1)
            .height
        )
        if duplicate_count:
            raise ValueError(
                "P/F ratio input must be collision-free; found "
                f"{duplicate_count} duplicate measurement keys"
            )

        pao2 = (
            relevant.filter(
                pl.col(config.grouper_col) == config.pao2_grouper_val
            )
            .with_row_index(_PAO2_ROW_ID)
            .select(
                _PAO2_ROW_ID,
                config.encounter_col,
                pl.col(config.event_dt_col).alias(config.pao2_time_col),
                pl.col(config.val_col)
                .cast(pl.Float64)
                .alias(config.pao2_value_col),
            )
        )
        if pao2.is_empty():
            return pl.DataFrame(schema=output_schema)

        fio2 = relevant.filter(
            pl.col(config.grouper_col) == config.fio2_grouper_val
        ).select(
            config.encounter_col,
            pl.col(config.event_dt_col).alias(config.fio2_time_col),
            pl.col(config.val_col)
            .cast(pl.Float64)
            .alias(config.fio2_value_col),
        )

        # Approved decision: FiO2 in (0, 1] is already a fraction; values above
        # 1 are percentages. Zero is invalid and cannot produce a P/F ratio.
        fio2 = fio2.with_columns(
            pl.when(
                (pl.col(config.fio2_value_col) > 0)
                & (pl.col(config.fio2_value_col) <= 1)
            )
            .then(pl.col(config.fio2_value_col))
            .when(pl.col(config.fio2_value_col) > 1)
            .then(pl.col(config.fio2_value_col) / 100.0)
            .otherwise(pl.lit(None, dtype=pl.Float64))
            .alias(config.fio2_fraction_col)
        ).filter(
            (pl.col(config.fio2_fraction_col) > 0)
            & (pl.col(config.fio2_fraction_col) <= 1)
        )

        candidates = pao2.select(
            _PAO2_ROW_ID,
            config.encounter_col,
            config.pao2_time_col,
        ).join(fio2, on=config.encounter_col, how="inner")

        # Approved decision: measurements exactly two hours apart qualify.
        candidates = candidates.with_columns(
            (
                pl.col(config.pao2_time_col)
                - pl.col(config.fio2_time_col)
            )
            .abs()
            .alias(_PAIR_DISTANCE)
        ).filter(
            pl.col(_PAIR_DISTANCE)
            <= pl.lit(
                timedelta(hours=config.time_window_between_pao2_fio2_hrs)
            )
        )

        # Approved decision: select the nearest FiO2 for each PaO2. When two
        # candidates are equally close, prefer the earlier available FiO2.
        selected = (
            candidates.with_columns(
                (
                    pl.col(config.fio2_time_col)
                    <= pl.col(config.pao2_time_col)
                ).alias(_FIO2_IS_PRIOR)
            )
            .sort(
                [_PAO2_ROW_ID, _PAIR_DISTANCE, _FIO2_IS_PRIOR],
                descending=[False, False, True],
            )
            .unique(subset=[_PAO2_ROW_ID], keep="first", maintain_order=True)
            .select(
                _PAO2_ROW_ID,
                config.fio2_value_col,
                config.fio2_fraction_col,
                config.fio2_time_col,
            )
        )

        paired = pao2.join(selected, on=_PAO2_ROW_ID, how="left")
        valid_pair = (
            (pl.col(config.pao2_value_col) > 0)
            & pl.col(config.fio2_fraction_col).is_not_null()
        )

        # Approved decision: the ratio becomes available only when both source
        # measurements exist, so its timestamp is the later source timestamp.
        paired = paired.with_columns(
            pl.when(valid_pair)
            .then(
                pl.col(config.pao2_value_col)
                / pl.col(config.fio2_fraction_col)
            )
            .otherwise(pl.lit(None, dtype=pl.Float64))
            .alias(config.pf_ratio_col),
            pl.when(valid_pair)
            .then(
                pl.when(
                    pl.col(config.pao2_time_col)
                    >= pl.col(config.fio2_time_col)
                )
                .then(pl.col(config.pao2_time_col))
                .otherwise(pl.col(config.fio2_time_col))
            )
            .otherwise(pl.lit(None, dtype=output_schema[config.pf_ratio_time_col]))
            .alias(config.pf_ratio_time_col),
            pl.when(
                pl.col(config.pao2_value_col).is_null()
                | (pl.col(config.pao2_value_col) <= 0)
            )
            .then(pl.lit(config.invalid_pao2_status))
            .when(pl.col(config.fio2_fraction_col).is_null())
            .then(pl.lit(config.no_valid_fio2_status))
            .otherwise(pl.lit(config.paired_status))
            .alias(config.pair_status_col),
        )

        return paired.select(output_schema.keys()).sort(
            config.encounter_col,
            config.pao2_time_col,
        )
