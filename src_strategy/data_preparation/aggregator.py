import polars as pl
import duckdb
from datetime import timedelta
import re

from typing import List
from ..configs.aggregator import FeatureConfig, FeatureDefinition, AggregatorConfig
from ..utils.logger import get_logger

logger = get_logger(__name__)

class Aggregator:
    def __init__(self, aggregator_config: AggregatorConfig, feature_config: FeatureConfig):
        self.aggregator_config = aggregator_config
        self.feature_config = feature_config

    def _aggregate_by_polars(self, df: pl.DataFrame):
        return df

    def _safe_identifier(self, name: str) -> str:
        """
        Validates that a string is safe to use as a SQL identifier.
        Allows only letters, digits, and underscores, and must start
        with a letter or underscore.
        """
        if not re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', name):
            raise ValueError(
                f"Unsafe SQL identifier: {name!r}. "
                f"Only alphanumeric characters and underscores are allowed."
            )
        return name

    def rolling_agg_by_duckdb(
        self,
        reference: pl.DataFrame,
        events: pl.DataFrame,        # pre-filtered, must have: encounter_col, evt_dt, evt_val
        agg_col_name: str,
        agg_func: str = "max",
        lookback_period: float | timedelta = 24.0*60,
        encounter_col: str = "EncounterEpicCsn",
        ref_dt_col: str = "Event_DateTime",      # NEW
        evt_dt_col: str = "evt_dt",              # NEW
        evt_val_col: str = "evt_val",            # NEW
    ) -> pl.DataFrame:
        """
        For each row in reference, look back `lookback_period` hours into events
        and compute the aggregate of evt_val.

        Parameters
        ----------
        reference : unique (encounter, Event_DateTime) pairs — the left table
        events : pre-filtered events with columns [encounter_col, evt_dt, evt_val]
        agg_col_name : name of the output column
        agg_func : "max", "min", or "last"
        lookback_period : hours to look back (float), or a timedelta
        encounter_col : name of the encounter ID column

        Returns
        -------
        reference with one new column added
        """
        if isinstance(lookback_period, (int, float)):
            lookback_period = timedelta(minutes=lookback_period)

        interval_str = f"{int(lookback_period.total_seconds())} seconds"

        # --- Sanitize identifiers ---
        encounter_col = self._safe_identifier(encounter_col)
        agg_col_name =self._safe_identifier(agg_col_name)
        ref_dt_col = self._safe_identifier(ref_dt_col)
        evt_dt_col = self._safe_identifier(evt_dt_col)
        evt_val_col = self._safe_identifier(evt_val_col)

        agg_map = {
            "max":   f"MAX(events_tbl.{evt_val_col})",
            "min":   f"MIN(events_tbl.{evt_val_col})",
            "mean":  f"AVG(events_tbl.{evt_val_col})",
            "sum":   f"SUM(events_tbl.{evt_val_col})",
            "count": f"COUNT(events_tbl.{evt_val_col})",
            "last":  f"LAST(events_tbl.{evt_val_col} ORDER BY events_tbl.{evt_dt_col})",
            "first": f"FIRST(events_tbl.{evt_val_col} ORDER BY events_tbl.{evt_dt_col})",
        }

        agg_expr = agg_map.get(agg_func.lower())
        if agg_expr is None:
            supported = ", ".join(sorted(agg_map.keys()))
            raise ValueError(
                f"Unknown agg_func: '{agg_func}'. Supported functions: {supported}"
            )

        with duckdb.connect() as conn:
            conn.register("reference_tbl", reference)
            conn.register("events_tbl", events)
            
            result =  conn.sql(f"""
                SELECT
                    reference_tbl.{encounter_col},
                    reference_tbl.{ref_dt_col},
                    {agg_expr} AS {agg_col_name}
                FROM reference_tbl
                LEFT JOIN events_tbl
                    ON reference_tbl.{encounter_col} = events_tbl.{encounter_col}
                    AND events_tbl.{evt_dt_col} <= reference_tbl.{ref_dt_col}
                    AND events_tbl.{evt_dt_col} >= reference_tbl.{ref_dt_col} - INTERVAL '{interval_str}'
                GROUP BY
                    reference_tbl.{encounter_col},
                    reference_tbl.{ref_dt_col}
            """).pl()
        return result

    def _prepare_event_table(self, df:pl.DataFrame, feature: FeatureDefinition):
        return df.filter(
            (pl.col(self.aggregator_config.grouper_col) == feature.event_grouper)&
            (pl.col(feature.val_col).is_not_null())
        ).select(
            self.aggregator_config.encounter_col,
            pl.col(self.aggregator_config.event_dt_col).alias(self.aggregator_config.evt_dt_col),
            pl.col(feature.val_col).alias(self.aggregator_config.evt_val_col)
        )

    def _monitor_pre_post_aggregate(self, backbone: pl.DataFrame, event: pl.DataFrame, feature: FeatureDefinition):
        agg_feat_len = backbone.filter(
            pl.col(feature.alias).is_not_null()
        ).shape[0]

        evt_len = event.filter(
            pl.col(self.aggregator_config.evt_val_col).is_not_null()
        ).shape[0]

        if evt_len == 0:
            logger.warning(f"Feature {feature.alias} has no events to aggregate. Check if the event_grouper '{feature.event_grouper}' is correct and if the input data has any events for this feature.")
            return

        logger.info(f"Feature {feature.alias} pre-aggregation: {evt_len}")
        logger.info(f"Feature {feature.alias} post-aggregation: {agg_feat_len}")
        logger.info(f"Feature {feature.alias} has {agg_feat_len/evt_len} ratio of post to pre aggregation")
        logger.info("--------------------------------------------------------------------------------")


    def _aggregate_by_duckdb(self, df: pl.DataFrame, backbone: pl.DataFrame):
        for feature in self.feature_config.rolling_metrics: 
            logger.info(f"Aggregating feature {feature.alias} using {feature.agg} over last {feature.lookback_period} minutes for events in {feature.event_grouper}")
            event = self._prepare_event_table(df, feature)
            event_with_agg = self.rolling_agg_by_duckdb(
                reference=backbone,
                events=event,
                agg_col_name=feature.alias,
                agg_func=feature.agg,
                lookback_period=feature.lookback_period,
                encounter_col=self.aggregator_config.encounter_col,
                ref_dt_col=self.aggregator_config.event_dt_col,
                evt_dt_col=self.aggregator_config.evt_dt_col,
                evt_val_col=self.aggregator_config.evt_val_col
            )
            backbone = backbone.join(event_with_agg, on=[self.aggregator_config.encounter_col, self.aggregator_config.event_dt_col],
                                      how="left")

            assert backbone.join(event, left_on=[self.aggregator_config.encounter_col, self.aggregator_config.event_dt_col], right_on=[self.aggregator_config.encounter_col, self.aggregator_config.evt_dt_col], how="inner").filter(pl.col(feature.alias)!=pl.col(self.aggregator_config.evt_val_col)).shape[0] == 0,\
            f"Aggregation failed for {feature.alias}. On joining back to original dataframe, values do not match"

            assert backbone.join(event, left_on=[self.aggregator_config.encounter_col, self.aggregator_config.event_dt_col], right_on=[self.aggregator_config.encounter_col, self.aggregator_config.evt_dt_col], how="inner").shape[0] == event.shape[0],\
            f"Aggregation failed for {feature.alias}. backbone and event tables have different number of rows after join"

            self._monitor_pre_post_aggregate(backbone, event, feature)
            logger.info(f"Feature {feature.alias} aggregated and joined. Current backbone table now has {backbone.shape[0]} rows and {backbone.shape[1]} columns.")
            logger.info("--------------------------------------------------------------------------------")

        return backbone

    def aggregate(self, df: pl.DataFrame, backbone: pl.DataFrame, engine="duckdb") -> pl.DataFrame:
        if engine == "duckdb":
            return self._aggregate_by_duckdb(df, backbone)
        elif engine == "polars":
            return self._aggregate_by_polars(df)
        return df
        