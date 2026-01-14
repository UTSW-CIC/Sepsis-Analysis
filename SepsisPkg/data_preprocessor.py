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

def scan_multiple_files(folder: Union[str, Path]):
    ppas