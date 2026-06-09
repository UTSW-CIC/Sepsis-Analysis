from experiment import Experiment, run_experiment
from src.configs.suspected_infection import SuspectedInfectionConfig

from src.configs.severitysepsis import SeveritySepsisConfig
from src.configs.dataconfig import DataInputOutputConfig, InputFileNames, env_settings
from src.configs.sirscalculator import SIRSPostAggConfig

# Fresh defaults, then mutate the one nested field you're changing.
severity_sepsis_config = SeveritySepsisConfig(
    infection_2_sirs_forward_hrs=24,
    infection_2_sirs_backward_hrs=24
)

sirs_config = SIRSPostAggConfig(
    hr_flag_col = "Pule_High_Flag"
)


abx_fwd_48h = Experiment(
    name="phase2_v2_abx_fwd_48h",          # folder name encodes the knob + value
    data_path=f"{env_settings.DATA_ABS_PATH}/data/raw_data_phase2_v2",
    input_file_names=InputFileNames(
        ENCOUNTER_BASELINE_SCORES = "Encounter Table with Baseline Values - Mar 2025 - Feb 2026 - 4.13.26 v2.csv" ,
        FLOWSHEETS = "Flowsheets - Mar 2025 - Feb 2026 - 4.9.26.csv",
        PROCEDURES  = "Procedure Orders - Mar 2025 - Feb 2026 - 4.9.26.csv",
        DIAGNOSIS  = "Diagnoses - 3.9.26.csv",
        MEDS = "Med Admin - Mar 2025 - Feb 2026 - 4.8.26.csv",
        LABS = "Lab Results - Mar 2025 - Feb 2026 - 4.8.26.csv"
    ),
    sirs_postagg_config = sirs_config,
    severitysepsisconfig=severity_sepsis_config
)

result = run_experiment(abx_fwd_48h)
print(result.output_dir)   # .../data/output/phase2_v2_abx_fwd_48h