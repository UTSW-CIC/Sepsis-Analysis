from experiment import Experiment, run_experiment
from src.configs.suspected_infection import SuspectedInfectionConfig

from src.configs.severitysepsis import SeveritySepsisConfig
from src.configs.dataconfig import DataInputOutputConfig, InputFileNames, env_settings, input_filenames_v3
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
    name="phase3_v3",          # folder name encodes the knob + value
    data_path=f"{env_settings.DATA_ABS_PATH}/data/raw_data_phase3",
    input_file_names=input_filenames_v3,
    sirs_postagg_config = sirs_config,
    severitysepsisconfig=severity_sepsis_config
)

result = run_experiment(abx_fwd_48h)
print(result.output_dir)   # .../data/output/phase2_v2_abx_fwd_48h