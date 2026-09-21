import argparse
import json
from pathlib import Path

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
from src_strategy.configs.run_configuration import (
    active_run_configuration_sections,
    run_identity_config,
)
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
from src_strategy.run_versioning import (
    RunMode,
    build_run_relative_path,
    canonical_configuration_json,
    configuration_sha256,
    create_incomplete_run_bundle,
    enforce_run_mode_preconditions,
    finalize_run_bundle,
    git_branch_name,
    git_commit_sha,
    utc_run_timestamp,
    validate_output_table_names,
)
from src_strategy.run_manifest import (
    ClinicalRunManifest,
    current_software_versions,
    describe_cached_input,
    describe_output_table,
    write_run_manifest,
)
from src_strategy.run_validation import (
    validate_binary_flag,
    validate_encounter_summary,
    validate_positive_flags_have_timestamps,
    # validate_sepsis2_uses_selected_first_organ_episodes,
    validate_sepsis3_is_subset_of_sepsis2,
    validate_unique_association_grain,
    validate_written_output_tables,
)

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


def parse_run_mode() -> RunMode:
    """Require the caller to choose whether output writing is permitted."""
    parser = argparse.ArgumentParser(
        description="Calculate Sepsis clinical classification outputs."
    )
    parser.add_argument(
        "--run-mode",
        required=True,
        choices=[mode.value for mode in RunMode],
        help=(
            "development calculates without saving clinical tables; "
            "versioned requires clean Git state and permits saving"
        ),
    )
    arguments = parser.parse_args()
    return RunMode(arguments.run_mode)


run_mode = parse_run_mode()
repository_root = Path(__file__).resolve().parent
enforce_run_mode_preconditions(run_mode, repository_root)

# Reserve an immutable run identity before clinical processing starts. If the
# pipeline later fails, the `.incomplete` directory is retained for review.
run_bundle_paths = None
run_timestamp = None
run_git_commit = None
run_git_branch = None
run_configuration_hash = None
run_configuration_snapshot = None
if run_mode is RunMode.VERSIONED:
    active_configuration = active_run_configuration_sections()
    run_configuration_hash = configuration_sha256(active_configuration)
    run_configuration_snapshot = json.loads(
        canonical_configuration_json(active_configuration)
    )
    run_timestamp = utc_run_timestamp()
    run_git_commit = git_commit_sha(repository_root)
    run_git_branch = git_branch_name(repository_root)
    relative_run_path = build_run_relative_path(
        dataset_version=run_identity_config.dataset_version,
        algorithm_variant=run_identity_config.algorithm_variant,
        run_timestamp=run_timestamp,
        git_commit=run_git_commit,
        configuration_hash=run_configuration_hash,
    )
    run_bundle_paths = create_incomplete_run_bundle(
        Path(input_output_config_3_1.output_path) / "clinical_runs",
        relative_run_path,
    )

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

# =========================================================================================
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
# =========================================================================================

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
    "df_suspected_infection.parquet": df_suspected_infection,
    "df_infection_anchors.parquet": df_infection_anchors,
    "df_pf_events.parquet": df_pf_events,
    "df_pulmonary_state_timeline.parquet": df_pulmonary_state_timeline,
    "df_pulmonary_state_segments.parquet": df_pulmonary_state_segments,
    "df_aggregated_with_pulmonary.parquet": df_aggregated_with_pulmonary,
    "df_organ_dysfunction.parquet": df_organ_dysfunction,
    "df_organ_dysfunction_segments.parquet": (
        df_organ_dysfunction_segments
    ),
    "df_organ_dysfunction_episodes.parquet": (
        df_organ_dysfunction_episodes
    ),
    "df_vasopressor_evidence.parquet": df_vasopressor_evidence,
    "df_septic_shock.parquet": df_septic_shock,
    "df_septic_shock_interval_segments.parquet": (
        df_septic_shock_interval_segments
    ),
    "df_septic_shock_interval_episodes.parquet": (
        df_septic_shock_interval_episodes
    ),
    "df_septic_shock_point_evidence.parquet": (
        df_septic_shock_point_evidence
    ),
    "df_sirs.parquet": df_sirs,
    "df_sirs_segments.parquet": df_sirs_segments,
    "df_sirs_episodes_raw.parquet": sirs_episode_results["raw"],
    "df_sirs_episodes_effective.parquet": df_effective_sirs_episodes,
    "df_sepsis1_associations.parquet": df_sepsis1_associations,
    "df_sepsis1_encounters.parquet": df_sepsis1_encounters,
    "df_sepsis2_associations.parquet": df_sepsis2_associations,
    "df_sepsis2_encounters.parquet": df_sepsis2_encounters,
    "df_sepsis3_associations.parquet": df_sepsis3_associations,
    "df_sepsis3_encounters.parquet": df_sepsis3_encounters,
}
if bp_episode_filter_config.enabled:
    clinical_outputs.update(
        {
            "df_hypotension_segments.parquet": df_bp_segments,
            "df_hypotension_episodes_raw.parquet": (
                bp_episode_results["raw"]
            ),
            "df_hypotension_episodes_bridged.parquet": (
                bp_episode_results["bridged"]
            ),
            "df_hypotension_episodes_merged.parquet": (
                bp_episode_results["merged"]
            ),
            "df_hypotension_episodes_filtered.parquet": (
                bp_episode_results["filtered"]
            ),
            "df_hypotension_episodes_effective.parquet": (
                df_effective_hypotension_episodes
            ),
        }
    )
if sirs_episode_filter_config.enabled:
    clinical_outputs.update(
        {
            "df_sirs_episodes_bridged.parquet": (
                sirs_episode_results["bridged"]
            ),
            "df_sirs_episodes_merged.parquet": (
                sirs_episode_results["merged"]
            ),
            "df_sirs_episodes_filtered.parquet": (
                sirs_episode_results["filtered"]
            ),
        }
    )

validate_output_table_names(clinical_outputs)

# The run directory supplies version identity, so filenames inside a bundle
# remain stable and contain no `_vN` suffix.
if run_mode is RunMode.VERSIONED:
    if (
        run_bundle_paths is None
        or run_timestamp is None
        or run_git_commit is None
        or run_configuration_hash is None
        or run_configuration_snapshot is None
    ):
        raise RuntimeError("Versioned run identity was not initialized")

    validation_results = [
        validate_encounter_summary(
            df_encounters,
            df_sepsis1_encounters,
            encounter_col=severitysepsisconfig.encounter_col,
            validation_name="sepsis1_one_row_per_input_encounter",
        ),
        validate_encounter_summary(
            df_encounters,
            df_sepsis2_encounters,
            encounter_col=severitysepsisconfig.encounter_col,
            validation_name="sepsis2_one_row_per_input_encounter",
        ),
        validate_encounter_summary(
            df_encounters,
            df_sepsis3_encounters,
            encounter_col=severitysepsisconfig.encounter_col,
            validation_name="sepsis3_one_row_per_input_encounter",
        ),
    ]

    for severity_name, summary, flag_col, timestamp_col in [
        (
            "sepsis1",
            df_sepsis1_encounters,
            severitysepsisconfig.sepsis1_flag_col,
            severitysepsisconfig.sepsis1_dt_col,
        ),
        (
            "sepsis2",
            df_sepsis2_encounters,
            severitysepsisconfig.sepsis2_flag_col,
            severitysepsisconfig.sepsis2_dt_col,
        ),
        (
            "sepsis3",
            df_sepsis3_encounters,
            severitysepsisconfig.sepsis3_flag_col,
            severitysepsisconfig.sepsis3_dt_col,
        ),
    ]:
        validation_results.extend(
            [
                validate_binary_flag(
                    summary,
                    flag_col=flag_col,
                    validation_name=f"{severity_name}_flag_is_binary_non_null",
                ),
                validate_positive_flags_have_timestamps(
                    summary,
                    flag_col=flag_col,
                    timestamp_col=timestamp_col,
                    validation_name=(
                        f"{severity_name}_positive_has_onset_timestamp"
                    ),
                ),
            ]
        )

    validation_results.extend(
        [
            validate_sepsis3_is_subset_of_sepsis2(
                df_sepsis2_encounters,
                df_sepsis3_encounters,
                config=severitysepsisconfig,
            ),
            validate_unique_association_grain(
                df_sepsis1_associations,
                key_columns=[
                    severitysepsisconfig.encounter_col,
                    severitysepsisconfig.infection_anchor_id_col,
                    severitysepsisconfig.sirs_episode_id_col,
                ],
                validation_name="sepsis1_association_grain_is_unique",
            ),
            validate_unique_association_grain(
                df_sepsis2_associations,
                key_columns=[
                    severitysepsisconfig.encounter_col,
                    severitysepsisconfig.infection_anchor_id_col,
                    severitysepsisconfig.organ_episode_id_col,
                ],
                validation_name="sepsis2_association_grain_is_unique",
            ),
            validate_unique_association_grain(
                df_sepsis3_associations,
                key_columns=[
                    severitysepsisconfig.encounter_col,
                    severitysepsisconfig.infection_anchor_id_col,
                    severitysepsisconfig.organ_episode_id_col,
                    "shock_evidence_key",
                ],
                validation_name="sepsis3_association_grain_is_unique",
            ),
            # validate_sepsis2_uses_selected_first_organ_episodes(
            #     df_sepsis2_associations,
            #     df_organ_dysfunction_episodes,
            #     config=severitysepsisconfig,
            # ),
        ]
    )

    for filename, dataframe in clinical_outputs.items():
        save_df(
            dataframe,
            str(run_bundle_paths.incomplete),
            filename,
            logger,
            message=f"Clinical criteria output completed: {filename}",
        )

    validation_results.append(
        validate_written_output_tables(
            run_bundle_paths.incomplete,
            clinical_outputs,
        )
    )

    cached_input_directory = Path(input_output_config_3_1.output_path)
    cached_inputs = [
        describe_cached_input(cached_input_directory / filename)
        for filename in [
            df_all_file_name,
            df_aggregated_file_name,
            df_all_no_collisions_file_name,
            "df_encounters.parquet",
        ]
    ]
    output_tables = [
        describe_output_table(
            run_bundle_paths.incomplete / filename,
            dataframe,
        )
        for filename, dataframe in clinical_outputs.items()
    ]
    manifest = ClinicalRunManifest(
        dataset_version=run_identity_config.dataset_version,
        algorithm_variant=run_identity_config.algorithm_variant,
        run_timestamp_utc=run_timestamp,
        git_commit=run_git_commit,
        git_branch=run_git_branch,
        git_worktree_clean=True,
        configuration_sha256=run_configuration_hash,
        configuration_snapshot=run_configuration_snapshot,
        clinical_definition_version=(
            run_identity_config.clinical_definition_version
        ),
        cached_inputs=cached_inputs,
        output_tables=output_tables,
        software_versions=current_software_versions(),
        validations=validation_results,
    )
    write_run_manifest(manifest, run_bundle_paths.incomplete)
    completed_run_path = finalize_run_bundle(run_bundle_paths)
    logger.info("Versioned clinical run published: %s", completed_run_path)
else:
    logger.info(
        "Development run completed; clinical output saving was disabled."
    )
