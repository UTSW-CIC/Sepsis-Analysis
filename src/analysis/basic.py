import polars as pl
from src.config import input_output_config
from pathlib import Path
import os

class BasicAnalysis:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.output_files = [f for f in os.listdir(self.data_dir) if f.endswith(".parquet")]
        self.df_dict_  = self.load_data()

    def load_data(self) -> dict[str, pl.DataFrame]:
        df_dict_ = {}
        for file in self.output_files:
            fname = file.split(".")[0]
            df_dict_[fname] = pl.read_parquet(os.path.join(self.data_dir, file))

        return df_dict_

    def _analyze_suspected_infection(self) -> pl.DataFrame:
        df_infect = self.df_dict_['df_infect']
        x = 0

    def analyze(self):
        self._analyze_suspected_infection()
        

    def save_data(self, df: pl.DataFrame, filename: str):
        file_path = self.data_dir / filename
        df.write_csv(file_path)

