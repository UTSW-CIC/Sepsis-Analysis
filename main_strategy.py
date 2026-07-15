from src_strategy.data_ingest.dataloader_1 import DataLoader
from src_strategy.configs.dataconfig import input_output_config_3, bp_config, data_config
from src_strategy.configs.outlierdetection.extremeoutliers import flowsheet_bounds_config, lab_bounds_config, bp_bounds_config

dl = DataLoader(input_output_config_3, data_config, bp_config, flowsheet_bounds_config, lab_bounds_config, bp_bounds_config)
df_all = dl.load_data()


