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
from src_strategy.configs.pulmonarydysfunction import pulmonary_dysfunction_config
from src_strategy.configs.organdysfunction import organdysfunction_config
from src_strategy.data_preparation import PFRatioBuilder
from src_strategy.events.organdysfunction import (
    build_organ_dysfunction_pipeline,
    prepare_organ_dysfunction_input,
)
from src_strategy.events.pulmonarydysfunction import (
    attach_pulmonary_state,
    build_pulmonary_state_segments,
    build_pulmonary_state_timeline,
)
from src_strategy.configs.sirscalculator import sirs_config
from src_strategy.configs.shortdurationfilter import sirs_episode_filter_config
from src_strategy.events.episode_filter import run_episode_filter
from src_strategy.events.sirs import (
    build_sirs_pipeline,
    build_sirs_state_segments,
)
from pathlib import Path

from src_strategy.configs.septicshock import septicshock_config
from src_strategy.configs.shortdurationfilter import (
    bp_episode_filter_config,
    sirs_episode_filter_config,
)
from src_strategy.events.hypotension import build_bp_state_segments

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
#                 bp_bounds_config)

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
# df_pf_events = PFRatioBuilder(pf_config).build(df_all_no_collisions)
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

# Pulmonary evidence must be constructed from the collision-free event table,
# while its reconstructed state is attached to the temporal aggregate table.
df_all_no_collisions = load_df(
    input_output_config_3_1.output_path,
    df_all_no_collisions_file_name,
)
df_pf_events = PFRatioBuilder(pf_config).build(df_all_no_collisions)
df_pulmonary_state_timeline = build_pulmonary_state_timeline(
    df_all_no_collisions,
    df_pf_events,
    config=pulmonary_dysfunction_config,
)
df_pulmonary_state_segments = build_pulmonary_state_segments(
    df_all_no_collisions,
    df_pf_events,
    config=pulmonary_dysfunction_config,
)
df_aggregated_with_pulmonary = attach_pulmonary_state(
    df_aggregated,
    df_pulmonary_state_timeline,
    config=pulmonary_dysfunction_config,
)

df_encounters = load_df(
    input_output_config_3_1.output_path,
    "df_encounters.parquet",
)
df_organ_dysfunction_input = prepare_organ_dysfunction_input(
    df_aggregated_with_pulmonary,
    df_encounters,
    config=organdysfunction_config,
)
df_organ_dysfunction = build_organ_dysfunction_pipeline(
    organdysfunction_config
).process(df_organ_dysfunction_input)

pulmonary_outputs = {
    "df_pf_events_v1.parquet": df_pf_events,
    "df_pulmonary_state_timeline_v1.parquet": df_pulmonary_state_timeline,
    "df_pulmonary_state_segments_v1.parquet": df_pulmonary_state_segments,
    "df_aggregated_with_pulmonary_v1.parquet": df_aggregated_with_pulmonary,
    "df_organ_dysfunction_v1.parquet": df_organ_dysfunction,
}

# Safety decision: pulmonary integration uses new versioned filenames and
# refuses the entire save operation if any target exists. No output is partly
# updated due to an existing target, and no prior artifact is overwritten.
existing_pulmonary_outputs = [
    filename
    for filename in pulmonary_outputs
    if (Path(input_output_config_3_1.output_path) / filename).exists()
]
if existing_pulmonary_outputs:
    raise FileExistsError(
        "Refusing to overwrite existing pulmonary outputs: "
        f"{existing_pulmonary_outputs}"
    )

for filename, dataframe in pulmonary_outputs.items():
    save_df(
        dataframe,
        input_output_config_3_1.output_path,
        filename,
        logger,
        message=f"Pulmonary/organ-dysfunction output completed: {filename}",
    )

# Downstream stages retain their row set and now also carry pulmonary state.
df_aggregated = df_aggregated_with_pulmonary

# sirs_pipeline = build_sirs_pipeline(sirs_config)
# df_sirs = sirs_pipeline.process(df_aggregated)
# save_df(df_sirs, input_output_config_3_1.output_path, "df_sirs.parquet", logger,
#          message=f"SIRS calculation completed, and data is saved to {input_output_config_3_1.output_path+'/df_sirs.parquet'}")

df_sirs = load_df(input_output_config_3_1.output_path, "df_sirs.parquet")

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
    # df_sirs_filtered = load_df(input_output_config_3_1.output_path, "df_sirs_segments_filtered.parquet")

if bp_episode_filter_config.enabled:
    df_encounters = load_df(
        input_output_config_3_1.output_path,
        "df_encounters.parquet",
    )

    df_bp_segments = build_bp_state_segments(
        df_aggregated,
        df_encounters,
        config=septicshock_config,
    )

    bp_episode_results = run_episode_filter(
        df_bp_segments,
        config=bp_episode_filter_config,
    )

    outputs = {
        "df_hypotension_segments_v1.parquet": df_bp_segments,
        "df_hypotension_episodes_raw_v1.parquet": bp_episode_results["raw"],
        "df_hypotension_episodes_bridged_v1.parquet": bp_episode_results["bridged"],
        "df_hypotension_episodes_merged_v1.parquet": bp_episode_results["merged"],
        "df_hypotension_episodes_filtered_v1.parquet": bp_episode_results["filtered"],
    }

    # Prevent accidental overwriting.
    # existing = [
    #     filename
    #     for filename in outputs
    #     if (
    #         Path(input_output_config_3_1.output_path) / filename
    #     ).exists()
    # ]
    # if existing:
    #     raise FileExistsError(
    #         f"Refusing to overwrite existing BP outputs: {existing}"
    #     )

    for filename, dataframe in outputs.items():
        save_df(
            dataframe,
            input_output_config_3_1.output_path,
            filename,
            logger,
            message=f"Hypotension output completed: {filename}",
        )

    df_bp_filtered = load_df(input_output_config_3_1.output_path, "df_hypotension_episodes_filtered_v1.parquet")

x = 0
