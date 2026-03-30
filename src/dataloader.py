import polars as pl
import duckdb
import os
from pathlib import Path
from src.utils.logger import get_logger

logger = get_logger(__name__)

class DataLoader:
    def __init__(self, data_dir: Path | str):
        self.data_dir = data_dir
        self.df_all = None

    def cast_cols(self,df: pl.DataFrame):
        cast_expr = [pl.col(c).cast(pl.Float64) for c in df.columns if c.startswith('Baseline_')]

        if df.schema['EncounterEpicCsn'] == pl.Utf8:
            cast_expr.append(
                pl.col("EncounterEpicCsn").cast(pl.Int64)
            )

        if 'PrimaryMrn' in df.schema and df.schema['PrimaryMrn'] == pl.Utf8:
            cast_expr.append(
                pl.col("PrimaryMrn").cast(pl.Int64)
            )

        if 'Death_Flag' in df.schema and df.schema['Death_Flag'] == pl.Utf8:
            cast_expr.append(
                pl.col("Death_Flag").cast(pl.Int64)
            )


        if 'Event_DateTime' in df.schema and df.schema['Event_DateTime'] == pl.Utf8:
            cast_expr.append(
                pl.col("Event_DateTime").str.strptime(pl.Datetime, "%Y-%m-%d %H:%M:%S%.f"),
            )

        if 'Arrival_Instant' in df.schema and df.schema['Arrival_Instant'] == pl.Utf8:
            cast_expr.append(
                pl.col("Arrival_Instant").str.strptime(pl.Datetime, "%Y-%m-%d %H:%M:%S%.f"),
            )

        if 'FirstAdmissionOrderInstant' in df.schema and df.schema['FirstAdmissionOrderInstant'] == pl.Utf8:
            cast_expr.append(
                pl.col("FirstAdmissionOrderInstant").str.strptime(pl.Datetime, "%Y-%m-%d %H:%M:%S%.f"),
            )

        if 'InpatientAdmissionInstant' in df.schema and df.schema['InpatientAdmissionInstant'] == pl.Utf8:
            cast_expr.append(
                pl.col("InpatientAdmissionInstant").str.strptime(pl.Datetime, "%Y-%m-%d %H:%M:%S%.f"),
            )

        if 'AdmissionDateValue' in df.schema and df.schema['AdmissionDateValue'] == pl.Utf8:
            cast_expr.append(
                pl.col("AdmissionDateValue").str.strptime(pl.Datetime, "%Y-%m-%d"),
            )

        if 'DischargeDateValue' in df.schema and df.schema['DischargeDateValue'] == pl.Utf8:
            cast_expr.append(
                pl.col("DischargeDateValue").str.strptime(pl.Datetime, "%Y-%m-%d"),
            )


        if 'NumericValue' in df.schema and df.schema['NumericValue'] == pl.Utf8:
            cast_expr.append(
                pl.col("NumericValue").cast(pl.Float64)
            )
        
        return df.with_columns(
            cast_expr
        )

    def load_data(self) -> pl.DataFrame:
        """
        Load data from the specified directory.

        Args:
            data_dir (Union[Path, str]): The directory containing the data files.
        Returns:
            pl.DataFrame: A Polars DataFrame containing the loaded data.
        """
        logger.info(f"Loading data from {self.data_dir}")
        lab_res = pl.read_csv(self.data_dir/Path("Lab Results - 3.9.26.csv"), infer_schema=False, null_values=['Null', "NULL", 'null'])
        flowsheets = pl.read_csv(self.data_dir/Path("Flowsheet - 3.24.26.csv"), infer_schema=False, null_values=['Null', "NULL", 'null'])
        med_admin = pl.read_csv(self.data_dir/Path("Med Admin - 3.9.26.csv"), infer_schema=False, null_values=['Null', "NULL", 'null'])
        procedures = pl.read_csv(self.data_dir/Path("Procedure Orders - 3.9.26.csv"), infer_schema=False, null_values=['Null', "NULL", 'null'])
        baseline = pl.read_csv(self.data_dir/Path("Encounter Table with Baseline Values - Mar 2025 - Feb 2026 - 3.25.26.csv"), infer_schema=False, null_values=['Null', "NULL", 'null'])
        diagnosis = pl.read_csv(self.data_dir/Path("Diagnoses - 3.9.26.csv"), infer_schema=False, null_values=['Null', "NULL", 'null'])
        logger.info(f"Data loaded. Shapes: lab_res={lab_res.shape}, flowsheets={flowsheets.shape}, med_admin={med_admin.shape}, procedures={procedures.shape}, baseline={baseline.shape}, diagnosis={diagnosis.shape}")
        logger.info("--------------------------------------------------------------------------------")
        lab_res = self.cast_cols(lab_res)
        flowsheets = self.cast_cols(flowsheets)
        med_admin = self.cast_cols(med_admin)
        procedures = self.cast_cols(procedures)
        baseline = self.cast_cols(baseline)
        diagnosis = self.cast_cols(diagnosis)

        logger.info("Data type casting completed.")
        df_all = pl.concat([
            lab_res, procedures, med_admin, flowsheets, diagnosis
        ], how='vertical')

        df_all = df_all.join(
            baseline,
            on='EncounterEpicCsn',
            how='outer'
        )
        logger.info(f"Concatenated all data into a single DataFrame with shape {df_all.shape} and columns {df_all.columns}")
        before_drop = df_all.shape[0]
        df_all = df_all.unique()
        after_drop = df_all.shape[0]
        logger.info(f"Dropped duplicate rows. Before: {before_drop}, After: {after_drop}, Dropped: {before_drop - after_drop}")

        logger.info("Filtering out rows with null EncounterEpicCsn or Event_DateTime")
        self.df_all = df_all.filter(
            pl.col("EncounterEpicCsn").is_not_null() & pl.col("Event_DateTime").is_not_null()
        )
        logger.info(f"After filtering, df_all has shape {self.df_all.shape}")
        return self.df_all
    
    def save_csv(self, output_dir: Path | str, filename: str = "infection_detection_result.csv"):
        """
        Save the full df_all DataFrame to a CSV file.

        Args:
            output_dir (Union[Path, str]): Directory where the CSV will be saved.
        
        Raises:
            ValueError: If load_data() has not been called yet.
        """
        if self.df_all is None:
            raise ValueError("No data loaded. Call load_data() before saving.")
        
        if isinstance(filename, str) and not filename.endswith(".csv"):
            filename += ".csv"
        
        logger.info(f"Saving df_all with shape {self.df_all.shape} to {output_dir}/{filename}")
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        output_path = output_dir / filename
        self.df_all.write_csv(output_path)

        logger.info(f"Finished saving data to {output_path}")