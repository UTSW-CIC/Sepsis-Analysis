from datetime import datetime, timedelta
from pathlib import Path

import polars as pl

from src_strategy.analysis.cohort import build_analysis_cohort
from src_strategy.analysis.config import (
    ENCOUNTER_COL,
    phase4_analysis_config,
)
from src_strategy.analysis.figure_config import phase4_figure_config
from src_strategy.analysis.figure_pipeline import Phase4FigurePipeline
from src_strategy.analysis.phase4 import (
    Phase4AnalysisInputs,
    Phase4CoreAnalysisPipeline,
)


BASE_TIME = datetime(2026, 1, 1)


def _sepsis_encounters() -> pl.DataFrame:
    def row(
        encounter: int,
        *,
        severity: int,
        onset_hours: int | None,
        calculated_category: str,
        calculated_poa_status: str | None,
        billed_category: str,
        length_of_stay: int,
        death_flag: int,
    ) -> dict:
        return {
            "EncounterEpicCsn": encounter,
            "Arrival_Instant": BASE_TIME,
            "InpatientAdmissionInstant": BASE_TIME + timedelta(hours=2),
            "LengthOfStayInDays": length_of_stay,
            "Death_Flag": death_flag,
            "Sepsis_Category": billed_category,
            "calculated_sepsis_severity": severity,
            "first_sepsis_dt": (
                None
                if onset_hours is None
                else BASE_TIME + timedelta(hours=onset_hours)
            ),
            "calculated_poa_status": calculated_poa_status,
            "calculated_sepsis_category": calculated_category,
        }

    return pl.DataFrame(
        [
            row(
                1,
                severity=1,
                onset_hours=1,
                calculated_category="POA-1",
                calculated_poa_status="POA",
                billed_category="POA-1",
                length_of_stay=4,
                death_flag=0,
            ),
            row(
                2,
                severity=2,
                onset_hours=60,
                calculated_category="NPOA-2",
                calculated_poa_status="NPOA",
                billed_category="UPOA-2",
                length_of_stay=8,
                death_flag=1,
            ),
            row(
                3,
                severity=0,
                onset_hours=None,
                calculated_category="No Sepsis",
                calculated_poa_status=None,
                billed_category="POA-1",
                length_of_stay=3,
                death_flag=0,
            ),
            row(
                4,
                severity=3,
                onset_hours=3,
                calculated_category="POA-3",
                calculated_poa_status="POA",
                billed_category="NPOA-3",
                length_of_stay=12,
                death_flag=1,
            ),
            row(
                5,
                severity=2,
                onset_hours=72,
                calculated_category="NPOA-2",
                calculated_poa_status="NPOA",
                billed_category="POA-2",
                length_of_stay=6,
                death_flag=0,
            ),
            row(
                6,
                severity=1,
                onset_hours=2,
                calculated_category="POA-1",
                calculated_poa_status="POA",
                billed_category="NPOA-1",
                length_of_stay=5,
                death_flag=0,
            ),
        ],
        schema_overrides={
            "EncounterEpicCsn": pl.Int64,
            "LengthOfStayInDays": pl.Int64,
            "Death_Flag": pl.Int64,
            "calculated_sepsis_severity": pl.Int8,
        },
    )


def _vasopressor_evidence() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "EncounterEpicCsn": [1, 4, 5, 6],
            "vasopressor_administration_time": [
                BASE_TIME + timedelta(hours=1),
                BASE_TIME + timedelta(hours=50),
                BASE_TIME + timedelta(hours=10),
                BASE_TIME + timedelta(hours=1),
            ],
            "vasopressor_qualifying_dose_flag": [1, 1, 1, 0],
        },
        schema_overrides={
            "EncounterEpicCsn": pl.Int64,
            "vasopressor_qualifying_dose_flag": pl.Int8,
        },
    )


def _analysis_tables() -> dict[str, pl.DataFrame]:
    pipeline = Phase4CoreAnalysisPipeline(
        clinical_run_dir=Path("unused-in-unit-test"),
        output_dir=Path("unused-in-unit-test"),
    )
    inputs = Phase4AnalysisInputs(
        sepsis_encounters=_sepsis_encounters(),
        vasopressor_evidence=_vasopressor_evidence(),
    )
    cohort = pipeline.prepare_cohort(inputs)
    return pipeline.build_tables(inputs, cohort)


def test_analysis_cohort_excludes_no_sepsis_and_billed_upoa() -> None:
    cohort = build_analysis_cohort(
        _sepsis_encounters(),
        phase4_analysis_config,
    )

    assert cohort["EncounterEpicCsn"].to_list() == [1, 4, 5, 6]
    assert not cohort["Sepsis_Category"].str.starts_with("UPOA-").any()
    assert cohort["calculated_sepsis_severity"].min() > 0
    assert (
        cohort.filter(pl.col("EncounterEpicCsn") == 1)
        ["calculated_inpatient_category"]
        .item()
        == "POA-1"
    )


def test_analysis_tables_are_aggregate_and_cover_active_analyses() -> None:
    tables = _analysis_tables()

    assert set(tables) == set(phase4_analysis_config.output_filenames)
    assert all(ENCOUNTER_COL not in table.columns for table in tables.values())

    category_counts = tables["category_counts"]
    assert category_counts["category_source"].n_unique() == 3
    assert (
        category_counts.group_by("category_source")
        .agg(pl.col("encounter_count").sum())
        ["encounter_count"]
        .to_list()
        == [4, 4, 4]
    )

    crosstabs = tables["category_crosstabs"]
    assert crosstabs.height == 2 * 6 * 6
    assert (
        crosstabs.group_by("calculated_reference")
        .agg(pl.col("encounter_count").sum())
        ["encounter_count"]
        .to_list()
        == [4, 4]
    )

    mortality_targets = tables["mortality_agreement"].select(
        "comparison",
        "target",
    ).unique()
    assert mortality_targets.filter(
        (pl.col("comparison") == "category") & (pl.col("target") == "POA-2")
    ).height == 1


def test_vasopressor_windows_use_only_qualifying_administrations() -> None:
    tables = _analysis_tables()
    counts = tables["vasopressor_window_category_counts"]

    denominators = counts.select(
        "vasopressor_window",
        "category_source",
        "denominator",
    ).unique()
    assert denominators["denominator"].to_list() == [2, 2, 2, 2]


def test_figure_pipeline_renders_complete_configured_inventory(
    tmp_path: Path,
) -> None:
    pipeline = Phase4FigurePipeline(
        analysis_dir=Path("unused-in-render-test"),
        output_dir=tmp_path,
    )

    pipeline._render_figures(_analysis_tables())

    rendered = {path.name for path in tmp_path.glob("*.png")}
    assert rendered == set(phase4_figure_config.figure_filenames)
    assert len(rendered) == 25
    assert all((tmp_path / filename).stat().st_size > 0 for filename in rendered)
