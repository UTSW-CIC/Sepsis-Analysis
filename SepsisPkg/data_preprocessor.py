import polars as pl
import seaborn as sns
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import plotly.express as px
import os
import sys
from pathlib import Path
from typing import Optional, Union

from config import SEPSIS_CONFIG

def cast_datetime_cols(
	lf: pl.LazyFrame,
	cols = ['Pt_Arrival', 'Event_DateTime', 'Admit_Time']
):
	schema = lf.collect_schema()
	for c in cols:
		if schema[c] in [pl.Utf8, pl.String]:
			lf = lf.with_columns(
			pl.col(c).str.strptime(pl.Datetime, format="%Y-%m-%d %H:%M:%S%.f")
		)
	return lf

BASELINE_COLS = [
    'Baseline_SBP',
	'Baseline_DBP',
	'Baseline_RespiratoryRate',
	'Baseline_PulseRate',
	'Baseline_Creatinine',
	'Baseline_Bilirubin',
	'Baseline_Platelets',
	'Baseline_WBC',
	'Baseline_BUN',
	'Baseline_LVEF'
]

def rename_event_datetime_col(lf_f, schema, rename_dict={'Event_Datetime':'Event_DateTime'}):
    for old_name, new_name in rename_dict.items():
        if old_name in schema.names():
            lf_f = lf_f.rename(
                rename_dict
            )
    
    return lf_f

def process_MEAS_VALUE_rate_char_cols(lf_f, schema):
    meas_value_rate = []
    meas_value_char = []
    if 'MEAS_VALUE_RATE' in schema.names():
        meas_value_rate.append((lf_f.filter(
            pl.col("MEAS_VALUE_RATE").is_not_null()
        ).select("PAT_ENC_CSN_ID", "Event_DateTime", "EVENT_NAME", "MEAS_VALUE_RATE").collect(), f))
        lf_f = lf_f.drop("MEAS_VALUE_RATE")

    if 'MEAS_VALUE_CHAR' in schema.names():
        meas_value_char.append((lf_f.filter(
            pl.col("MEAS_VALUE_CHAR").is_not_null()
        ).select("PAT_ENC_CSN_ID", "Event_DateTime", "EVENT_NAME", "MEAS_VALUE_CHAR").collect(), f))
        lf_f = lf_f.drop("MEAS_VALUE_CHAR")
    
    if  'MEAS_VALUE' in schema.names() and schema['MEAS_VALUE'] not in [pl.Utf8, pl.String]:
        lf_f = lf_f.with_columns(
        pl.col("MEAS_VALUE").cast(pl.Utf8)
        )
    return lf_f

def drop_cols_if_exist(lf_f, schema, cols = ['Event_ID', 'Before_Admit_YN']):
    for c in cols:
        if c in schema.names():
            print(f"Dropping Before_Admit_YN for file {c}\n")
            lf_f = lf_f.drop(c)
    return lf_f

def preprocess_dir(RAW_DATA_PATH="../data/raw_data_new"):
    files = sorted(os.listdir(RAW_DATA_PATH))

    lf_list = []

    lf_baseline = None
    for idx, f in enumerate(files):
        if f == 'SOFA Scores - 1.13.26.csv': continue
        f_path = os.path.join(RAW_DATA_PATH, f)
        lf_f = pl.scan_csv(
            f_path,
            null_values=['null', 'NULL', 'Null', "None"],
            infer_schema_length=int(1e7)
        )

        schema = lf_f.collect_schema()
        lf_f = rename_event_datetime_col(lf_f, schema, {'Event_Datetime':'Event_DateTime'})
        lf_f = process_MEAS_VALUE_rate_char_cols(lf_f, schema)
        
        if f == 'Encounter Table with Baseline Values - Dec 2024 - Nov 2025.csv':
            lf_baseline = lf_f
            continue
        
        lf_list.append(lf_f)
    
    return lf_list, lf_baseline

