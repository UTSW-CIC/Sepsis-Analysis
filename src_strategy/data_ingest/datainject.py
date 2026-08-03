import polars as pl
from ..configs.dataconfig import DataConfig, BloodPressureConfig, DataInputOutputConfig
from ..configs.outlierdetection.extremeoutliers import FlowsheetBoundsConfig, LabBoundsConfig
from logging import Logger

from typing import List, Mapping, Literal, Any, Tuple
from enum import Enum
from pathlib import Path

class SORT_BY(str, Enum):
    NULL_PCT_VALUE = 'null_pct_Value'
    N_UNIQUE_ENCOUNTERS = 'n_unique_encounters'
    N_ROWS = 'n_rows'
    N_NULLS_VALUE = 'n_nulls_Value'


class DataInjectMonitor:
    def __init__(self, data_config: DataConfig,
                 bp_config: BloodPressureConfig,
                 physiological_bounds_config: FlowsheetBoundsConfig = None,
                 lab_bounds_config: LabBoundsConfig = None,
                 input_output_dataconfig: DataInputOutputConfig = None,
                 logger = None):
        self.data_config = data_config
        self.bp_config = bp_config
        self.physiological_bounds_config = physiological_bounds_config
        self.lab_bounds_config = lab_bounds_config
        self.input_output_dataconfig = input_output_dataconfig
        self.logger = logger

    def _emit(self, message: str, mode:str = 'info', end = '\n'):
        """Write to the supplied logger, instance logger, or stdout."""

        if self.logger is not None:
            if mode == 'info':
                self.logger.info(message)
            elif mode == 'warning':
                self.logger.warning(message)
            elif mode == 'error':
                self.logger.error(message)
            else:
                self.logger.info(message)
            if end:
                self.logger.info(end)
        else:
            print(message)
            if end:
                print(end)

    def _emit_table(self, df: pl.DataFrame, message=None, top:int = 10, end = '\n'):
        if self.logger is not None:
            if message is not None:
                self.logger.info(message)
            self.logger.info(df.head(top))
            if end:
                self.logger.info(end)
        else:
            if message is not None:
                print(message)
            print(df.head(top))
            if end:
                print(end)

    def compare_encounters_among_tables(self, df_list: Mapping[str, pl.DataFrame], show_encounters:bool=False, save: bool=True)->None:
        keys = list(df_list.keys())
        encs = set(df_list[keys[0]][self.data_config.encounter_col].unique())
        current_table = keys[0]
        for table_name, df in df_list.items():
            if table_name == keys[0]:
                continue
            encs_2 = set(df[self.data_config.encounter_col].unique())
            if encs != encs_2:
                self._emit(f'Encounter mismatch between {table_name} and {current_table}. {table_name} has {len(encs_2)} encounters while {current_table} has {len(encs)} encounters.',
                          'warning')
            diff1 = encs - encs_2
            diff2 = encs_2 - encs
            if len(diff1) > 0:
                self._emit(f'Encounter mismatch between {table_name} and {current_table}. {table_name} has {len(diff1)} encounters that are not in {current_table}: {diff1 if show_encounters else ""}.',
                          'warning')
            if len(diff2) > 0:
                self._emit(f'Encounter mismatch between {table_name} and {current_table}. {current_table} has {len(diff2)} encounters that are not in {table_name}: {diff2 if show_encounters else ""}.',
                          'warning')
            encs = encs.union(encs_2)
            current_table = current_table+', '+table_name

    def summarize_table(self, df: pl.DataFrame, name: str=None,
                         sort_by: Literal['null_pct_Value', 'n_unique_encounters', 'n_rows', 'n_nulls_Value']=None, descending: bool=True, save:bool=True)->None:
        if name is None:
            name = ""
        if sort_by is None:
            sort_by = 'null_pct_Value'

        prefix = name + ': ' if name is not None else '' 
        event_grouper_summary = df.group_by(
            self.data_config.grouper_col
        ).agg(
            pl.col(self.data_config.encounter_col).n_unique().alias('n_unique_encounters'),
            pl.len().alias('n_rows'),
            pl.col(self.data_config.raw_val_col).null_count().alias('n_nulls_Value'),
            (pl.col(self.data_config.raw_val_col).null_count() / pl.len()).alias('null_pct_Value')
        )
        self._emit_table(event_grouper_summary.sort(by=sort_by, descending=descending),
                        message=f"{prefix}Event Grouper by {sort_by}",
                        end='-'*25,
                        top=10)
        if save:
            if not name:
                raise ValueError('name must be provided if save is True')
            event_grouper_summary.write_csv(Path(self.input_output_dataconfig.meta_ingest_path)/Path(f'{name}_eventgrouper_by{sort_by}.csv'))

        event_type_summary = df.group_by(
            self.data_config.type_col
        ).agg(
            pl.col(self.data_config.encounter_col).n_unique().alias('n_unique_encounters'),
            pl.len().alias('n_rows'),
            pl.col(self.data_config.raw_val_col).null_count().alias('n_nulls_Value'),
            (pl.col(self.data_config.raw_val_col).null_count() / pl.len()).alias('null_pct_Value')
        )
        self._emit_table(event_type_summary.sort(by=sort_by, descending=descending),
                        message=f"{prefix}Event Type by {sort_by}",
                        end='-'*25,
                        top=10)
        if save:
            if not name:
                raise ValueError('name must be provided if save is True')
            event_grouper_summary.write_csv(Path(self.input_output_dataconfig.meta_ingest_path)/Path(f'{name}_type_by{sort_by}.csv'))

        event_name_summary = df.group_by(
            self.data_config.event_name_col
        ).agg(
            pl.col(self.data_config.encounter_col).n_unique().alias('n_unique_encounters'),
            pl.len().alias('n_rows'),
            pl.col(self.data_config.raw_val_col).null_count().alias('n_nulls_Value'),
            (pl.col(self.data_config.raw_val_col).null_count() / pl.len()).alias('null_pct_Value')
        )
        self._emit_table(event_name_summary.sort(by='null_pct_Value', descending=descending),
                        message=f"{prefix}Event Name by {sort_by}",
                        end='-'*25,
                        top=10)
        if save:
            if not name:
                raise ValueError('name must be provided if save is True')
            event_grouper_summary.write_csv(Path(self.input_output_dataconfig.meta_ingest_path)/Path(f'{name}_eventname_by{sort_by}.csv'))
    
    def summarize_outlier_cols(
            self,
            df: pl.DataFrame,
            outlier_dict: Mapping[str, Tuple[str, Any]],
            name: str=None):
        if name is None:
            name = ""
        else:
            name = name + ": "
        for orig_col, (outlier_col, outlier_val) in outlier_dict.items():
            # Count outliers
            n_outliers =df.filter(
                pl.col(outlier_col) == outlier_val
            ).shape[0]
            self._emit(f'{name}{orig_col} has {n_outliers} outliers')

            # Count mismatch between orig_col and outlier_col
            n_mismatch = df.filter(
                (pl.col(outlier_col) != pl.col(orig_col))&(pl.col(orig_col).is_not_null() & pl.col(outlier_col).is_not_null())
            ).shape[0]
            self._emit(f'{name}{orig_col} and {outlier_col} have {n_mismatch} mismatched values (excluding nulls) ...')

            if n_outliers > 0:
                df_outlier_by_grouper = df.filter(
                    pl.col(outlier_col) == outlier_val
                )[self.data_config.grouper_col].value_counts(sort=True)
                self._emit_table(df_outlier_by_grouper,
                                message=f'{name}{orig_col} outliers by {self.data_config.grouper_col}',
                                end='-'*25,
                                top=10)
    
    def _sys_dia_columns_correspond_to(self, df: pl.DataFrame,  bp_cols: List[str]):
        for col in bp_cols:
            assert col in df.columns, f'Column {col} not found in df'
            unique_groupers = df.filter(
                pl.col(col).is_not_null()
            )[self.bp_config.grouper_col].unique()
            assert len(unique_groupers) == 1, f'Column {col} has multiple unique groupers: {unique_groupers}'
            self._emit(f'Column {col} has grouper {unique_groupers[0]}')

    def _map_columns_correspond_to(self, df: pl.DataFrame, bp_cols: List[str]):
        for col in bp_cols:
            assert col in df.columns, f'Column {col} not found in df'
            unique_groupers = df.filter(
                pl.col(col).is_not_null()
            )[self.bp_config.grouper_col].unique()
            assert len(unique_groupers) == 2, f'Column {col} has multiple unique groupers: {unique_groupers}'
            self._emit(f'Column {col} has grouper {unique_groupers}')

    def summarize_same_instant_events(self, df: pl.DataFrame,
                                      encounter_id: str, event_dt: str, event_grouper_col: str,
                                      name: str=None):
        if name is None:
            name = ""
        else:
            name = name + ": "
        events_collision = df.group_by(
            encounter_id,
            event_dt,
            event_grouper_col
        ).agg(
            pl.len().alias('n_rows')
        ).filter(pl.col('n_rows') > 1)

        self._emit_table(
            df=events_collision[event_grouper_col].value_counts(sort=True),
            message=f'{name}Same instant events by {event_grouper_col}. Value counts:',
        )
        self._emit_table(
            df=events_collision[encounter_id].value_counts(sort=True),
            message=f'{name}Same instant events by {encounter_id}. Value counts:',
        )