import polars as pl
from src.utils.utils import extract_systolic_bp, rolling_agg, extract_arterial_blood_pressure_mean
# from src.config import feature_config, FeatureConfig, AggregatorConfig, agg_config
from src.configs.aggregator import FeatureConfig, AggregatorConfig 
from src.utils.logger import get_logger

logger = get_logger(__name__)

class EventAggregator():
    def __init__(self, df_all: pl.DataFrame,
                  data_config: AggregatorConfig,
                  feature_config: FeatureConfig):
        self.df_all = df_all
        self.data_config = data_config
        self.feature_config = feature_config

        self.is_missing_sbp = self._check_missing_sbp()

    def _check_missing_sbp(self) -> bool: 
        df_sbp = self.df_all.filter(
                pl.col(self.data_config.grouper_col) == self.data_config.blood_pressure_config.bp_grouper_val
        )
        missing_sbp = df_sbp.filter(pl.col(self.data_config.val_col).is_null()).shape[0]
        return missing_sbp/len(df_sbp) > 0.1

    def _prepare_event_table(self, feat_name: str) -> pl.DataFrame:
        if feat_name == "Systolic Blood Pressure": 
            feat_name = self.data_config.blood_pressure_config.bp_grouper_val
            if self.is_missing_sbp:
                return extract_systolic_bp(self.df_all, self.data_config).select(
                    pl.col(self.data_config.encounter_col),
                    pl.col(self.data_config.event_dt_col).alias(self.data_config.evt_dt_col),
                    pl.col(self.data_config.blood_pressure_config.sys_col).alias(self.data_config.evt_val_col)
                )
            else:
                return self.df_all.filter(pl.col(self.data_config.grouper_col).is_in([feat_name]) & pl.col(self.data_config.val_col).is_not_null()).select(
                    pl.col(self.data_config.encounter_col),
                    pl.col(self.data_config.event_dt_col).alias(self.data_config.evt_dt_col),
                    pl.col(self.data_config.val_col).alias(self.data_config.evt_val_col)
            )

        if feat_name == "Arterial Blood Pressure Mean":
            return extract_arterial_blood_pressure_mean(self.df_all, self.data_config).select(
            pl.col(self.data_config.encounter_col),
            pl.col(self.data_config.event_dt_col).alias(self.data_config.evt_dt_col),
            pl.col(self.data_config.blood_pressure_config.map_col).alias(self.data_config.evt_val_col)
        )

        return (
            self.df_all.filter(pl.col(self.data_config.grouper_col).is_in([feat_name]) & pl.col(self.data_config.val_col).is_not_null())
            .select(pl.col(self.data_config.encounter_col), pl.col(self.data_config.event_dt_col).alias("evt_dt"), pl.col(self.data_config.val_col).alias("evt_val"))
        )

    def aggregate(self) -> pl.DataFrame:
        reference = self.df_all.select([self.data_config.encounter_col, self.data_config.event_dt_col]).unique()
        logger.info(f"Created reference table with {reference.shape[0]} rows based on unique combinations of {self.data_config.encounter_col} and {self.data_config.event_dt_col}")
        self.features_dict_ = {}

        # aggregate features according to config
        for feature in self.feature_config.rolling_metrics:
            logger.info(f"Aggregating feature {feature.alias} using {feature.agg} over last {feature.lookback_period} minutes for events in {feature.event_grouper}")
            if feature.event_grouper == "Arterial Blood Pressure Mean" or feature.event_grouper == "Systolic Blood Pressure":
                x = 0
            df_ev = self._prepare_event_table(feature.event_grouper)
            if len(df_ev) < 1000:
                logger.warning(f"Only {len(df_ev)} events found for feature {feature.alias}. Check if the event_grouper value is correct and if there are enough events in the data.")
            df_feature = rolling_agg(
                reference=reference,
                events= df_ev,
                agg_col_name=feature.alias,
                agg_func=feature.agg,
                lookback_period=feature.lookback_period,
                encounter_col=self.data_config.encounter_col,
                ref_dt_col=self.data_config.event_dt_col,
                evt_dt_col=self.data_config.evt_dt_col,
                evt_val_col=self.data_config.evt_val_col
            )
            logger.info(f"Joining aggregated feature {feature.alias} back to reference table")
            reference = reference.join(df_feature, on=[self.data_config.encounter_col, self.data_config.event_dt_col], how="left")
            logger.info(f"Feature {feature.alias} aggregated and joined. Current reference table now has {reference.shape[0]} rows and {reference.shape[1]} columns.")
            logger.info("--------------------------------------------------------------------------------")
            self.features_dict_[feature.alias] = feature

        logger.info("All features aggregated and joined back to reference table.")
        return reference