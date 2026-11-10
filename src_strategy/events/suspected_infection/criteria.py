from abc import ABC, abstractmethod

import duckdb
import polars as pl

from ...configs.suspected_infection import SuspectedInfectionConfig


class SuspectedInfectionCriterion(ABC):
    """Strategy contract for one suspected-infection evidence source."""

    def __init__(self, config: SuspectedInfectionConfig):
        self.config = config

    @abstractmethod
    def detect(self, df: pl.DataFrame) -> pl.DataFrame:
        """Return evidence in the configured long-frame format."""

    def _long_rows(
        self,
        df: pl.DataFrame,
        evidence_datetime_col: str,
        criterion_value: str,
        long_value: str,
        infection_episode_id_col: str = "_infection_episode_id",
        infection_datetime_col: str = "_infect_dt",
        criterion_met_datetime_col: str = "_criterion_met_dt",
        administration_datetime_col: str | None = None,
        antibiotic_time_source_col: str | None = None,
        culture_result_datetime_col: str | None = None,
        culture_result_status_col: str | None = None,
        lactate_result_datetime_col: str | None = None,
        lactate_result_value_col: str | None = None,
    ) -> pl.DataFrame:
        antibiotic_config = self.config.antibiotic_blood_culture_config
        configured_admin_col = antibiotic_config.administration_datetime_col
        admin_datetime = (
            pl.col(administration_datetime_col)
            if administration_datetime_col is not None
            else pl.lit(None, dtype=pl.Datetime)
        )
        antibiotic_time_source = (
            pl.col(antibiotic_time_source_col)
            if antibiotic_time_source_col is not None
            else pl.lit(None, dtype=pl.String)
        )
        culture_result_datetime = (
            pl.col(culture_result_datetime_col)
            if culture_result_datetime_col is not None
            else pl.lit(None, dtype=pl.Datetime)
        )
        culture_result_status = (
            pl.col(culture_result_status_col)
            if culture_result_status_col is not None
            else pl.lit(None, dtype=pl.String)
        )
        lactate_result_datetime = (
            pl.col(lactate_result_datetime_col)
            if lactate_result_datetime_col is not None
            else pl.lit(None, dtype=pl.Datetime)
        )
        lactate_result_value = (
            pl.col(lactate_result_value_col)
            if lactate_result_value_col is not None
            else pl.lit(None, dtype=pl.Float64)
        )
        return df.select(
            pl.col(self.config.encounter_col),
            pl.col(infection_episode_id_col).alias(
                self.config.infection_episode_id_col
            ),
            pl.lit(criterion_value).alias(self.config.variable_name_col),
            pl.col(infection_datetime_col).alias(self.config.value_name_dt_col),
            pl.col(criterion_met_datetime_col).alias(
                self.config.criterion_met_datetime_col
            ),
            pl.col(evidence_datetime_col).alias(
                self.config.evidence_datetime_col
            ),
            pl.lit(long_value).alias(self.config.value_type_col),
            admin_datetime.alias(configured_admin_col),
            antibiotic_time_source.alias(
                antibiotic_config.antibiotic_time_source_col
            ),
            culture_result_datetime.alias(
                self.config.culture_result_datetime_col
            ),
            culture_result_status.alias(self.config.culture_result_status_col),
            lactate_result_datetime.alias(
                self.config.lactate_culture_config.lactate_result_datetime_col
            ),
            lactate_result_value.alias(
                self.config.lactate_culture_config.lactate_result_value_col
            ),
        )

    def _culture_orders_with_results(self, df: pl.DataFrame) -> pl.DataFrame:
        """Return one culture-order row per Event_ID with optional result metadata."""
        orders = (
            df.filter(
                (pl.col(self.config.type_col) == self.config.blood_culture_order_type)
                & pl.col(self.config.grouper_col).is_in(
                    self.config.blood_culture_groupers
                )
            )
            .select(
                pl.col(self.config.encounter_col).alias("_encounter"),
                pl.col(self.config.event_id).alias("_culture_id"),
                pl.col(self.config.event_dt_col).alias("_culture_dt"),
                pl.col(self.config.event_name_col).alias("_culture_name"),
            )
            .drop_nulls(["_encounter", "_culture_dt"])
            .unique()
            .sort("_encounter", "_culture_dt", "_culture_name")
        )
        linked_orders = (
            orders.filter(pl.col("_culture_id").is_not_null())
            .group_by("_encounter", "_culture_id", maintain_order=True)
            .agg(
                pl.col("_culture_dt").first(),
                pl.col("_culture_name").first(),
            )
        )
        unlinked_orders = orders.filter(pl.col("_culture_id").is_null())

        result_text = pl.col(self.config.raw_val_col).cast(pl.String).fill_null("")
        result_name = (
            pl.col(self.config.event_name_col).cast(pl.String).fill_null("")
        )
        result_rows = (
            df.filter(
                (pl.col(self.config.type_col) == self.config.blood_culture_result_type)
                & pl.col(self.config.grouper_col).is_in(
                    self.config.blood_culture_groupers
                )
            )
            .select(
                pl.col(self.config.encounter_col).alias("_encounter"),
                pl.col(self.config.event_id).alias("_culture_id"),
                pl.col(self.config.event_dt_col).alias("_result_dt"),
                pl.col(self.config.event_name_col),
                pl.col(self.config.raw_val_col),
            )
            .drop_nulls(["_encounter", "_culture_id", "_result_dt"])
            .with_columns(
                pl.when(
                    pl.concat_str([result_name, result_text], separator=" ")
                    .str.contains(self.config.culture_contaminant_value_pattern)
                )
                .then(pl.lit("contaminant"))
                .when(
                    result_name.str.to_uppercase().is_in(
                        self.config.culture_negative_event_names
                    )
                    & result_text.str.contains(
                        self.config.culture_negative_value_pattern
                    )
                )
                .then(pl.lit("negative"))
                .when(
                    result_name.str.contains(
                        self.config.culture_positive_event_name_pattern
                    )
                    & result_text.str.contains(
                        self.config.culture_positive_value_pattern
                    )
                )
                .then(pl.lit("positive"))
                .otherwise(pl.lit("indeterminate"))
                .alias("_row_result_status")
            )
        )
        result_summary = (
            result_rows.group_by("_encounter", "_culture_id")
            .agg(
                pl.col("_result_dt").min().alias("_first_result_dt"),
                pl.col("_result_dt")
                .filter(pl.col("_row_result_status") == "contaminant")
                .min()
                .alias("_contaminant_dt"),
                pl.col("_result_dt")
                .filter(pl.col("_row_result_status") == "positive")
                .min()
                .alias("_positive_dt"),
                pl.col("_result_dt")
                .filter(pl.col("_row_result_status") == "negative")
                .min()
                .alias("_negative_dt"),
            )
            .with_columns(
                pl.when(pl.col("_contaminant_dt").is_not_null())
                .then(pl.lit("contaminant"))
                .when(pl.col("_positive_dt").is_not_null())
                .then(pl.lit("positive"))
                .when(pl.col("_negative_dt").is_not_null())
                .then(pl.lit("negative"))
                .otherwise(pl.lit("indeterminate"))
                .alias("_culture_result_status")
            )
            .with_columns(
                pl.when(pl.col("_culture_result_status") == "contaminant")
                .then(pl.col("_contaminant_dt"))
                .when(pl.col("_culture_result_status") == "positive")
                .then(pl.col("_positive_dt"))
                .when(pl.col("_culture_result_status") == "negative")
                .then(pl.col("_negative_dt"))
                .otherwise(pl.col("_first_result_dt"))
                .alias("_culture_result_dt")
            )
            .select(
                "_encounter",
                "_culture_id",
                "_culture_result_dt",
                "_culture_result_status",
            )
        )

        linked_orders = linked_orders.join(
            result_summary,
            on=["_encounter", "_culture_id"],
            how="left",
            validate="1:1",
        ).with_columns(
            pl.col("_culture_result_status").fill_null("pending")
        )
        unlinked_orders = unlinked_orders.with_columns(
            pl.lit(None, dtype=pl.Datetime).alias("_culture_result_dt"),
            pl.lit("pending").alias("_culture_result_status"),
        )
        return (
            pl.concat([linked_orders, unlinked_orders], how="vertical")
            .sort("_encounter", "_culture_dt", "_culture_name")
            .with_row_index("_culture_key")
        )

    def _lactate_orders_with_results(self, df: pl.DataFrame) -> pl.DataFrame:
        """Return lactate orders with optional linked result time and value."""
        config = self.config.lactate_culture_config
        orders = (
            df.filter(
                (pl.col(self.config.type_col) == config.lactate_order_type)
                & (
                    pl.col(self.config.grouper_col)
                    == config.lactate_order_grouper_val
                )
                & pl.col(self.config.event_name_col).is_in(
                    config.lactate_order_event_names
                )
            )
            .select(
                pl.col(self.config.encounter_col).alias("_encounter"),
                pl.col(self.config.event_id).alias("_lactate_id"),
                pl.col(self.config.event_dt_col).alias("_lactate_dt"),
                pl.col(self.config.event_name_col).alias("_lactate_name"),
            )
            .drop_nulls(["_encounter", "_lactate_dt"])
            .unique()
            .sort("_encounter", "_lactate_dt", "_lactate_name")
        )
        linked_orders = (
            orders.filter(pl.col("_lactate_id").is_not_null())
            .group_by("_encounter", "_lactate_id", maintain_order=True)
            .agg(
                pl.col("_lactate_dt").first(),
                pl.col("_lactate_name").first(),
            )
        )
        unlinked_orders = orders.filter(pl.col("_lactate_id").is_null())

        result_summary = (
            df.filter(
                (pl.col(self.config.type_col) == config.lactate_result_type)
                & (
                    pl.col(self.config.grouper_col)
                    == config.lactate_grouper_val
                )
            )
            .select(
                pl.col(self.config.encounter_col).alias("_encounter"),
                pl.col(self.config.event_id).alias("_lactate_id"),
                pl.col(self.config.event_dt_col).alias("_lactate_result_dt"),
                pl.col(self.config.val_col)
                .cast(pl.Float64)
                .alias("_lactate_result_value"),
            )
            .drop_nulls(["_encounter", "_lactate_id", "_lactate_result_dt"])
            .sort("_encounter", "_lactate_id", "_lactate_result_dt")
            .group_by("_encounter", "_lactate_id", maintain_order=True)
            .agg(
                pl.col("_lactate_result_dt").first(),
                pl.col("_lactate_result_value").first(),
            )
        )
        linked_orders = linked_orders.join(
            result_summary,
            on=["_encounter", "_lactate_id"],
            how="left",
            validate="1:1",
        )
        unlinked_orders = unlinked_orders.with_columns(
            pl.lit(None, dtype=pl.Datetime).alias("_lactate_result_dt"),
            pl.lit(None, dtype=pl.Float64).alias("_lactate_result_value"),
        )
        return (
            pl.concat([linked_orders, unlinked_orders], how="vertical")
            .sort("_encounter", "_lactate_dt", "_lactate_name")
            .with_row_index("_lactate_key")
        )


class AntibioticCultureCriterion(SuspectedInfectionCriterion):
    def detect(self, df: pl.DataFrame) -> pl.DataFrame:
        config = self.config.antibiotic_blood_culture_config
        grouper_expr = pl.col(self.config.grouper_col).cast(pl.String)
        administration_filter = (
            (pl.col(self.config.type_col) == config.antibiotic_administration_type)
            & grouper_expr.is_in(config.antibiotic_grouper)
        )

        administration_rows = (
            df.filter(administration_filter)
            .select(
                self.config.encounter_col,
                self.config.event_id,
                self.config.event_dt_col,
            )
            .drop_nulls(
                [
                    self.config.encounter_col,
                    self.config.event_dt_col,
                ]
            )
        )
        linked_administrations = (
            administration_rows.filter(pl.col(self.config.event_id).is_not_null())
            .group_by(self.config.encounter_col, self.config.event_id)
            .agg(pl.col(self.config.event_dt_col).min().alias("_admin_dt"))
        )
        unlinked_administrations = (
            administration_rows.filter(pl.col(self.config.event_id).is_null())
            .select(
                pl.col(self.config.encounter_col).alias("_encounter"),
                pl.col(self.config.event_id).alias("_antibiotic_id"),
                pl.col(self.config.event_dt_col).alias("_antibiotic_dt"),
                pl.col(self.config.event_dt_col).alias("_admin_dt"),
                pl.lit("administration_fallback").alias("_infect_dt_source"),
            )
            .unique()
        )
        orders = (
            df.filter(
                pl.col(self.config.type_col) == config.antibiotic_order_type
            )
            .select(
                self.config.encounter_col,
                self.config.event_id,
                self.config.event_dt_col,
            )
            .drop_nulls(
                [
                    self.config.encounter_col,
                    self.config.event_id,
                    self.config.event_dt_col,
                ]
            )
            .group_by(self.config.encounter_col, self.config.event_id)
            .agg(pl.col(self.config.event_dt_col).min().alias("_order_dt"))
        )
        first_event_by_id = (
            df.select(
                self.config.encounter_col,
                self.config.event_id,
                self.config.event_dt_col,
            )
            .drop_nulls(
                [
                    self.config.encounter_col,
                    self.config.event_id,
                    self.config.event_dt_col,
                ]
            )
            .group_by(self.config.encounter_col, self.config.event_id)
            .agg(
                pl.col(self.config.event_dt_col)
                .min()
                .alias("_event_id_first_dt")
            )
        )
        linked_antibiotics = (
            linked_administrations.join(
                first_event_by_id,
                on=[self.config.encounter_col, self.config.event_id],
                how="inner",
                validate="1:1",
            )
            .join(
                orders,
                on=[self.config.encounter_col, self.config.event_id],
                how="left",
                validate="1:1",
            )
            .with_columns(
                pl.coalesce("_order_dt", "_event_id_first_dt").alias(
                    "_antibiotic_dt"
                ),
                pl.when(pl.col("_order_dt").is_not_null())
                .then(pl.lit("medication_order"))
                .when(pl.col("_event_id_first_dt") < pl.col("_admin_dt"))
                .then(pl.lit("event_id_first_event"))
                .otherwise(pl.lit("administration_fallback"))
                .alias("_infect_dt_source"),
            )
            .select(
                pl.col(self.config.encounter_col).alias("_encounter"),
                pl.col(self.config.event_id).alias("_antibiotic_id"),
                "_antibiotic_dt",
                "_admin_dt",
                "_infect_dt_source",
            )
        )
        antibiotics = (
            pl.concat(
                [linked_antibiotics, unlinked_administrations],
                how="vertical",
            )
            .sort(
                "_encounter",
                "_antibiotic_dt",
                "_admin_dt",
                "_antibiotic_id",
            )
            .with_columns(
                (
                    pl.lit(f"{config.long_value}:")
                    + pl.int_range(1, pl.len() + 1)
                    .over("_encounter")
                    .cast(pl.String)
                ).alias("_infection_episode_id")
            )
        )
        cultures = self._culture_orders_with_results(df)

        before_minutes = config.culture_before_antibiotic_minutes
        after_minutes = config.culture_after_antibiotic_minutes
        with duckdb.connect() as connection:
            connection.register("antibiotics", antibiotics)
            connection.register("cultures", cultures)
            pairs = connection.sql(f"""
                SELECT
                    a._encounter,
                    a._antibiotic_id,
                    a._antibiotic_dt,
                    a._admin_dt,
                    a._infect_dt_source,
                    a._infection_episode_id,
                    c._culture_key,
                    c._culture_id,
                    c._culture_dt,
                    c._culture_result_dt,
                    c._culture_result_status,
                    LEAST(
                        a._antibiotic_dt,
                        MIN(c._culture_dt) OVER (
                            PARTITION BY a._encounter, a._infection_episode_id
                        )
                    ) AS _infect_dt,
                    GREATEST(
                        a._admin_dt,
                        MIN(c._culture_dt) OVER (
                            PARTITION BY a._encounter, a._infection_episode_id
                        )
                    ) AS _criterion_met_dt
                FROM antibiotics AS a
                INNER JOIN cultures AS c
                    ON a._encounter = c._encounter
                    AND c._culture_dt >= a._admin_dt
                        - INTERVAL '{before_minutes} minutes'
                    AND c._culture_dt <= a._admin_dt
                        + INTERVAL '{after_minutes} minutes'
            """).pl()

        chosen_pair = pairs.rename({"_encounter": self.config.encounter_col})
        antibiotic_rows = self._long_rows(
            chosen_pair.unique(
                subset=[
                    self.config.encounter_col,
                    "_infection_episode_id",
                ]
            ),
            "_antibiotic_dt",
            config.antibiotic_datetime_col,
            config.long_value,
            administration_datetime_col="_admin_dt",
            antibiotic_time_source_col="_infect_dt_source",
        )
        culture_rows = self._long_rows(
            chosen_pair,
            "_culture_dt",
            config.blood_culture_datetime_col,
            config.long_value,
            administration_datetime_col="_admin_dt",
            antibiotic_time_source_col="_infect_dt_source",
            culture_result_datetime_col="_culture_result_dt",
            culture_result_status_col="_culture_result_status",
        )
        return pl.concat([antibiotic_rows, culture_rows], how="vertical")


class LactateCultureCriterion(SuspectedInfectionCriterion):
    def detect(self, df: pl.DataFrame) -> pl.DataFrame:
        config = self.config.lactate_culture_config
        lactates = self._lactate_orders_with_results(df).with_columns(
            (
                pl.lit(f"{config.long_value}:")
                + pl.int_range(1, pl.len() + 1)
                .over("_encounter")
                .cast(pl.String)
            ).alias("_infection_episode_id")
        )
        cultures = self._culture_orders_with_results(df)

        tolerance_minutes = config.tolerance_minutes
        minimum_culture_orders = config.minimum_culture_orders
        with duckdb.connect() as connection:
            connection.register("lactates", lactates)
            connection.register("cultures", cultures)
            chosen_matches = connection.sql(f"""
                WITH matches AS (
                    SELECT
                        l._encounter,
                        l._lactate_key,
                        l._lactate_dt,
                        l._lactate_result_dt,
                        l._lactate_result_value,
                        l._infection_episode_id,
                        c._culture_key,
                        c._culture_dt,
                        c._culture_name,
                        c._culture_result_dt,
                        c._culture_result_status
                    FROM lactates AS l
                    INNER JOIN cultures AS c
                        ON l._encounter = c._encounter
                        AND c._culture_dt >= l._lactate_dt
                            - INTERVAL '{tolerance_minutes} minutes'
                        AND c._culture_dt <= l._lactate_dt
                            + INTERVAL '{tolerance_minutes} minutes'
                ),
                qualifying_episodes AS (
                    SELECT
                        _encounter,
                        _lactate_key,
                        _lactate_dt,
                        MIN(_culture_dt) AS _first_culture_dt,
                        LIST_EXTRACT(
                            LIST(_culture_dt ORDER BY _culture_dt, _culture_key),
                            {minimum_culture_orders}
                        ) AS _criterion_culture_dt
                    FROM matches
                    GROUP BY
                        _encounter,
                        _lactate_key,
                        _lactate_dt
                    HAVING COUNT(DISTINCT _culture_key) >= {minimum_culture_orders}
                )
                SELECT
                    matches._encounter,
                    matches._lactate_key,
                    matches._lactate_dt,
                    matches._lactate_result_dt,
                    matches._lactate_result_value,
                    matches._infection_episode_id,
                    matches._culture_key,
                    matches._culture_dt,
                    matches._culture_name,
                    matches._culture_result_dt,
                    matches._culture_result_status,
                    LEAST(
                        matches._lactate_dt,
                        qualifying_episodes._first_culture_dt
                    ) AS _infect_dt,
                    GREATEST(
                        matches._lactate_dt,
                        qualifying_episodes._criterion_culture_dt
                    ) AS _criterion_met_dt
                FROM matches
                INNER JOIN qualifying_episodes
                    ON matches._encounter = qualifying_episodes._encounter
                    AND matches._lactate_key = qualifying_episodes._lactate_key
                    AND matches._lactate_dt = qualifying_episodes._lactate_dt
                ORDER BY
                    matches._encounter,
                    matches._lactate_key,
                    matches._lactate_dt,
                    matches._culture_dt,
                    matches._culture_name NULLS LAST
            """).pl()
            # chosen_matches = connection.sql(f"""
            #     WITH matches AS (
            #         SELECT
            #             l._encounter,
            #             l._lactate_dt,
            #             c._culture_dt,
            #             c._culture_name
            #         FROM lactates AS l
            #         INNER JOIN cultures AS c
            #             ON l._encounter = c._encounter
            #             AND c._culture_dt >= l._lactate_dt
            #                 - INTERVAL '{tolerance_minutes} minutes'
            #             AND c._culture_dt <= l._lactate_dt
            #                 + INTERVAL '{tolerance_minutes} minutes'
            #     ),
            #     qualifying_episodes AS (
            #         SELECT
            #             _encounter,
            #             _lactate_dt,
            #             MIN(_culture_dt) AS _first_culture_dt,
            #             COUNT(*) AS _culture_count
            #         FROM matches
            #         GROUP BY _encounter, _lactate_dt
            #         HAVING COUNT(*) >= {minimum_culture_orders}
            #     ),
            #     chosen_episode AS (
            #         SELECT _encounter, _lactate_dt
            #         FROM (
            #             SELECT
            #                 _encounter,
            #                 _lactate_dt,
            #                 ROW_NUMBER() OVER (
            #                     PARTITION BY _encounter
            #                     ORDER BY
            #                         LEAST(_lactate_dt, _first_culture_dt),
            #                         _lactate_dt
            #                 ) AS _episode_rank
            #             FROM qualifying_episodes
            #         )
            #         WHERE _episode_rank = 1
            #     )
            #     SELECT
            #         matches._encounter,
            #         matches._lactate_dt,
            #         matches._culture_dt,
            #         matches._culture_name
            #     FROM matches
            #     INNER JOIN chosen_episode
            #         ON matches._encounter = chosen_episode._encounter
            #         AND matches._lactate_dt = chosen_episode._lactate_dt
            #     ORDER BY
            #         matches._encounter,
            #         matches._culture_dt,
            #         matches._culture_name NULLS LAST
            # """).pl()

        chosen_matches = chosen_matches.rename(
            {"_encounter": self.config.encounter_col}
        )
        lactate_rows = self._long_rows(
            chosen_matches.unique(
                subset=[self.config.encounter_col, "_lactate_key"]
            ),
            "_lactate_dt",
            config.lactate_datetime_col,
            config.long_value,
            lactate_result_datetime_col="_lactate_result_dt",
            lactate_result_value_col="_lactate_result_value",
        )
        culture_rows = self._long_rows(
            chosen_matches,
            "_culture_dt",
            config.blood_culture_datetime_col,
            config.long_value,
            culture_result_datetime_col="_culture_result_dt",
            culture_result_status_col="_culture_result_status",
        )
        return pl.concat([lactate_rows, culture_rows], how="vertical")


class CodeSepsisCriterion(SuspectedInfectionCriterion):
    def detect(self, df: pl.DataFrame) -> pl.DataFrame:
        config = self.config.code_sepsis_config
        events = (
            df.filter(pl.col(self.config.grouper_col) == config.grouper_val)
            .select(
                self.config.encounter_col,
                pl.col(self.config.event_dt_col).alias("_event_dt"),
            )
            .drop_nulls([self.config.encounter_col, "_event_dt"])
            .unique()
            .sort(self.config.encounter_col, "_event_dt")
            .with_columns(
                (
                    pl.lit(f"{config.long_value}:")
                    + pl.int_range(1, pl.len() + 1)
                    .over(self.config.encounter_col)
                    .cast(pl.String)
                ).alias("_infection_episode_id"),
                pl.col("_event_dt").alias("_infect_dt"),
                pl.col("_event_dt").alias("_criterion_met_dt"),
            )
        )
        return self._long_rows(
            events,
            "_event_dt",
            config.datetime_col,
            config.long_value,
        )


class SuspectedInfectionFlowsheetCriterion(SuspectedInfectionCriterion):
    def detect(self, df: pl.DataFrame) -> pl.DataFrame:
        config = self.config.suspected_infection_flowsheet_config
        events = (
            df.filter(
                (pl.col(self.config.grouper_col) == config.grouper_val)
                & (pl.col(self.config.raw_val_col) == config.qualifying_value)
            )
            .select(
                self.config.encounter_col,
                pl.col(self.config.event_dt_col).alias("_event_dt"),
            )
            .drop_nulls([self.config.encounter_col, "_event_dt"])
            .unique()
            .sort(self.config.encounter_col, "_event_dt")
            .with_columns(
                (
                    pl.lit(f"{config.long_value}:")
                    + pl.int_range(1, pl.len() + 1)
                    .over(self.config.encounter_col)
                    .cast(pl.String)
                ).alias("_infection_episode_id"),
                pl.col("_event_dt").alias("_infect_dt"),
                pl.col("_event_dt").alias("_criterion_met_dt"),
            )
        )
        return self._long_rows(
            events,
            "_event_dt",
            config.datetime_col,
            config.long_value,
        )
