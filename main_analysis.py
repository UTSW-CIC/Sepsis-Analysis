from src.configs.dataconfig import DataInputOutputConfig, env_settings, input_filenames_v2
from src.configs.analysis.twoexpr import two_experiment_analysis_config
from src.configs.basic import basic_analysis_config

from src.analysis.basic import BasicAnalysis
from src.analysis.core import CoreAnalysis
from src.analysis.analyze2exp import TwoExperimentsAnalysis
from pathlib import Path

import os
import polars as pl
os.environ["NUMEXPR_MAX_THREADS"] = "64"  

input_output_config_2 = DataInputOutputConfig(
    data_path=f"{env_settings.DATA_ABS_PATH}/data/raw_data_phase2_v2",
    output_path=f'{env_settings.DATA_ABS_PATH}/data/output_data_phase2_v2_iteration2',
    input_file_names=input_filenames_v2
)

# input_output_config_2 = DataInputOutputConfig(
#     data_path=f"{env_settings.DATA_ABS_PATH}/data/raw_data_phase2_v2",
#     output_path=f'{env_settings.DATA_ABS_PATH}/data/output/raw_data_phase2_v2_old',
#     input_file_names=input_filenames_v2
# )

if __name__ == "__main__":
    # b = BasicAnalysis(input_output_config_2.output_path, basic_analysis_config) 
    b = CoreAnalysis( f'{env_settings.DATA_ABS_PATH}/data/output/raw_data_phase3_v2_old',
                      "./core_analysis_output_v3_v2old_1", basic_analysis_config) 
    b.analyze()
    # b = TwoExperimentsAnalysis(Path("../Sepsis-data/data/output/raw_data_phase2_v2_old"),
    #                                 input_output_config_2.output_path,
    #                              "./two_exper_analysis_output", two_experiment_analysis_config)
    # b.analyze(
    #     "Old Algorithm",
    #     "Updated Algorithm",
    #     "sepsis_comparison_output"
    #     )