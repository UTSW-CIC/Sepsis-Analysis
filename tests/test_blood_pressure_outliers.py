from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import polars as pl

from src_strategy.configs.dataconfig import BloodPressureConfig, DataConfig
from src_strategy.configs.outlierdetection.extremeoutliers import (
    BloodPressureBoundsConfig,
)
from src_strategy.data_ingest.dataloader_1 import DataLoader
from src_strategy.data_ingest.transformers import (
    BloodPressureBounds,
    BloodPressureExtractor,
)


def make_data_loader() -> DataLoader:
    data_config = DataConfig()
    bp_config = BloodPressureConfig()
    bounds_config = BloodPressureBoundsConfig.with_defaults()
    return DataLoader(
        input_output_dataconfig=None,
        data_config=data_config,
        bp_config=bp_config,
        bp_bounds_config=bounds_config,
    )


def make_blood_pressure_result() -> pl.DataFrame:
    """Run synthetic BP rows through extraction, bounds, and cleaning."""
    start = datetime(2026, 1, 1)
    raw = pl.DataFrame(
        {
            "EncounterEpicCsn": [1, 1, 1, 1, 1, 1],
            "Event_DateTime": [
                start + timedelta(minutes=offset) for offset in range(6)
            ],
            "Event_Grouper": [
                "Blood Pressure",
                "Blood Pressure",
                "Blood Pressure",
                "Blood Pressure",
                "Arterial Blood Pressure Mean",
                "Arterial Blood Pressure Mean",
            ],
            "Type": ["Flowsheet"] * 6,
            "Event_Name": ["Blood Pressure"] * 4 + ["Measured MAP"] * 2,
            "Value": ["120/80", "400/80", "120/400", "120/", "60", "400"],
            "NumericValue": [None, None, None, None, 60.0, 400.0],
        }
    )

    loader = make_data_loader()
    extracted = BloodPressureExtractor(loader.bp_config).apply(raw)
    flagged = BloodPressureBounds(
        loader.bp_config, loader.bp_bounds_config
    ).apply(extracted)
    return loader.merge_outlier_col_to_bp(flagged)


def test_bp_outlier_flags_are_boolean_and_component_specific() -> None:
    result = make_blood_pressure_result()

    assert result["sys_is_outlier"].to_list() == [
        False,
        True,
        False,
        False,
        False,
        False,
    ]
    assert result["dia_is_outlier"].to_list() == [
        False,
        False,
        True,
        False,
        False,
        False,
    ]
    assert result["map_is_outlier"].to_list() == [
        False,
        False,
        False,
        False,
        False,
        True,
    ]


def test_sys_and_dia_are_cleaned_as_one_reading() -> None:
    result = make_blood_pressure_result()

    assert result["sys_temp"].to_list() == [120.0, None, None, None, None, None]
    assert result["dia_temp"].to_list() == [80.0, None, None, None, None, None]


def test_measured_map_is_cleaned_independently() -> None:
    result = make_blood_pressure_result()

    assert result["map_temp"].to_list() == [None, None, None, None, 60.0, None]


def test_bp_monitoring_uses_boolean_flags_without_expected_mismatches() -> None:
    result = make_blood_pressure_result()
    loader = make_data_loader()

    with TemporaryDirectory() as temp_dir:
        loader.input_output_dataconfig = SimpleNamespace(
            meta_outlier_path=temp_dir
        )
        loader.record_outliers_bp(result)
        loader.record_outliers_bp_mismatch(result)

        output_files = {path.name for path in Path(temp_dir).iterdir()}
        assert output_files == {
            "bp_bounds.csv",
            "bp_outliers_sys.csv",
            "bp_outliers_dia.csv",
            "bp_outliers_map.csv",
        }

        bounds = pl.read_csv(Path(temp_dir) / "bp_bounds.csv")
        assert bounds["key"].to_list() == ["lower_bound", "upper_bound"]

        for column in ("sys", "dia", "map"):
            outliers = pl.read_csv(
                Path(temp_dir) / f"bp_outliers_{column}.csv"
            )
            assert outliers.height == 1
            assert f"{column}_is_outlier" in outliers.columns
