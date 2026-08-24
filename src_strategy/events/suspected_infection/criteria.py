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
        datetime_col: str,
        criterion_value: str,
        long_value: str,
    ) -> pl.DataFrame:
        return df.select(
            pl.col(self.config.encounter_col),
            pl.lit(criterion_value).alias(self.config.variable_name_col),
            pl.col(datetime_col).alias(self.config.value_name_dt_col),
            pl.lit(long_value).alias(self.config.value_type_col),
        )


class AntibioticCultureCriterion(SuspectedInfectionCriterion):
    def detect(self, df: pl.DataFrame) -> pl.DataFrame:
        config = self.config.antibiotic_blood_culture_config
        antibiotic_type = pl.col(self.config.type_col).cast(pl.String)
        antibiotic_filter = antibiotic_type.str.starts_with(
            config.antibiotic_type_prefix
        )
        for excluded_prefix in config.antibiotic_excluded_type_prefixes:
            antibiotic_filter &= ~antibiotic_type.str.starts_with(excluded_prefix)

        antibiotics = (
            df.filter(antibiotic_filter)
            .select(
                pl.col(self.config.encounter_col).alias("_encounter"),
                pl.col(self.config.event_dt_col).alias("_antibiotic_dt"),
                pl.col(self.config.event_name_col).alias("_antibiotic_name"),
            )
            .drop_nulls(["_encounter", "_antibiotic_dt"])
            .unique()
        )
        cultures = (
            df.filter(
                pl.col(self.config.grouper_col)
                == config.blood_culture_grouper_val
            )
            .select(
                pl.col(self.config.encounter_col).alias("_encounter"),
                pl.col(self.config.event_dt_col).alias("_culture_dt"),
                pl.col(self.config.event_name_col).alias("_culture_name"),
            )
            .drop_nulls(["_encounter", "_culture_dt"])
            .unique()
        )

        before_minutes = config.culture_before_antibiotic_minutes
        after_minutes = config.culture_after_antibiotic_minutes
        with duckdb.connect() as connection:
            connection.register("antibiotics", antibiotics)
            connection.register("cultures", cultures)
            pairs = connection.sql(f"""
                SELECT
                    a._encounter,
                    a._antibiotic_dt,
                    c._culture_dt,
                    ROW_NUMBER() OVER (
                        PARTITION BY a._encounter
                        ORDER BY
                            LEAST(a._antibiotic_dt, c._culture_dt),
                            a._antibiotic_dt,
                            c._culture_dt,
                            a._antibiotic_name NULLS LAST,
                            c._culture_name NULLS LAST
                    ) AS _episode_rank
                FROM antibiotics AS a
                INNER JOIN cultures AS c
                    ON a._encounter = c._encounter
                    AND c._culture_dt >= a._antibiotic_dt
                        - INTERVAL '{before_minutes} minutes'
                    AND c._culture_dt <= a._antibiotic_dt
                        + INTERVAL '{after_minutes} minutes'
            """).pl()

        chosen_pair = (
            pairs
            # TODO: Decide whether you want to keep all culture/IV combinations or only the earliest
            #.filter(pl.col("_episode_rank") == 1)
            .drop("_episode_rank")
            .rename({"_encounter": self.config.encounter_col})
        )
        antibiotic_rows = self._long_rows(
            chosen_pair,
            "_antibiotic_dt",
            config.antibiotic_datetime_col,
            config.long_value,
        )
        culture_rows = self._long_rows(
            chosen_pair,
            "_culture_dt",
            config.blood_culture_datetime_col,
            config.long_value,
        )
        return pl.concat([antibiotic_rows, culture_rows], how="vertical")


class LactateCultureCriterion(SuspectedInfectionCriterion):
    def detect(self, df: pl.DataFrame) -> pl.DataFrame:
        config = self.config.lactate_culture_config
        lactates = (
            df.filter(
                pl.col(self.config.grouper_col) == config.lactate_grouper_val
            )
            .select(
                pl.col(self.config.encounter_col).alias("_encounter"),
                pl.col(self.config.event_dt_col).alias("_lactate_dt"),
            )
            .drop_nulls(["_encounter", "_lactate_dt"])
            .unique()
        )
        cultures = (
            df.filter(
                pl.col(self.config.grouper_col)
                == config.blood_culture_grouper_val
            )
            .select(
                pl.col(self.config.encounter_col).alias("_encounter"),
                pl.col(self.config.event_dt_col).alias("_culture_dt"),
                pl.col(self.config.event_name_col).alias("_culture_name"),
            )
            .drop_nulls(["_encounter", "_culture_dt"])
            .unique()
        )

        tolerance_minutes = config.tolerance_minutes
        minimum_culture_orders = config.minimum_culture_orders
        with duckdb.connect() as connection:
            connection.register("lactates", lactates)
            connection.register("cultures", cultures)
            chosen_matches = connection.sql(f"""
                WITH matches AS (
                    SELECT
                        l._encounter,
                        l._lactate_dt,
                        c._culture_dt,
                        c._culture_name
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
                        _lactate_dt
                    FROM matches
                    GROUP BY
                        _encounter,
                        _lactate_dt
                    HAVING COUNT(*) >= {minimum_culture_orders}
                )
                SELECT
                    matches._encounter,
                    matches._lactate_dt,
                    matches._culture_dt,
                    matches._culture_name
                FROM matches
                INNER JOIN qualifying_episodes
                    ON matches._encounter = qualifying_episodes._encounter
                    AND matches._lactate_dt = qualifying_episodes._lactate_dt
                ORDER BY
                    matches._encounter,
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
                subset=[self.config.encounter_col, "_lactate_dt"]
            ),
            "_lactate_dt",
            config.lactate_datetime_col,
            config.long_value,
        )
        culture_rows = self._long_rows(
            chosen_matches,
            "_culture_dt",
            config.blood_culture_datetime_col,
            config.long_value,
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
        )
        return self._long_rows(
            events,
            "_event_dt",
            config.datetime_col,
            config.long_value,
        )
