from src.dataloader import DataLoader
from src.events.infectiondetection import InfectionDetection
from src.events.sirs import SIRSCalculator
from src.events.aggregator import EventAggregator
from src.events.ventprocessor import VentProcessor
from src.events.organdysfunction.organdysfunction import OrganDysfunctionCalculator
from src.events.septicshock import SepticShockCalculator
from src.outlierdetection.layer1 import Layer1PhysiologicalBound

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


from src.configs.dataconfig import input_output_config, vasopressors_config
from src.configs.suspected_infection import suspected_infection_config
from src.configs.sirscalculator import sirs_config
from src.configs.aggregator import feature_config, vent_config, AggregatorConfig, agg_config
from src.configs.organdysfunction import organdysfunction_config
from src.configs.septicshock import septicshock_config
from src.configs.severitysepsis import severitysepsisconfig
from src.configs.basic import basic_analysis_config
from src.events.outlierremoval import VitalOutlierRemoval, OutlierRemovalConfig
from src.configs.outlierdetection.layer1 import physiological_bounds_config
from src.configs.fillnulls import sirs_expiration_config

from src.utils.logger import get_logger, setup_root_logger
from src.utils.utils import save_df, load_df, join_baselines_2_agg, load_output_folder, compare_column_between_two_dfs
from src.utils.fillnull import NullsFiller

import os
import polars as pl
os.environ["NUMEXPR_MAX_THREADS"] = "64"  


if __name__ == "__main__":
    