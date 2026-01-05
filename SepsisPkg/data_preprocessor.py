import polars as pl
import seaborn as sns
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import plotly.express as px
import os
import sys

from config import SEPSIS_CONFIG


# The "Anchor" for your Rolling Window
expr_culture_orders = (
    # Look for the ORDER or PROCEDURE
    (pl.col("event_full_name").str.to_lowercase().str.contains("order")) &
    (pl.col("event_full_name").str.to_lowercase().str.contains("culture")) &
    
    # Filter for the actual REQUEST (Procedure), not the Result
    (pl.col("event_full_name").str.to_lowercase().str.contains("procedure"))
)


expr_antibiotics_gold_standard = (
    (pl.col("Event_Grouper") == "Antibiotics") & 
    
    # 1. INCLUSION: Must be a systemic route
    (pl.col("event_full_name").str.to_lowercase().str.contains(r"\biv\b|intravenous|infusion|injection|push|piggy back")) &
    
    # 2. EXCLUSION: The "Not Sepsis" Filter
    ~(pl.col("event_full_name").str.to_lowercase().str.contains(
        r"dialysis|"        # Maintenance fluids
        r"heparin|"         # Line flushes
        r"lock solution|"   # Catheter cleaning
        r"chemo|"           # Cancer treatment
        r"rubicin|"         # Specific chemo agents (Doxorubicin, etc.)
        r"epoch|"           # Chemo cocktail
        r"intravitreal|"    # Eye injections (Local)
        r"intrapleural|"    # Lung cavity (Local/Mechanical)
        r"alteplase|"       # Clot busters
        r"activase"         # Clot busters
    ))
)

def detect_sepsis_suspicion(lf: pl.LazyFrame, expr_antibiotics_gold_standard: pl.Expr,
                            expr_culture_orders: pl.Expr):
    lf_abx = lf.filter(
        expr_antibiotics_gold_standard
    ).select(
        "PAT_ENC_CSN_ID",
        pl.col("Event_DateTime").alias("ABX_Time")
    ).sort("ABX_Time")

    lf_culture = lf.filter(
        expr_culture_orders 
    ).select(
        "PAT_ENC_CSN_ID",
        pl.col("Event_DateTime").alias("culture_Time")
    ).sort("culture_Time")

    lf_suspected_backward = lf_abx.join_asof(
        lf_culture,
        left_on="ABX_Time",
        right_on="culture_Time",
        by="PAT_ENC_CSN_ID",
        strategy="backward",
        tolerance="24h"
    ).filter(pl.col("culture_Time").is_not_null())

    lf_suspected_forward = lf_abx.join_asof(
        lf_culture,
        left_on="ABX_Time",
        right_on="culture_Time",
        by="PAT_ENC_CSN_ID",
        strategy="forward",
        tolerance="72h"
    ).filter(pl.col("culture_Time").is_not_null())

    # Combine matches and pick the EARLIEST of the two times
    df_suspected_infection = (
        pl.concat([lf_suspected_backward, lf_suspected_forward])
        .unique()
        .with_columns(
            # Sepsis Time Zero = Min(Abx Time, Culture Time)
            pl.min_horizontal(["ABX_Time", "culture_Time"]).alias("Suspected_Infection_Time")
        )
        # Get the FIRST episode per encounter
        .group_by("PAT_ENC_CSN_ID")
        .agg(pl.col("Suspected_Infection_Time").min())
        .collect()
    )
    return df_suspected_infection

df_all = pl.read_parquet("./data/preprocessed_all_data.parquet")

df_suspected_infection = detect_sepsis_suspicion(
    df_all.lazy(), expr_antibiotics_gold_standard, expr_culture_orders
)
print(df_suspected_infection.shape)