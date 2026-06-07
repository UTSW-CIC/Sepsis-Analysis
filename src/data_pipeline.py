# main.py
import os
import polars as pl

os.environ["NUMEXPR_MAX_THREADS"] = "64"

from src.dataloader import DataLoader
from src.events.infectiondetection import InfectionDetection
from src.events.sirs import SIRSCalculator
from src.events.aggregator import EventAggregator
from src.events.vento2delivery import VentO2Delivery
from src.events.organdysfunction.organdysfunction import OrganDysfunctionCalculator
from src.events.septicshock import SepticShockCalculator
from src.events.severitysepsisflag import SeveritySepsisFlag
from src.outlierdetection.layer1 import Layer1PhysiologicalBound
from src.utils.logger import get_logger, setup_root_logger
from src.utils.utils import save_df, compare_column_between_two_dfs


def run_pipeline(
    io_config,
    physiological_bounds_config,
    suspected_infection_config,
    agg_config,
    feature_config,
    sirs_postagg_config,
    pulmonary_dysfunction_config,
    organdysfunction_config,
    septicshock_config,
    severitysepsisconfig,
):
    setup_root_logger(log_dir=io_config.logger_dir)
    logger = get_logger("pipeline")

    # 1. Load data
    dl = DataLoader(io_config)
    df_all = dl.load_data()
    save_df(df_all, io_config.output_path, "df_all.parquet", logger, message="Initial data loaded.")
    logger.info("=" * 80)

    # 2. Outlier removal
    layer1 = Layer1PhysiologicalBound(physiological_bounds_config)
    df_all_layer1 = layer1.apply(df_all, inplace=False)
    diff_cnts = compare_column_between_two_dfs(
        df_all, df_all_layer1,
        physiological_bounds_config.grouper_col,
        physiological_bounds_config.encounter_col,
        physiological_bounds_config.val_col,
        "original", "clone",
        pl.col(f"original_{physiological_bounds_config.val_col}").is_not_null()
        & pl.col(f"clone_{physiological_bounds_config.val_col}").is_null(),
        None,
    )
    logger.info(f"Groupers with outlier values: {diff_cnts}")
    save_df(df_all_layer1, io_config.output_path, "df_all_layer1.parquet", logger, message="Layer 1 outlier removal applied.")
    logger.info("=" * 80)

    # 3. Infection detection
    df_infect = InfectionDetection(df_all_layer1, suspected_infection_config).detect_infection_longframe()
    save_df(df_infect, io_config.output_path, "df_infect_long.parquet", logger, message="Infection data detected.")
    logger.info("=" * 80)

    # 4. Aggregation
    ev_agg = EventAggregator(df_all_layer1, agg_config, feature_config)
    df_agg = ev_agg.aggregate()
    save_df(df_agg, io_config.output_path, "df_agg.parquet", logger, message="Aggregated features saved.")
    logger.info("=" * 80)

    # 5. SIRS (post-aggregation)
    sirs_calculator = SIRSCalculator(df_agg, sirs_postagg_config)
    df_sirs = sirs_calculator.calculate_sirs_flags()
    save_df(df_sirs, io_config.output_path, "df_sirs_postagg.parquet", logger, message="SIRS flags calculated.")
    logger.info("=" * 80)

    # 6. Vent / O2 delivery
    vent_proc = VentO2Delivery(df_all_layer1, pulmonary_dysfunction_config)
    df_o2vent = vent_proc.process()
    save_df(df_o2vent, io_config.output_path, "df_o2vent.parquet", logger, message="Vent O2 delivery processed.")
    logger.info("=" * 80)

    # 7. Organ dysfunction
    organdysfunction_obj = OrganDysfunctionCalculator(df_agg, df_all, organdysfunction_config)
    df_organdysfunction = organdysfunction_obj.calculate()
    save_df(df_organdysfunction, io_config.output_path, "df_organdysfunction.parquet", logger, message="Organ dysfunction labels saved.")
    logger.info("=" * 80)

    # 8. Septic shock
    septicshock_obj = SepticShockCalculator(df_organdysfunction, septicshock_config)
    df_septicshock = septicshock_obj.calculate()
    save_df(df_septicshock, io_config.output_path, "df_septicshock.parquet", logger, message="Septic shock labels saved.")
    logger.info("=" * 80)

    # 9. Severity / sepsis flags
    sepsis_obj = SeveritySepsisFlag(
        df_infect, df_sirs, df_organdysfunction, df_o2vent, df_septicshock,
        severitysepsisconfig,
    )
    df_sepsis1, df_sepsis2, df_sepsis3 = sepsis_obj.compute()
    save_df(df_sepsis1, io_config.output_path, "df_sepsis1.parquet", logger, message="Sepsis 1 labels saved.")
    save_df(df_sepsis2, io_config.output_path, "df_sepsis2.parquet", logger, message="Sepsis 2 labels saved.")
    save_df(df_sepsis3, io_config.output_path, "df_sepsis3.parquet", logger, message="Sepsis 3 labels saved.")
    logger.info("=" * 80)

    logger.info("Pipeline complete.")

    return {
        "df_all": df_all,
        "df_all_layer1": df_all_layer1,
        "df_infect": df_infect,
        "df_agg": df_agg,
        "df_sirs": df_sirs,
        "df_o2vent": df_o2vent,
        "df_organdysfunction": df_organdysfunction,
        "df_septicshock": df_septicshock,
        "df_sepsis1": df_sepsis1,
        "df_sepsis2": df_sepsis2,
        "df_sepsis3": df_sepsis3,
    }


if __name__ == "__main__":
    # Import your configs here (or from a dashboard, CLI, etc.)
    from src.configs.dataconfig import input_output_config_2
    from src.configs.suspected_infection import suspected_infection_config
    from src.configs.sirscalculator import sirs_postagg_config
    from src.configs.aggregator import feature_config, agg_config
    from src.configs.organdysfunction import organdysfunction_config
    from src.configs.septicshock import septicshock_config
    from src.configs.severitysepsis import severitysepsisconfig
    from src.configs.outlierdetection.layer1 import physiological_bounds_config
    from src.configs.pulmonarydysfunction import pulmonary_dysfunction_config

    results = run_pipeline(
        io_config=input_output_config_2,
        physiological_bounds_config=physiological_bounds_config,
        suspected_infection_config=suspected_infection_config,
        agg_config=agg_config,
        feature_config=feature_config,
        sirs_postagg_config=sirs_postagg_config,
        pulmonary_dysfunction_config=pulmonary_dysfunction_config,
        organdysfunction_config=organdysfunction_config,
        septicshock_config=septicshock_config,
        severitysepsisconfig=severitysepsisconfig,
    )
