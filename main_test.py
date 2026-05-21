from src.configs.dataconfig import input_output_config
from src.dataloader import DataLoader
from src.utils.utils import load_df
from src.utils.logger import get_logger 

logger = get_logger(__name__)

if __name__ == '__main__':
    # dl = DataLoader(input_output_dataconfig=input_output_config)
    # df_all = dl.load_data()
    df_all = load_df(input_path=input_output_config.output_path, file_name='df_all.parquet')

    print(df_all.schema)