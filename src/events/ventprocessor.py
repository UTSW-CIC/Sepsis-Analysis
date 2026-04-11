import polars as pl
# from src.config import VentConfig, vent_config
from src.configs.aggregator import VentConfig, vent_config
from src.utils.logger import get_logger

logger = get_logger(__name__)

class VentProcessor():
    def __init__(self, df_all: pl.DataFrame,
                 df_agg: pl.DataFrame, # Output from EventAggregator
                 vent_config: VentConfig = vent_config):
        self.df_all=df_all
        self.df_agg = df_agg
        self.vent_config = vent_config
        self.vent_events = self._get_vent_frame()
        self.o2_events = self._get_o2_delivery_frame()

    def _get_vent_frame(self):
        return (
            self.df_all
            .filter(
                pl.col(self.vent_config.grouper_col)
                    .is_in([self.vent_config.vent_on_status, self.vent_config.vent_off_status ])
            )
            .select(
                self.vent_config.encounter_col,
                pl.col(self.vent_config.event_dt_col).alias(self.vent_config.evt_dt_col),
                pl.col(self.vent_config.grouper_col).alias(self.vent_config.evt_val_col),
            )
        )
    
    def _get_o2_delivery_frame(self):
        return (
            self.df_all
            .filter(pl.col(self.vent_config.grouper_col) == self.vent_config.o2_grouper_val)
            .select(
                self.vent_config.encounter_col,
                pl.col(self.vent_config.event_dt_col).alias(self.vent_config.evt_dt_col),
                pl.col(self.vent_config.grouper_col).alias(self.vent_config.evt_val_col),
            )
        )

    def _aggregate_vent_events(self, df_event: pl.DataFrame, ffill_nulls: bool) -> pl.DataFrame:
        joined_vent = (
            self.df_agg
            .join(df_event, on=self.vent_config.encounter_col, how="left")
            .filter(
                (pl.col(self.vent_config.evt_dt_col).is_null())|
                (pl.col(self.vent_config.evt_dt_col) <= pl.col(self.vent_config.event_dt_col))
            )
        )
        if ffill_nulls:
            joined_vent = joined_vent.sort(by=[self.vent_config.encounter_col, self.vent_config.event_dt_col, self.vent_config.evt_dt_col]).with_columns(
                pl.col(self.vent_config.evt_val_col).forward_fill().over(self.vent_config.encounter_col).fill_null(self.vent_config.vent_off_status)
            )

        joined_vent = joined_vent.select(
            self.vent_config.encounter_col,
            self.vent_config.event_dt_col,
            self.vent_config.evt_dt_col,
            self.vent_config.evt_val_col
        )

        vent_status = (
            joined_vent
            .sort(self.vent_config.evt_dt_col)
            .group_by([self.vent_config.encounter_col, self.vent_config.event_dt_col])
            .agg(
                pl.col(self.vent_config.evt_dt_col).last().alias(self.vent_config.vent_dt_alias),
                pl.col(self.vent_config.evt_val_col).last().alias(self.vent_config.vent_alias)
            )
        )
        return vent_status


    def compute(self) -> pl.DataFrame:
        logger.info("Computing Vent Status")

        logger.info("Joining vent events to the aggregated table from EventAggregator")

        vent_status = self._aggregate_vent_events(self.vent_events, ffill_nulls=True) 
        o2_status = self._aggregate_vent_events(self.o2_events, ffill_nulls=False)

        return self.df_agg.join(
            # Combine the vent and o2 status in one column
            pl.concat([vent_status, o2_status], how="vertical").sort(by=[self.vent_config.encounter_col, self.vent_config.event_dt_col]).unique(),
            on=[self.vent_config.encounter_col, self.vent_config.event_dt_col],
            how="left"
        )

        # # Vent
        # joined_vent = (
        #     self.df_agg
        #     .join(self.vent_events, on=self.vent_config.encounter_col, how="left")
        #     .filter(
        #         (pl.col(self.vent_config.evt_dt_col).is_null())|
        #         (pl.col(self.vent_config.evt_dt_col) <= pl.col(self.vent_config.event_dt_col))
        #     )
        # ).sort(by=[self.vent_config.encounter_col, self.vent_config.event_dt_col, self.vent_config.evt_dt_col]).with_columns(
        #     pl.col(self.vent_config.evt_val_col).forward_fill().over(self.vent_config.encounter_col)
        # ).select(
        #     self.vent_config.encounter_col,
        #     self.vent_config.event_dt_col,
        #     self.vent_config.evt_dt_col,
        #     self.vent_config.evt_val_col
        # )

        # vent_status = (
        #     joined_vent
        #     .sort(self.vent_config.evt_dt_col)
        #     .group_by([self.vent_config.encounter_col, self.vent_config.event_dt_col])
        #     .agg(
        #         pl.col(self.vent_config.evt_dt_col).last().alias(self.vent_config.vent_dt_alias),
        #         pl.col(self.vent_config.evt_val_col).last().alias(self.vent_config.vent_alias)
        #     )
        # )


        

        # o2 = self.df_agg.join(
        #     self.o2_events.sort(self.vent_config.o2_evt_dt_col),
        #     on=self.vent_config.encounter_col, how="left"
        # )
        # joined_o2 = (
        #     self.df_agg
        #     .join(self.o2_events, on=self.vent_config.encounter_col, how="left")
        #     .filter(pl.col(self.vent_config.evt_dt_col) <= pl.col(self.vent_config.event_dt_col))
        # )

        # Take the most recent vent e/vent for each reference point
        # vent_all = pl.concat([vent_status, self.o2_events], how="vertical").sort(by=[self.vent_config.encounter_col, self.vent_config.evt_dt_col])
        vent_all = vent_status.join(
            self.o2_events, on=self.vent_config.encounter_col, how='left', suffix='_o2'
        ).filter(
            pl.col(self.vent_config.evt_dt_col)<=pl.col(self.vent_config.event_dt_col)
        )
        vent_dt_long = vent_all.unpivot(
            on=[self.vent_config.vent_dt_alias, self.vent_config.evt_dt_col],
            index=[self.vent_config.encounter_col, self.vent_config.event_dt_col],
            variable_name= 'evt_dt_type',
            value_name='evt_dt_val'
        )

        vent_val_long = vent_all.unpivot(
            on=[self.vent_config.vent_alias, self.vent_config.evt_val_col],
            index=[self.vent_config.encounter_col, self.vent_config.event_dt_col],
            variable_name= 'evt_val_type',
            value_name='evt_val_val'
        )

        # Assert that the indices of the long dataframes match in order to concatenate them horizontally
        assert vent_dt_long.select([self.vent_config.encounter_col, self.vent_config.event_dt_col]).equals(
            vent_val_long.select([self.vent_config.encounter_col, self.vent_config.event_dt_col])
        ), "The indices of the long dataframes do not match, cannot concatenate"

        vent_long = pl.concat([vent_dt_long.drop('evt_dt_type'), vent_val_long.select('evt_val_val')], how='horizontal').rename(
            {"evt_val_val": self.vent_config.vent_alias, "evt_dt_val": self.vent_config.vent_dt_alias}
        )
        d = self.df_agg.join(vent_long, on=[self.vent_config.encounter_col, self.vent_config.event_dt_col], how="left")
        return d