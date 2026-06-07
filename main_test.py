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
from src.configs.dataconfig import input_output_config
from src.dataloader import DataLoader
from src.utils.utils import load_df
from src.utils.logger import get_logger 

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

setup_root_logger(log_dir=input_output_config.logger_dir)
logger = get_logger(__name__)

def load_data():
    df_all_layer1 = load_df(input_output_config.output_path, "df_all_layer1.parquet", logger)
    df_all = load_df(input_output_config.output_path, "df_all.parquet", logger)
    df_sirs_filled = load_df(input_output_config.output_path, "df_sirs_filled.parquet", logger)
    df_agg = load_df(input_output_config.output_path, "df_agg.parquet", logger)
    return {
        'df_all': df_all,
        'df_all_layer1': df_all_layer1,
        'df_sirs_filled': df_sirs_filled,
        'df_agg': df_agg
    }

def analyze_layer1(df_all, df_all_layer1):
    #TODO: What was the purpose of this layer?
    enc_id = physiological_bounds_config.encounter_col
    grouper_col = physiological_bounds_config.grouper_col
    evt_dt = physiological_bounds_config.event_datetime_col
    
    for vital in physiological_bounds_config.REQUIRED_SIGNALS:
        df_all.filter(pl.col(grouper_col) == vital).select(
            pl.col(enc_id),
        ).unique()
    x = 0
    

# Find values that occurred at the same instant with different values
def get_conflict_values_at_same_instant(
        df_sirs_filled: pl.DataFrame,
        df_agg: pl.DataFrame,
        enc_id: str, 
        event_dt: str,
        event_grouper_col: str,
        grouper_val: str,
        value_col: str,
        agg_key: str, # In the form of "last_temp_8h"
        
):
    df_sirs_grpr = df_sirs_filled.filter(
        pl.col("Event_Grouper") == grouper_val
    ).select(
       enc_id, event_dt, event_grouper_col, value_col 
    ).sort(by=[enc_id, event_dt])

    df_agg_grp = df_agg.select(
        enc_id, event_dt, agg_key
    ).sort(by=[enc_id, event_dt])
    
    return df_sirs_grpr.join(
        df_agg_grp,
        on=['EncounterEpicCsn', "Event_DateTime"],
        how='inner'
    ).filter(pl.col("NumericValue")!=pl.col(agg_key))
    
if __name__ == '__main__':
    df_dict = load_data()
    # analyze_layer1(df_dict['df_all'], df_dict['df_all_layer1'])
    df_conflict_grb = get_conflict_values_at_same_instant(
        df_sirs_filled=df_dict['df_sirs_filled'],
        df_agg=df_dict['df_agg'],
        enc_id="EncounterEpicCsn",
        event_dt="Event_DateTime",
        event_grouper_col="Event_Grouper",
        grouper_val="Respirations",
        value_col="NumericValue",
        agg_key="last_resp_8h"
    )
    x = 0
