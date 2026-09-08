from src_strategy.data_ingest.dataloader_1 import DataLoader
from src_strategy.configs.dataconfig import input_output_config_3_1, bp_config, data_config
from src_strategy.configs.outlierdetection.extremeoutliers import flowsheet_bounds_config, lab_bounds_config, bp_bounds_config
from src_strategy.utils.logger import setup_root_logger, get_logger
from src_strategy.utils.utils import save_df, load_df
from src_strategy.configs.collision import collision_config
from src_strategy.data_preparation.resolvecollision import ResolveCollision
from src_strategy.data_preparation.aggregator import Aggregator
from src_strategy.configs.aggregator import feature_config, agg_config
from src_strategy.configs.pulmonarydysfunction import pf_config 
from src_strategy.configs.sirscalculator import sirs_config
from src_strategy.configs.shortdurationfilter import sirs_episode_filter_config
from src_strategy.events.episode_filter import run_episode_filter
from src_strategy.events.sirs import (
    build_sirs_pipeline,
    build_sirs_state_segments,
)
from src_strategy.configs.suspected_infection import suspected_infection_config
from src_strategy.events.suspected_infection import (
    build_suspected_infection_pipeline,
)

import polars as pl

setup_root_logger(log_dir=input_output_config_3_1.logger_dir)
logger = get_logger(__name__)

# dl = DataLoader(input_output_config_3_1,
#                 data_config,
#                 bp_config,
#                 flowsheet_bounds_config,
#                 lab_bounds_config,
#                 bp_bounds_config,
#                 pf_config=pf_config)

# df_all, df_encounters = dl.load_data()
if bp_config.calculate_map:
    df_all_file_name = "df_all.parquet"
    df_all_no_collisions_file_name = "df_all_no_collisions.parquet"
    df_aggregated_file_name = "df_aggregated.parquet"
else:
    df_all_file_name = "df_all_map_measured_only.parquet"
    df_all_no_collisions_file_name = "df_all_no_collisions_map_measured_only.parquet"
    df_aggregated_file_name = "df_aggregated_map_measured_only.parquet"

# save_df(df_all, input_output_config_3_1.output_path, df_all_file_name, logger, message=f"Data injestion & Preprocessing completed, and data is saved to {input_output_config_3_1.output_path+'/'+df_all_file_name}")
# save_df(df_encounters, input_output_config_3_1.output_path, "df_encounters.parquet", logger, message=f"Encounters data is saved to {input_output_config_3_1.output_path+'/df_encounters.parquet'}")

# df_all = load_df(input_output_config_3_1.output_path, df_all_file_name)


# #================================================================================
# # TODO: Find a better way to do this
# df_all = df_all.with_columns(
#     pl.when(
#         pl.col(collision_config.grouper_col) == "Arterial Blood Pressure Mean"
#     ).then(pl.lit("Blood Pressure")).otherwise(pl.col(collision_config.grouper_col)).alias(collision_config.grouper_col)
# )

# df_all = df_all.with_columns(
#     pl.when(
#         (pl.col(collision_config.grouper_col) == "Lactate")&
#         (pl.col(collision_config.type_col) == "Procedure Order")
#     ).then(
#         pl.lit('Lactate-Procedure-Order')
#     ).otherwise(pl.col(collision_config.grouper_col)).alias(collision_config.grouper_col)
# )
# # #================================================================================


# rc = ResolveCollision(collision_config, input_output_config_3_1)
# df_all_no_collisions = rc.resolve(df_all)
# backbone = df_all_no_collisions.select([collision_config.encounter_col, collision_config.event_dt_col]).unique().sort(collision_config.encounter_col, collision_config.event_dt_col)
# save_df(df_all_no_collisions, input_output_config_3_1.output_path, df_all_no_collisions_file_name, logger,
#          message=f"Handling numerical value collisions completed, and data is saved to {input_output_config_3_1.output_path+'/'+df_all_no_collisions_file_name}")
# save_df(backbone, input_output_config_3_1.output_path, "backbone.parquet", logger,
#          message=f"Backbone (unique encounter, event_dt) is saved to {input_output_config_3_1.output_path+'/backbone.parquet'}")
# df_all_no_collisions = load_df(input_output_config_3_1.output_path, df_all_no_collisions_file_name)
# backbone = load_df(input_output_config_3_1.output_path, "backbone.parquet")

# suspected_infection_pipeline = build_suspected_infection_pipeline(
#     suspected_infection_config
# )
# df_suspected_infection = suspected_infection_pipeline.process(
#     df_all_no_collisions
# )
# save_df(
#     df_suspected_infection,
#     input_output_config_3_1.output_path,
#     "df_suspected_infection.parquet",
#     logger,
#     message="Suspected-infection detection completed",
# )
# agg = Aggregator(
#     agg_config,
#     feature_config
# )
# df_aggregated = agg.aggregate(df_all_no_collisions, backbone)
# save_df(df_aggregated, input_output_config_3_1.output_path, df_aggregated_file_name, logger,
#          message=f"Aggregation completed, and data is saved to {input_output_config_3_1.output_path+'/'+df_aggregated_file_name}")

df_aggregated = load_df(input_output_config_3_1.output_path, df_aggregated_file_name)

sirs_pipeline = build_sirs_pipeline(sirs_config)
df_sirs = sirs_pipeline.process(df_aggregated)
save_df(df_sirs, input_output_config_3_1.output_path, "df_sirs.parquet", logger,
         message=f"SIRS calculation completed, and data is saved to {input_output_config_3_1.output_path+'/df_sirs.parquet'}")

# Short-duration filtering is an exploratory, status-level analysis. It remains
# disabled by default and does not replace df_sirs or feed classification.
if sirs_episode_filter_config.enabled:
    df_sirs_segments = build_sirs_state_segments(df_sirs, config=sirs_config)
    sirs_episode_results = run_episode_filter(
        df_sirs_segments,
        config=sirs_episode_filter_config,
    )
    save_df(
        sirs_episode_results['raw'], input_output_config_3_1.output_path, "df_sirs_segments_raw.parquet", logger, message="SIRS state-segment reconstruction completed"
    )
    save_df(
        sirs_episode_results['merged'], input_output_config_3_1.output_path, "df_sirs_segments_merged.parquet", logger, message="SIRS state-segment merge completed"
    )
    save_df(
        sirs_episode_results['filtered'], input_output_config_3_1.output_path, "df_sirs_segments_filtered.parquet", logger, message="SIRS state-segment filtering completed"
    )
    # save_df(
    #     df_sirs_segments,
    #     input_output_config_3_1.output_path,
    #     "df_sirs_segments.parquet",
    #     logger,
    #     message="SIRS state-segment reconstruction completed",
    # )
    # for stage, episode_df in sirs_episode_results.items():
    #     output_name = (
    #         f"df_{sirs_episode_filter_config.status_name}"
    #         f"_episodes_{stage}.parquet"
    #     )
    #     save_df(
    #         episode_df,
    #         input_output_config_3_1.output_path,
    #         output_name,
    #         logger,
    #         message=f"SIRS episode-filter stage '{stage}' completed",
    #     )

x = 0
