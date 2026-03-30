import polars as pl
from src.config import VentConfig, vent_config
from src.utils.logger import get_logger

logger = get_logger(__name__)

class VentProcessor():
    def __init__(self, df_all: pl.DataFrame,
                 df_agg: pl.DataFrame, # Output from EventAggregator
                 vent_config: VentConfig = vent_config):
        self.df_all=df_all
        self.df_agg = df_agg
        self.vent_config = vent_config
        self.vent_events = self._get_event_frame()

    def _get_event_frame(self):
        return  (
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

    def compute(self) -> pl.DataFrame:
        logger.info("Computing Vent Status")

        logger.info("Joining vent events to the aggregated table from EventAggregator")
        joined_vent = (
            self.df_agg
            .join(self.vent_events, on=self.vent_config.encounter_col, how="left")
            .filter(pl.col(self.vent_config.evt_dt_col) <= pl.col(self.vent_config.event_dt_col))
        )

        # Take the most recent vent e/vent for each reference point
        vent_status = (
            joined_vent
            .sort(self.vent_config.evt_dt_col)
            .group_by([self.vent_config.encounter_col, self.vent_config.event_dt_col])
            .agg(pl.col(self.vent_config.evt_val_col).last().alias(self.vent_config.alias))
        )

        return self.df_agg.join(vent_status,
                                 on=[self.vent_config.encounter_col,
                                      self.vent_config.event_dt_col], how="left")