from src.dataloader import DataLoader
from src.events.infectiondetection import InfectionDetection
from src.events.sirs import SIRSCalculator
from src.events.aggregator import EventAggregator
from src.events.ventprocessor import VentProcessor
from src.events.organdysfunction.organdysfunction import OrganDysfunctionCalculator
from src.events.septicshock import SepticShockCalculator
from src.outlierdetection.layer1 import Layer1PhysiologicalBound
from src.events.vento2delivery import VentO2Delivery

from src.events.severitysepsisflag import SeveritySepsisFlag
from src.events.analysis import Analysis

from src.analysis.basic import BasicAnalysis

import polars as pl

def combine_sepsis123(df_s1, df_s2, df_s3):
    import polars as pl
    df_s1_first = df_s1.group_by("EncounterEpicCsn").agg(pl.col("earliest_sepsis1_instance").min().alias("first_sepsis_instant")).with_columns(
        pl.lit(1).alias("sepsis_score")
    )
    df_s2_first = df_s2.group_by("EncounterEpicCsn").agg(pl.col("earliest_sepsis2_instance").min().alias("first_sepsis_instant")).with_columns(
        pl.lit(2).alias("sepsis_score")
    )
    df_s3_first = df_s3.group_by("EncounterEpicCsn").agg(pl.col("earliest_sepsis3_instance").min().alias("first_sepsis_instant")).with_columns(
        pl.lit(3).alias("sepsis_score")
    )
    df_sepsis_all = pl.concat([df_s1_first, df_s2_first, df_s3_first], how='vertical')
    df_min = df_sepsis_all.join(
        df_sepsis_all.group_by("EncounterEpicCsn").agg(pl.col("first_sepsis_instant").min().alias("first_of_all")),
        on="EncounterEpicCsn"
    ).filter(pl.col("first_sepsis_instant")==pl.col("first_of_all"))
    df_min = df_min.filter(pl.col("EncounterEpicCsn").is_duplicated()).sort(by='EncounterEpicCsn')
    x = 0


#TODO: Old configuration to be removed after testing the code
# from src.config import (input_output_config, feature_config, SIRSConfig,
#                         OrganDysfunctionConfig, organdysfunction_config,
#                         vent_config, septicshock_config)

# from src.config import (feature_config, SIRSConfig,
#                         OrganDysfunctionConfig, organdysfunction_config,
#                         vent_config, septicshock_config)


from src.configs.dataconfig import input_output_config, input_output_config_2, vasopressors_config
from src.configs.suspected_infection import suspected_infection_config
from src.configs.sirscalculator import sirs_config, sirs_postagg_config
from src.configs.aggregator import feature_config, vent_config, AggregatorConfig, agg_config
from src.configs.organdysfunction import organdysfunction_config
from src.configs.septicshock import septicshock_config
from src.configs.severitysepsis import severitysepsisconfig
from src.configs.basic import basic_analysis_config
from src.events.outlierremoval import VitalOutlierRemoval, OutlierRemovalConfig
from src.configs.outlierdetection.layer1 import physiological_bounds_config
from src.configs.fillnulls import sirs_expiration_config
from src.configs.pulmonarydysfunction import pulmonary_dysfunction_config

from src.utils.logger import get_logger, setup_root_logger
from src.utils.utils import save_df, load_df, join_baselines_2_agg, load_output_folder, compare_column_between_two_dfs
from src.utils.fillnull import NullsFiller

import os
import polars as pl
os.environ["NUMEXPR_MAX_THREADS"] = "64"  

setup_root_logger(log_dir=input_output_config_2.logger_dir)
logger = get_logger(__name__)

if __name__ == "__main__":
    # # logger.info("Starting pipeline")
    # dl = DataLoader(input_output_config_2)
    # df_all = dl.load_data()
    # save_df(df_all, input_output_config_2.output_path, "df_all.parquet", logger, message="Initial data loaded.")
    # logger.info("=================================================================================")
    # # df_all = load_df(input_output_config.output_path, "df_all.parquet", logger)

    # # Apply outlier removal for vital signs before any calculations, as vitals are used in multiple downstream steps and we want to ensure consistency
    # layer1 = Layer1PhysiologicalBound(physiological_bounds_config)
    # df_all_layer1 = layer1.apply(df_all, inplace=False) 
    # diff_cnts = compare_column_between_two_dfs(df_all,
    #                                            df_all_layer1,
    #                                            physiological_bounds_config.grouper_col,
    #                                            physiological_bounds_config.encounter_col,
    #                                            physiological_bounds_config.val_col,
    #                                            "original",
    #                                            "clone",
    #                                            pl.col(f"original_{physiological_bounds_config.val_col}").is_not_null() & pl.col(f"clone_{physiological_bounds_config.val_col}").is_null(),
    #                                            None)
    # logger.info(f"Groupers with outlier values: {diff_cnts}") 
    # save_df(df_all_layer1, input_output_config_2.output_path, "df_all_layer1.parquet", logger, message="Layer 1 (Physiological bounds of vital signs) outlier removal applied.")
    # logger.info("=================================================================================")
    # # df_all_layer1 = load_df(input_output_config_2.output_path, "df_all_layer1.parquet", logger)
    # # df_all = load_df(input_output_config_2.output_path, "df_all.parquet", logger)


    # df_infect = InfectionDetection(df_all_layer1, suspected_infection_config).detect_infection_longframe()
    # save_df(df_infect, input_output_config_2.output_path, "df_infect_long.parquet", logger, message="Infection data detected.")
    # logger.info("=================================================================================")

    
    # # sirs_config.hr_flag_col = "Pule_High_Flag"
    # # sirs_calculator = SIRSCalculator(df_all_layer1, sirs_config)
    # # df_sirs = sirs_calculator.calculate_sirs_flags()
    # # save_df(df_sirs, input_output_config_2.output_path, "df_sirs.parquet", logger, message="SIRS flags calculated.")
    # # logger.info("=================================================================================")

    # # null_fillers = NullsFiller(sirs_expiration_config)
    # # df_sirs_filled = null_fillers.fill_nulls(df_sirs)
    # # save_df(df_sirs_filled, input_output_config_2.output_path, "df_sirs_filled.parquet", logger, message="SIRS flags after filling nulls calculated.")

    # # # Analysis of the filled sirs vals
    # # df_comb = pl.concat([df_sirs.sort(by=['EncounterEpicCsn', 'Event_DateTime']).select("EncounterEpicCsn", "Event_DateTime", "Event_Grouper", "NumericValue"), df_sirs_filled.select(pl.col("EncounterEpicCsn").alias("filled_enc_id"), pl.col("Event_DateTime").alias("filled_event_dt"), pl.col("Event_Grouper").alias("filled_event_grpr"), pl.col("NumericValue").alias("filled_num_val"))], how='horizontal')
    # # grouper_cnts = df_comb.filter(pl.col("NumericValue").is_null()&pl.col("filled_num_val").is_not_null())['Event_Grouper'].value_counts()
    # # logger.info(f"Groupers for which null values were filled: {grouper_cnts}")
    # # logger.info("=================================================================================")
    # # df_sirs_filled = load_df(input_output_config_2.output_path, "df_sirs_filled.parquet", logger)


    # ev_agg = EventAggregator(df_all_layer1, agg_config, feature_config)
    # df_agg = ev_agg.aggregate()
    # save_df(df_agg, input_output_config.output_path, "df_agg.parquet", logger, message="Aggregated features saved.")
    # logger.info("=================================================================================")
    # # df_agg = load_df(input_output_config.output_path, "df_agg.parquet", logger)

    # sirs_calculator = SIRSCalculator(df_agg, sirs_postagg_config)
    # df_sirs = sirs_calculator.calculate_sirs_flags()
    # save_df(df_sirs, input_output_config_2.output_path, "df_sirs_postagg.parquet", logger, message="SIRS flags calculated after aggregation.")
    # logger.info("=================================================================================")


    # vent_proc = VentO2Delivery(df_all_layer1, pulmonary_dysfunction_config)
    # df_o2vent = vent_proc.process()
    # save_df(df_o2vent, input_output_config_2.output_path, "df_o2vent.parquet", logger, message="Vent ")
    # logger.info("=================================================================================")

    # # df_agg_vent = load_df(input_output_config.output_path, "df_agg_vent.parquet", logger)
    # # # # # # df_agg_vent = load_df(input_output_config.output_path, "df_agg_vent.parquet", logger)
    # # df_agg_vent_baselines = join_baselines_2_agg(df_agg_vent, df_all_layer1, organdysfunction_config.encounter_col,
    # #                                               organdysfunction_config.baseline.columns, logger)

    # # df_vent_baseline = join_baselines_2_agg(df_o2vent, df_all_layer1, organdysfunction_config.encounter_col, organdysfunction_config.baseline.columns, logger)

    # # drop_cols = []
    # # for c in [c for c in df_vent_baseline.columns if c.endswith('_right') or c.endswith('_1')]:
    # #     drop_cols.append(c)
    # # df_vent_baseline = df_vent_baseline.drop(drop_cols)

    # # organdysfunction_obj = OrganDysfunctionCalculator(df_agg_vent_baselines, df_all, organdysfunction_config)
    # organdysfunction_obj = OrganDysfunctionCalculator(df_agg, df_all, organdysfunction_config)
    # df_organdysfunction = organdysfunction_obj.calculate()
    # save_df(df_organdysfunction, input_output_config_2.output_path, "df_organdysfunction.parquet", logger, message="Organ dysfunction labels saved.")
    # logger.info("=================================================================================")

    # septicshock_obj = SepticShockCalculator(df_organdysfunction, septicshock_config)
    # df_septicshock = septicshock_obj.calculate()
    # save_df(df_septicshock, input_output_config_2.output_path, "df_septicshock.parquet", logger, message="Septic shock labels saved.")

    # df_dict = load_output_folder(input_output_config_2.output_path, logger)

    # sepsis_obj = SeveritySepsisFlag(df_dict['df_infect_long'], df_dict['df_sirs_postagg'],
    #                                 df_dict['df_organdysfunction'], df_dict['df_o2vent'], df_dict['df_septicshock'], severitysepsisconfig)
    # df_sepsis1, df_sepsis2, df_sepsis3 = sepsis_obj.compute()
    # save_df(df_sepsis1, input_output_config_2.output_path, "df_sepsis1.parquet", logger, message="Sepsis 1 labels saved.")
    # save_df(df_sepsis2, input_output_config_2.output_path, "df_sepsis2.parquet", logger, message="Sepsis 2 labels saved.")
    # save_df(df_sepsis3, input_output_config_2.output_path, "df_sepsis3.parquet", logger, message="Sepsis 3 labels saved.")
    # logger.info("=================================================================================")
    # df_dict = load_output_folder(input_output_config.output_path, logger)
    
    # # # df_sepsis_all = combine_sepsis123(df_dict['df_sepsis1'], df_dict['df_sepsis2'], df_dict['df_sepsis3'])

    # # # basic_analysis = BasicAnalysis(input_output_config.output_path, basic_analysis_config)
    # # # basic_analysis.analyze()

    analysis = Analysis(input_output_config_2.output_path, basic_analysis_config)
    analysis.analyze()
