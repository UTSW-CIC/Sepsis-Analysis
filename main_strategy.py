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
    build_organ_dysfunction_episodes,
    build_organ_dysfunction_pipeline,
    build_organ_dysfunction_state_segments,
    prepare_organ_dysfunction_input,
)
from src_strategy.events.pulmonarydysfunction import (
    attach_pulmonary_state,
    build_pulmonary_state_segments,
    build_pulmonary_state_timeline,
)
from src_strategy.events.septicshock import (
    build_septic_shock_interval_episodes,
    build_septic_shock_interval_segments,
    build_septic_shock_pipeline,
    build_septic_shock_point_evidence,
    build_vasopressor_evidence,
    prepare_septic_shock_input,
)
from src_strategy.configs.sirscalculator import sirs_config
from src_strategy.configs.severitysepsis import severitysepsisconfig
from src_strategy.events.episode_filter import (
    build_state_episodes,
    run_episode_filter,
)
from src_strategy.events.sepsis import (
    build_infection_anchors,
    build_sepsis1_associations,
    build_sepsis1_encounter_summary,
    build_sepsis2_associations,
    build_sepsis2_encounter_summary,
    build_sepsis3_associations,
    build_sepsis3_encounter_summary,
)
from src_strategy.events.sirs import (
    build_effective_sirs_episodes,
    build_sirs_pipeline,
    build_sirs_state_segments,
)
from pathlib import Path

from src_strategy.configs.septicshock import septicshock_config
from src_strategy.configs.shortdurationfilter import (
    bp_episode_filter_config,
    sirs_episode_filter_config,
)
from src_strategy.events.hypotension import (
    attach_effective_hypotension,
    build_bp_state_segments,
    build_effective_hypotension_episodes,
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

df_all = load_df(input_output_config_3_1.output_path, df_all_file_name)


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
df_suspected_infection = build_suspected_infection_pipeline(
    suspected_infection_config
).process(df_all_no_collisions)
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
df_organ_dysfunction_segments = build_organ_dysfunction_state_segments(
    df_organ_dysfunction_input,
    df_pulmonary_state_timeline,
    config=organdysfunction_config,
    pulmonary_config=pulmonary_dysfunction_config,
)
df_organ_dysfunction_episodes = build_organ_dysfunction_episodes(
    df_organ_dysfunction_segments,
    config=organdysfunction_config,
)

# Reuse the existing BP segment reconstruction and episode filter before shock
# whenever duration filtering is enabled. Raw BP flags remain available for
# audit, while the effective flag controls their contribution to shock.
bp_episode_results = None
df_effective_hypotension_episodes = None
if bp_episode_filter_config.enabled:
    df_bp_segments = build_bp_state_segments(
        df_aggregated,
        df_encounters,
        config=septicshock_config,
    )
    bp_episode_results = run_episode_filter(
        df_bp_segments,
        config=bp_episode_filter_config,
    )
    df_effective_hypotension_episodes = (
        build_effective_hypotension_episodes(bp_episode_results)
    )

df_vasopressor_evidence = build_vasopressor_evidence(
    df_all_no_collisions,
    config=septicshock_config,
)
df_septic_shock_base_input = prepare_septic_shock_input(
    df_aggregated,
    df_encounters,
    df_vasopressor_evidence,
    config=septicshock_config,
)
df_septic_shock_input = df_septic_shock_base_input
if bp_episode_filter_config.enabled:
    df_septic_shock_input = attach_effective_hypotension(
        df_septic_shock_input,
        df_effective_hypotension_episodes,
    )
df_septic_shock = build_septic_shock_pipeline(
    septicshock_config,
    use_filtered_hypotension=bp_episode_filter_config.enabled,
).process(df_septic_shock_input)
df_septic_shock_interval_segments = build_septic_shock_interval_segments(
    df_septic_shock_base_input,
    df_effective_hypotension_episodes,
    use_filtered_hypotension=bp_episode_filter_config.enabled,
    config=septicshock_config,
)
df_septic_shock_interval_episodes = build_septic_shock_interval_episodes(
    df_septic_shock_interval_segments,
    use_filtered_hypotension=bp_episode_filter_config.enabled,
    config=septicshock_config,
)
df_septic_shock_point_evidence = build_septic_shock_point_evidence(
    df_vasopressor_evidence,
    config=septicshock_config,
)

# Sepsis 1 uses the same reconstructed SIRS episodes regardless of whether the
# optional duration filter is enabled. The effective flag records which raw
# positive episodes are eligible for classification under the configured mode.
df_sirs = build_sirs_pipeline(sirs_config).process(df_aggregated)
df_sirs_segments = build_sirs_state_segments(df_sirs, config=sirs_config)
if sirs_episode_filter_config.enabled:
    sirs_episode_results = run_episode_filter(
        df_sirs_segments,
        config=sirs_episode_filter_config,
    )
else:
    sirs_episode_results = {
        "raw": build_state_episodes(df_sirs_segments),
    }
df_effective_sirs_episodes = build_effective_sirs_episodes(
    sirs_episode_results,
    filter_enabled=sirs_episode_filter_config.enabled,
    config=severitysepsisconfig,
)
df_infection_anchors = build_infection_anchors(
    df_suspected_infection,
    config=severitysepsisconfig,
)
df_sepsis1_associations = build_sepsis1_associations(
    df_infection_anchors,
    df_effective_sirs_episodes,
    use_filtered_sirs=sirs_episode_filter_config.enabled,
    config=severitysepsisconfig,
)
df_sepsis1_encounters = build_sepsis1_encounter_summary(
    df_encounters,
    df_sepsis1_associations,
    config=severitysepsisconfig,
)
df_sepsis2_associations = build_sepsis2_associations(
    df_infection_anchors,
    df_organ_dysfunction_episodes,
    config=severitysepsisconfig,
)
df_sepsis2_encounters = build_sepsis2_encounter_summary(
    df_encounters,
    df_sepsis2_associations,
    config=severitysepsisconfig,
)
df_sepsis3_associations = build_sepsis3_associations(
    df_sepsis2_associations,
    df_septic_shock_interval_episodes,
    df_septic_shock_point_evidence,
    config=severitysepsisconfig,
)
df_sepsis3_encounters = build_sepsis3_encounter_summary(
    df_encounters,
    df_sepsis3_associations,
    config=severitysepsisconfig,
)

clinical_outputs = {
    "df_suspected_infection_v1.parquet": df_suspected_infection,
    "df_infection_anchors_v1.parquet": df_infection_anchors,
    "df_pf_events_v1.parquet": df_pf_events,
    "df_pulmonary_state_timeline_v1.parquet": df_pulmonary_state_timeline,
    "df_pulmonary_state_segments_v1.parquet": df_pulmonary_state_segments,
    "df_aggregated_with_pulmonary_v1.parquet": df_aggregated_with_pulmonary,
    "df_organ_dysfunction_v1.parquet": df_organ_dysfunction,
    "df_organ_dysfunction_segments_v1.parquet": (
        df_organ_dysfunction_segments
    ),
    "df_organ_dysfunction_episodes_v1.parquet": (
        df_organ_dysfunction_episodes
    ),
    "df_vasopressor_evidence_v1.parquet": df_vasopressor_evidence,
    "df_septic_shock_v1.parquet": df_septic_shock,
    "df_septic_shock_interval_segments_v1.parquet": (
        df_septic_shock_interval_segments
    ),
    "df_septic_shock_interval_episodes_v1.parquet": (
        df_septic_shock_interval_episodes
    ),
    "df_septic_shock_point_evidence_v1.parquet": (
        df_septic_shock_point_evidence
    ),
    "df_sirs_v1.parquet": df_sirs,
    "df_sirs_segments_v1.parquet": df_sirs_segments,
    "df_sirs_episodes_raw_v1.parquet": sirs_episode_results["raw"],
    "df_sirs_episodes_effective_v1.parquet": df_effective_sirs_episodes,
    "df_sepsis1_associations_v1.parquet": df_sepsis1_associations,
    "df_sepsis1_encounters_v1.parquet": df_sepsis1_encounters,
    "df_sepsis2_associations_v1.parquet": df_sepsis2_associations,
    "df_sepsis2_encounters_v1.parquet": df_sepsis2_encounters,
    "df_sepsis3_associations_v1.parquet": df_sepsis3_associations,
    "df_sepsis3_encounters_v1.parquet": df_sepsis3_encounters,
}
if bp_episode_filter_config.enabled:
    clinical_outputs.update(
        {
            "df_hypotension_segments_v1.parquet": df_bp_segments,
            "df_hypotension_episodes_raw_v1.parquet": (
                bp_episode_results["raw"]
            ),
            "df_hypotension_episodes_bridged_v1.parquet": (
                bp_episode_results["bridged"]
            ),
            "df_hypotension_episodes_merged_v1.parquet": (
                bp_episode_results["merged"]
            ),
            "df_hypotension_episodes_filtered_v1.parquet": (
                bp_episode_results["filtered"]
            ),
            "df_hypotension_episodes_effective_v1.parquet": (
                df_effective_hypotension_episodes
            ),
        }
    )
if sirs_episode_filter_config.enabled:
    clinical_outputs.update(
        {
            "df_sirs_episodes_bridged_v1.parquet": (
                sirs_episode_results["bridged"]
            ),
            "df_sirs_episodes_merged_v1.parquet": (
                sirs_episode_results["merged"]
            ),
            "df_sirs_episodes_filtered_v1.parquet": (
                sirs_episode_results["filtered"]
            ),
        }
    )

# Safety decision: clinical integration uses new versioned filenames and
# refuses the entire save operation if any target exists. No output is partly
# updated due to an existing target, and no prior artifact is overwritten.
existing_clinical_outputs = [
    filename
    for filename in clinical_outputs
    if (Path(input_output_config_3_1.output_path) / filename).exists()
]
if existing_clinical_outputs:
    raise FileExistsError(
        "Refusing to overwrite existing clinical outputs: "
        f"{existing_clinical_outputs}"
    )

for filename, dataframe in clinical_outputs.items():
    save_df(
        dataframe,
        input_output_config_3_1.output_path,
        filename,
        logger,
        message=f"Clinical criteria output completed: {filename}",
    )
