from pathlib import Path
from tempfile import TemporaryDirectory

import polars as pl
from polars.testing import assert_frame_equal

from src_strategy.configs.dataconfig import (
    BloodPressureConfig,
    DataConfig,
    DataInputOutputConfig,
    InputFileNames,
)
from src_strategy.configs.outlierdetection.extremeoutliers import (
    BloodPressureBoundsConfig,
    FlowsheetBoundsConfig,
    LabBoundsConfig,
)
from src_strategy.configs.pulmonarydysfunction import PFConfig
from src_strategy.data_ingest.dataloader_1 import DataLoader as DataLoaderV1
from src_strategy.data_ingest.dataloader_2 import DataLoader as DataLoaderV2


FILENAMES = InputFileNames(
    ENCOUNTER_BASELINE_SCORES="encounters.csv",
    FLOWSHEETS="flowsheets.csv",
    LABS="labs.csv",
    MEDS="meds.csv",
    PROCEDURES="procedures.csv",
    DIAGNOSIS="diagnoses.csv",
)

EVENT_COLUMNS = [
    "EncounterEpicCsn",
    "Event_DateTime",
    "Type",
    "Event_Grouper",
    "Event_Name",
    "NumericValue",
    "Value",
]


def event_frame(rows: list[tuple]) -> pl.DataFrame:
    return pl.DataFrame(rows, schema=EVENT_COLUMNS, orient="row")


def write_synthetic_sources(input_path: Path) -> None:
    input_path.mkdir(parents=True, exist_ok=True)
    time_0 = "2026-01-01 00:00:00.000"
    time_1 = "2026-01-01 00:30:00.000"
    time_2 = "2026-01-01 01:00:00.000"

    bp_row = (1, time_0, "Flowsheet", "Blood Pressure", "BP", None, "120/80")
    event_frame(
        [
            bp_row,
            bp_row,
            (
                1,
                time_1,
                "Flowsheet",
                "Arterial Blood Pressure Mean",
                "Measured MAP",
                60.0,
                "60",
            ),
            (1, time_2, "Flowsheet", "Pulse", "Pulse", 100.0, "100"),
        ]
    ).write_csv(input_path / FILENAMES.FLOWSHEETS)

    event_frame(
        [
            (1, time_0, "Lab", "PAO2", "PO2 ART", 80.0, "80"),
            (1, time_1, "Lab", "FIO2", "FIO2", 40.0, "40"),
        ]
    ).write_csv(input_path / FILENAMES.LABS)

    event_frame(
        [(1, time_1, "Medication", "Medication", "Example Med", 1.0, "1")]
    ).write_csv(input_path / FILENAMES.MEDS)
    event_frame(
        [(1, time_1, "Procedure", "Procedure", "Example Order", 1.0, "1")]
    ).write_csv(input_path / FILENAMES.PROCEDURES)
    event_frame(
        [(1, time_1, "Diagnosis", "Diagnosis", "Example Diagnosis", 1.0, "1")]
    ).write_csv(input_path / FILENAMES.DIAGNOSIS)
    pl.DataFrame({"EncounterEpicCsn": [1]}).write_csv(
        input_path / FILENAMES.ENCOUNTER_BASELINE_SCORES
    )


def make_io_config(
    input_path: Path,
    output_path: Path,
) -> DataInputOutputConfig:
    return DataInputOutputConfig(
        data_path=str(input_path),
        output_path=str(output_path),
        input_file_names=FILENAMES,
    )


def make_loader(loader_class, io_config: DataInputOutputConfig):
    return loader_class(
        io_config,
        DataConfig(),
        BloodPressureConfig(),
        FlowsheetBoundsConfig.with_defaults(),
        LabBoundsConfig.with_defaults(),
        BloodPressureBoundsConfig.with_defaults(),
        pf_config=PFConfig(),
    )


def csv_schema_map(root: Path) -> dict[str, list[str]]:
    return {
        str(path.relative_to(root)): pl.read_csv(path).columns
        for path in sorted(root.rglob("*.csv"))
    }


def test_dataloader_v2_matches_v1_end_to_end() -> None:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        input_path = root / "input"
        write_synthetic_sources(input_path)

        v1_io = make_io_config(input_path, root / "v1_output")
        v2_io = make_io_config(input_path, root / "v2_output")
        v1_events, v1_encounters = make_loader(DataLoaderV1, v1_io).load_data()
        v2_events, v2_encounters = make_loader(DataLoaderV2, v2_io).load_data()

        event_sort_cols = [
            "EncounterEpicCsn",
            "Event_DateTime",
            "Type",
            "Event_Grouper",
            "Event_Name",
            "Value",
        ]
        assert_frame_equal(
            v2_events.sort(event_sort_cols),
            v1_events.sort(event_sort_cols),
        )
        assert_frame_equal(
            v2_encounters.sort("EncounterEpicCsn"),
            v1_encounters.sort("EncounterEpicCsn"),
        )

        assert v2_events.height == 8
        assert v2_encounters.height == 1

        bp = v2_events.filter(pl.col("Event_Grouper") == "Blood Pressure")
        assert bp["sys"].to_list() == [120.0]
        assert bp["dia"].to_list() == [80.0]
        assert bp["map"].to_list() == [None]

        measured_map = v2_events.filter(
            pl.col("Event_Grouper") == "Arterial Blood Pressure Mean"
        )
        assert measured_map["map"].to_list() == [60.0]

        pao2 = v2_events.filter(pl.col("Event_Grouper") == "PAO2")
        assert pao2["pf_ratio"].to_list() == [200.0]
        assert pao2["PF_Ratio_Flag"].to_list() == [None]

        assert csv_schema_map(Path(v2_io.meta_output_path)) == csv_schema_map(
            Path(v1_io.meta_output_path)
        )


def test_dataloader_v2_is_importable_without_switching_active_loader() -> None:
    assert DataLoaderV2 is not DataLoaderV1
    assert DataLoaderV2.__module__.endswith("dataloader_2")
