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
        agg_func : "max", "min", "mean", "sum", "count", "last", or "first"
        lookback_period : hours to look back (float), or a timedelta
        encounter_col : name of the encounter ID column

        Returns
        -------
        Reference keys with the aggregate and ``<agg_col_name>_source_ts``.
        For row-selecting aggregates, the timestamp identifies the selected
        source row. Max/min ties select the most recent row. For multi-event
        aggregates, it is the latest contributing timestamp, accompanied by
        ``<agg_col_name>_contributor_count``.
        """
        if isinstance(lookback_period, (int, float)):
            lookback_period = timedelta(minutes=lookback_period)

        interval_str = f"{int(lookback_period.total_seconds())} seconds"

        # --- Sanitize identifiers ---
        encounter_col = self._safe_identifier(encounter_col)
        agg_col_name = self._safe_identifier(agg_col_name)
        source_ts_col = self._safe_identifier(f"{agg_col_name}_source_ts")
        contributor_count_col = self._safe_identifier(
            f"{agg_col_name}_contributor_count"
        )
        ref_dt_col = self._safe_identifier(ref_dt_col)
        evt_dt_col = self._safe_identifier(evt_dt_col)
        evt_val_col = self._safe_identifier(evt_val_col)

        event_value = f"events_tbl.{evt_val_col}"
        event_time = f"events_tbl.{evt_dt_col}"
        non_null_filter = f"FILTER (WHERE {event_value} IS NOT NULL)"
        agg_map = {
            "max": (
                f"FIRST({event_value} ORDER BY {event_value} DESC NULLS LAST, "
                f"{event_time} DESC) {non_null_filter}",
                f"FIRST({event_time} ORDER BY {event_value} DESC NULLS LAST, "
                f"{event_time} DESC) {non_null_filter}",
            ),
            "min": (
                f"FIRST({event_value} ORDER BY {event_value} ASC NULLS LAST, "
                f"{event_time} DESC) {non_null_filter}",
                f"FIRST({event_time} ORDER BY {event_value} ASC NULLS LAST, "
                f"{event_time} DESC) {non_null_filter}",
            ),
            "mean": (
                f"AVG({event_value})",
                f"MAX({event_time}) {non_null_filter}",
            ),
            "sum": (
                f"SUM({event_value})",
                f"MAX({event_time}) {non_null_filter}",
            ),
            "count": (
                f"COUNT({event_value})",
                f"MAX({event_time}) {non_null_filter}",
            ),
            "last": (
                f"FIRST({event_value} ORDER BY {event_time} DESC) "
                f"{non_null_filter}",
                f"MAX({event_time}) {non_null_filter}",
            ),
            "first": (
                f"FIRST({event_value} ORDER BY {event_time} ASC) "
                f"{non_null_filter}",
                f"MIN({event_time}) {non_null_filter}",
            ),
        }

        normalized_agg_func = agg_func.lower()
        agg_expressions = agg_map.get(normalized_agg_func)
        if agg_expressions is None:
            supported = ", ".join(sorted(agg_map.keys()))
            raise ValueError(
                f"Unknown agg_func: '{agg_func}'. Supported functions: {supported}"
            )
        agg_expr, source_ts_expr = agg_expressions

        contributor_count_select = ""
        if normalized_agg_func in {"mean", "sum", "count"}:
            contributor_count_select = (
                f", COUNT({event_value}) AS {contributor_count_col}"
            )

        with duckdb.connect() as conn:
            conn.register("reference_tbl", reference)
            conn.register("events_tbl", events)
            
            result =  conn.sql(f"""
                SELECT
                    reference_tbl.{encounter_col},
                    reference_tbl.{ref_dt_col},
                    {agg_expr} AS {agg_col_name},
                    {source_ts_expr} AS {source_ts_col}
                    {contributor_count_select}
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

    def rolling_flag_by_duckdb(
        self,
        reference: pl.DataFrame,
        events: pl.DataFrame,
        agg_col_name: str,
        flag_true_values: List[str] | None = None,
        flag_false_values: List[str] | None = None,
        termination_events: pl.DataFrame | None = None,
        lookback_period: float | timedelta | None = None,
        encounter_col: str = "EncounterEpicCsn",
        ref_dt_col: str = "Event_DateTime",
        evt_dt_col: str = "evt_dt",
        evt_val_col: str = "evt_val",
    ) -> pl.DataFrame:
        """Calculate a persistent boolean state at each reference row.

        A null-valued event sets the flag to 1 because the presence of its
        grouper is evidence that the event occurred. Explicitly configured
        true and false values remain supported. When no true values are
        configured, any main-grouper event not explicitly false sets the flag.
        When a lookback period is provided, only events inside that inclusive
        window contribute and a true state clears when its evidence expires.
        Without a lookback period, all prior encounter events contribute, so
        the state persists until a false/termination event or encounter end.

        Same-instant true/false collisions are expected to be resolved before
        this method is called. If one remains, false wins defensively.

        The result contains the reference keys, ``agg_col_name``, and
        ``<agg_col_name>_last_set_ts`` for evidence tracing.
        """
        flag_true_values = flag_true_values or []
        flag_false_values = flag_false_values or []
        overlapping_values = set(flag_true_values) & set(flag_false_values)
        if overlapping_values:
            raise ValueError(
                "Flag true and false values must not overlap: "
                f"{sorted(overlapping_values)!r}"
            )

        encounter_col = self._safe_identifier(encounter_col)
        agg_col_name = self._safe_identifier(agg_col_name)
        last_set_ts_col = self._safe_identifier(f"{agg_col_name}_last_set_ts")
        ref_dt_col = self._safe_identifier(ref_dt_col)
        evt_dt_col = self._safe_identifier(evt_dt_col)
        evt_val_col = self._safe_identifier(evt_val_col)

        lower_bound_clause = ""
        if lookback_period is not None:
            if isinstance(lookback_period, (int, float)):
                lookback_period = timedelta(minutes=lookback_period)
            if lookback_period < timedelta(0):
                raise ValueError("lookback_period must be non-negative")

            interval_str = f"{int(lookback_period.total_seconds())} seconds"
            lower_bound_clause = f"""
                        AND events_tbl.{evt_dt_col} >= reference_tbl.{ref_dt_col}
                            - INTERVAL '{interval_str}'
            """

        flag_state_col = "_flag_state"
        event_value = pl.col(evt_val_col)
        event_value_as_string = event_value.cast(pl.String)
        is_explicit_false = (
            event_value.is_not_null()
            & event_value_as_string.is_in(flag_false_values)
            if flag_false_values
            else pl.lit(False)
        )
        is_true = (
            event_value.is_null()
            | event_value_as_string.is_in(flag_true_values)
            if flag_true_values
            else pl.lit(True)
        )

        classified_events = (
            events.with_columns(
                pl.when(is_explicit_false)
                .then(pl.lit(0))
                .when(is_true)
                .then(pl.lit(1))
                .otherwise(pl.lit(None))
                .alias(flag_state_col)
            )
            .filter(pl.col(flag_state_col).is_not_null())
            .select(encounter_col, evt_dt_col, flag_state_col)
        )

        if termination_events is not None:
            classified_termination_events = termination_events.select(
                encounter_col,
                evt_dt_col,
                pl.lit(0).alias(flag_state_col),
            )
            classified_events = pl.concat(
                [classified_events, classified_termination_events],
                how="vertical",
            ).unique(subset=[encounter_col, evt_dt_col, flag_state_col])

        with duckdb.connect() as conn:
            conn.register("reference_tbl", reference)
            conn.register("events_tbl", classified_events)

            result = conn.sql(f"""
                WITH rolling_state AS (
                    SELECT
                        reference_tbl.{encounter_col},
                        reference_tbl.{ref_dt_col},
                        MAX(
                            CASE
                                WHEN events_tbl.{flag_state_col} = 1
                                THEN events_tbl.{evt_dt_col}
                            END
                        ) AS last_true_ts,
                        MAX(
                            CASE
                                WHEN events_tbl.{flag_state_col} = 0
                                THEN events_tbl.{evt_dt_col}
                            END
                        ) AS last_false_ts
                    FROM reference_tbl
                    LEFT JOIN events_tbl
                        ON reference_tbl.{encounter_col} = events_tbl.{encounter_col}
                        AND events_tbl.{evt_dt_col} <= reference_tbl.{ref_dt_col}
                        {lower_bound_clause}
                    GROUP BY
                        reference_tbl.{encounter_col},
                        reference_tbl.{ref_dt_col}
                )
                SELECT
                    {encounter_col},
                    {ref_dt_col},
                    CASE
                        WHEN last_true_ts IS NOT NULL
                            AND (
                                last_false_ts IS NULL
                                OR last_true_ts > last_false_ts
                            )
                        THEN 1
                        ELSE 0
                    END AS {agg_col_name},
                    last_true_ts AS {last_set_ts_col}
                FROM rolling_state
            """).pl()

        return result

    def _prepare_event_table(self, df:pl.DataFrame, feature: FeatureDefinition):
        event_filter = (
            pl.col(self.aggregator_config.grouper_col) == feature.event_grouper
        )
        if feature.agg_type == "numeric":
            event_filter &= pl.col(feature.val_col).is_not_null()

        return df.filter(event_filter).select(
            self.aggregator_config.encounter_col,
            pl.col(self.aggregator_config.event_dt_col).alias(self.aggregator_config.evt_dt_col),
            pl.col(feature.val_col).alias(self.aggregator_config.evt_val_col)
        )

    def _prepare_termination_event_table(
        self,
        df: pl.DataFrame,
        feature: FeatureDefinition,
    ) -> pl.DataFrame | None:
        if feature.termination_event_grouper is None:
            return None

        return (
            df.filter(
                pl.col(self.aggregator_config.grouper_col)
                == feature.termination_event_grouper
            )
            .select(
                self.aggregator_config.encounter_col,
                pl.col(self.aggregator_config.event_dt_col).alias(
                    self.aggregator_config.evt_dt_col
                ),
            )
            .unique()
        )

    def _monitor_pre_post_aggregate(
        self,
        backbone: pl.DataFrame,
        event: pl.DataFrame,
        feature: FeatureDefinition,
        termination_events: pl.DataFrame | None = None,
    ):
        if feature.agg_type == "flag":
            agg_feat_len = backbone.filter(pl.col(feature.alias) == 1).shape[0]
            event_value = pl.col(self.aggregator_config.evt_val_col)
            if feature.flag_true_values:
                recognized_event = (
                    event_value.is_null()
                    | event_value.cast(pl.String).is_in(
                        feature.flag_true_values
                        + (feature.flag_false_values or [])
                    )
                )
                evt_len = event.filter(recognized_event).shape[0]
            else:
                evt_len = event.shape[0]
            if termination_events is not None:
                evt_len += termination_events.shape[0]
        else:
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
            event = self._prepare_event_table(df, feature)
            termination_events = None

            if feature.agg_type == "numeric":
                logger.info(f"Aggregating numeric feature {feature.alias} using {feature.agg} over last {feature.lookback_period} minutes for events in {feature.event_grouper}")
                event_with_agg = self.rolling_agg_by_duckdb(
                    reference=backbone,
                    events=event,
                    agg_col_name=feature.alias,
                    agg_func=feature.agg,
                    lookback_period=feature.lookback_period,
                    encounter_col=self.aggregator_config.encounter_col,
                    ref_dt_col=self.aggregator_config.event_dt_col,
                    evt_dt_col=self.aggregator_config.evt_dt_col,
                    evt_val_col=self.aggregator_config.evt_val_col,
                )
            elif feature.agg_type == "flag":
                if not feature.persist_until_termination:
                    raise NotImplementedError(
                        "Flag features with persist_until_termination=False "
                        "do not yet have approved aggregation semantics"
                    )

                if feature.lookback_period is None:
                    logger.info(f"Aggregating flag feature {feature.alias} over all prior encounter events in {feature.event_grouper}")
                else:
                    logger.info(f"Aggregating flag feature {feature.alias} over last {feature.lookback_period} minutes for events in {feature.event_grouper}")
                termination_events = self._prepare_termination_event_table(
                    df,
                    feature,
                )
                event_with_agg = self.rolling_flag_by_duckdb(
                    reference=backbone,
                    events=event,
                    agg_col_name=feature.alias,
                    flag_true_values=feature.flag_true_values or [],
                    flag_false_values=feature.flag_false_values,
                    termination_events=termination_events,
                    lookback_period=feature.lookback_period,
                    encounter_col=self.aggregator_config.encounter_col,
                    ref_dt_col=self.aggregator_config.event_dt_col,
                    evt_dt_col=self.aggregator_config.evt_dt_col,
                    evt_val_col=self.aggregator_config.evt_val_col,
                )
            else:
                raise ValueError(
                    f"Unsupported aggregation type: {feature.agg_type!r}"
                )

            backbone = backbone.join(event_with_agg, on=[self.aggregator_config.encounter_col, self.aggregator_config.event_dt_col],
                                      how="left")

            if feature.agg_type == "numeric":
                if feature.agg == "last":
                    assert backbone.join(event, left_on=[self.aggregator_config.encounter_col, self.aggregator_config.event_dt_col], right_on=[self.aggregator_config.encounter_col, self.aggregator_config.evt_dt_col], how="inner").filter(pl.col(feature.alias)!=pl.col(self.aggregator_config.evt_val_col)).shape[0] == 0,\
                    f"Aggregation failed for {feature.alias}. On joining back to original dataframe, values do not match"

                assert backbone.join(event, left_on=[self.aggregator_config.encounter_col, self.aggregator_config.event_dt_col], right_on=[self.aggregator_config.encounter_col, self.aggregator_config.evt_dt_col], how="inner").shape[0] == event.shape[0],\
                f"Aggregation failed for {feature.alias}. backbone and event tables have different number of rows after join"

                source_ts_col = f"{feature.alias}_source_ts"
                assert backbone.filter(
                    pl.col(source_ts_col)
                    > pl.col(self.aggregator_config.event_dt_col)
                ).is_empty(), f"Aggregation failed for {feature.alias}. Source timestamp cannot be after the reference timestamp"
            else:
                assert backbone.filter(
                    pl.col(feature.alias).is_null()
                    | ~pl.col(feature.alias).is_in([0, 1])
                ).is_empty(), f"Aggregation failed for {feature.alias}. Flag output must be 0 or 1"

            self._monitor_pre_post_aggregate(
                backbone,
                event,
                feature,
                termination_events,
            )
            logger.info(f"Feature {feature.alias} aggregated and joined. Current backbone table now has {backbone.shape[0]} rows and {backbone.shape[1]} columns.")
            logger.info("--------------------------------------------------------------------------------")

        return backbone

    def aggregate(self, df: pl.DataFrame, backbone: pl.DataFrame, engine="duckdb") -> pl.DataFrame:
        if engine == "duckdb":
            return self._aggregate_by_duckdb(df, backbone)
        elif engine == "polars":
            return self._aggregate_by_polars(df)
        return df
