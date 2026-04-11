from src.dataloader import DataLoader
from src.events.infectiondetection import InfectionDetection
from src.events.sirs import SIRSCalculator
from src.events.aggregator import EventAggregator
from src.events.ventprocessor import VentProcessor
from src.events.organdysfunction.organdysfunction import OrganDysfunctionCalculator
from src.events.septicshock import SepticShockCalculator

from src.events.severitysepsisflag import SeveritySepsisFlag

from src.analysis.basic import BasicAnalysis


#TODO: Old configuration to be removed after testing the code
# from src.config import (input_output_config, feature_config, SIRSConfig,
#                         OrganDysfunctionConfig, organdysfunction_config,
#                         vent_config, septicshock_config)

# from src.config import (feature_config, SIRSConfig,
#                         OrganDysfunctionConfig, organdysfunction_config,
#                         vent_config, septicshock_config)


from src.configs.dataconfig import input_output_config
from src.configs.suspected_infection import suspected_infection_config
from src.configs.sirscalculator import sirs_config
from src.configs.aggregator import feature_config, vent_config, AggregatorConfig, agg_config
from src.configs.organdysfunction import organdysfunction_config
from src.configs.septicshock import septicshock_config
from src.configs.severitysepsis import severitysepsisconfig

from src.utils.logger import get_logger, setup_root_logger
from src.utils.utils import save_df, load_df, join_baselines_2_agg, load_output_folder

import os
os.environ["NUMEXPR_MAX_THREADS"] = "16"  

setup_root_logger(log_dir=input_output_config.logger_dir)
logger = get_logger(__name__)

if __name__ == "__main__":
    # logger.info("Starting pipeline")
    # dl = DataLoader(input_output_config)
    # df_all = dl.load_data()
    # save_df(df_all, input_output_config.output_path, "df_all.parquet", logger, message="Initial data loaded.")
    # logger.info("=================================================================================")
    df_all = load_df(input_output_config.output_path, "df_all.parquet", logger)

    # df_infect = InfectionDetection(df_all, suspected_infection_config).detect_infection()
    # save_df(df_infect, input_output_config.output_path, "df_infect.parquet", logger, message="Infection data detected.")
    # logger.info("=================================================================================")

    # # # sirs_config = SIRSConfig()
    # sirs_config.hr_flag_col = "Pule_High_Flag"
    # sirs_calculator = SIRSCalculator(df_all, sirs_config)
    # df_sirs = sirs_calculator.calculate_sirs_flags()
    # save_df(df_sirs, input_output_config.output_path, "df_sirs.parquet", logger, message="SIRS flags calculated.")
    # logger.info("=================================================================================")

    # ev_agg = EventAggregator(df_all, agg_config, feature_config)
    # df_agg = ev_agg.aggregate()
    # save_df(df_agg, input_output_config.output_path, "df_agg.parquet", logger, message="Aggregated features saved.")
    # logger.info("=================================================================================")
    # # df_agg = load_df(input_output_config.output_path, "df_agg.parquet", logger)

    # vent_proc = VentProcessor(df_all, df_agg, vent_config)
    # df_agg_vent = vent_proc.compute()

    # save_df(df_agg_vent, input_output_config.output_path, "df_agg_vent.parquet", logger, message="Aggregated features with vent status saved.")
    # logger.info("=================================================================================")

    # # df_agg_vent = load_df(input_output_config.output_path, "df_agg_vent.parquet", logger)

    # # df_agg_vent = load_df(input_output_config.output_path, "df_agg_vent.parquet", logger)

    # df_agg_vent_baselines = join_baselines_2_agg(df_agg_vent, df_all, organdysfunction_config.encounter_col,
    #                                               organdysfunction_config.baseline.columns, logger)

    # drop_cols = []
    # for c in [c for c in df_agg_vent_baselines.columns if c.endswith('_right') or c.endswith('_1')]:
    #     drop_cols.append(c)
    # df_agg_vent_baselines = df_agg_vent_baselines.drop(drop_cols)

    # organdysfunction_obj = OrganDysfunctionCalculator(df_agg_vent_baselines, df_all, organdysfunction_config)
    # df_organdysfunction = organdysfunction_obj.calculate()
    # save_df(df_organdysfunction, input_output_config.output_path, "df_organdysfunction.parquet", logger, message="Organ dysfunction labels saved.")
    # logger.info("=================================================================================")

    # septicshock_obj = SepticShockCalculator(df_agg_vent_baselines, septicshock_config)
    # df_septicshock = septicshock_obj.calculate()

    # save_df(df_septicshock, input_output_config.output_path, "df_septicshock.parquet", logger, message="Septic shock labels saved.")

    df_dict = load_output_folder(input_output_config.output_path, logger)

    sepsis_obj = SeveritySepsisFlag(df_dict['df_infect'], df_dict['df_sirs'],
                                    df_dict['df_organdysfunction'], df_dict['df_septicshock'], severitysepsisconfig)
    df_sepsis = sepsis_obj.compute()
    # df_sepsis = sepsis_obj._sepsis_1()
    # save_df(df_sepsis, input_output_config.output_path, "df_sepsis.parquet", logger, message="Sepsis labels saved.")
    # logger.info("=================================================================================")


    # df_dict = load_output_folder(input_output_config.output_path, logger)

    # basic_analysis = BasicAnalysis(input_output_config.output_path)
    # basic_analysis.analyze()