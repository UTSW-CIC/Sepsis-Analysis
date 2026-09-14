import polars as pl
import pytest

from src_strategy.events.organdysfunction import (
    prepare_organ_dysfunction_input,
)
from src_strategy.events.organdysfunction.input_preparation import (
    BASELINE_ROW_AVAILABLE,
)


def _aggregated_frame() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "EncounterEpicCsn": [2, 1, 3],
            "row_marker": ["first", "second", "third"],
            "last_lactate_6h": [2.0, 2.1, None],
        },
        schema_overrides={"last_lactate_6h": pl.Float64},
    )


def _encounter_frame() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "EncounterEpicCsn": [1, 2],
            "Baseline_Creatinine": [1.0, None],
            "Baseline_eGFR": [100.0, None],
            "Baseline_Bilirubin": [1.0, None],
            "Baseline_Platelets": [200.0, None],
        },
        schema_overrides={
            "Baseline_Creatinine": pl.Float64,
            "Baseline_eGFR": pl.Float64,
            "Baseline_Bilirubin": pl.Float64,
            "Baseline_Platelets": pl.Float64,
        },
    )


def test_baseline_join_preserves_aggregate_rows_order_and_columns() -> None:
    aggregated = _aggregated_frame()

    result = prepare_organ_dysfunction_input(
        aggregated,
        _encounter_frame(),
    )

    assert result.height == aggregated.height
    assert result.select(aggregated.columns).equals(aggregated)
    assert result["row_marker"].to_list() == ["first", "second", "third"]
    assert result["Baseline_Creatinine"].to_list() == [None, 1.0, None]


def test_baseline_join_distinguishes_null_values_from_missing_encounter() -> None:
    result = prepare_organ_dysfunction_input(
        _aggregated_frame(),
        _encounter_frame(),
    )

    assert result[BASELINE_ROW_AVAILABLE].to_list() == [True, True, False]
    assert result.filter(pl.col("EncounterEpicCsn") == 2).select(
        "Baseline_Creatinine",
        "Baseline_eGFR",
        "Baseline_Bilirubin",
        "Baseline_Platelets",
    ).row(0) == (None, None, None, None)


def test_baseline_join_rejects_duplicate_encounter_rows() -> None:
    encounters = pl.concat(
        [_encounter_frame(), _encounter_frame().filter(pl.col("EncounterEpicCsn") == 1)]
    )

    with pytest.raises(ValueError, match="duplicate encounter IDs"):
        prepare_organ_dysfunction_input(_aggregated_frame(), encounters)


def test_baseline_join_rejects_null_encounter_keys() -> None:
    aggregated = _aggregated_frame().with_columns(
        pl.when(pl.col("EncounterEpicCsn") == 3)
        .then(None)
        .otherwise(pl.col("EncounterEpicCsn"))
        .alias("EncounterEpicCsn")
    )

    with pytest.raises(ValueError, match="aggregate encounter identifiers"):
        prepare_organ_dysfunction_input(aggregated, _encounter_frame())


def test_baseline_join_rejects_missing_required_encounter_column() -> None:
    encounters = _encounter_frame().drop("Baseline_eGFR")

    with pytest.raises(ValueError, match="Baseline_eGFR"):
        prepare_organ_dysfunction_input(_aggregated_frame(), encounters)


@pytest.mark.parametrize(
    "protected_col",
    ["Baseline_Creatinine", BASELINE_ROW_AVAILABLE],
)
def test_baseline_join_never_overwrites_existing_columns(
    protected_col: str,
) -> None:
    aggregated = _aggregated_frame().with_columns(
        pl.lit(None).alias(protected_col)
    )

    with pytest.raises(ValueError, match="would overwrite"):
        prepare_organ_dysfunction_input(aggregated, _encounter_frame())
