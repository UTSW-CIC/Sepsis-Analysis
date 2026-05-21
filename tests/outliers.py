import polars as pl
from src.configs.dataconfig import input_output_config
from src.dataloader import DataLoader

def load_data():
    dl = DataLoader(input_output_config)
    df_all = dl.load_data()
    return df_all

