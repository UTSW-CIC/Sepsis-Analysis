"""Evaluate auditable encounter-level cohort exclusions."""

import json

import polars as pl

from src_strategy.configs.encounter_exclusions import (
    EncounterExclusionConfig,
    EncounterExclusionRule,
)


AUDIT_SCHEMA = {
    "EncounterEpicCsn": pl.Int64,
    "exclusion_rule": pl.String,
    "source_column": pl.String,
    "operator": pl.String,
    "configured_value": pl.String,
    "observed_value": pl.String,
}


def _rule_expression(rule: EncounterExclusionRule) -> pl.Expr:
    """Translate one validated declarative rule into a Polars expression."""
    column = pl.col(rule.column)
    if rule.operator == "eq":
        expression = column == rule.value
    elif rule.operator == "ne":
        expression = column != rule.value
    elif rule.operator == "gt":
        expression = column > rule.value
    elif rule.operator == "ge":
        expression = column >= rule.value
    elif rule.operator == "lt":
        expression = column < rule.value
    elif rule.operator == "le":
        expression = column <= rule.value
    elif rule.operator == "in":
        expression = column.is_in(rule.value)
    elif rule.operator == "not_in":
        expression = ~column.is_in(rule.value)
    else:  # pragma: no cover - Pydantic rejects unsupported operators.
        raise ValueError(
            f"Unsupported encounter exclusion operator: {rule.operator}"
        )

    return expression.fill_null(rule.null_behavior == "exclude")


def _empty_audit(encounter_dtype: pl.DataType) -> pl.DataFrame:
    schema = dict(AUDIT_SCHEMA)
    schema["EncounterEpicCsn"] = encounter_dtype
    return pl.DataFrame(schema=schema)


def apply_encounter_exclusions(
    encounters: pl.DataFrame,
    config: EncounterExclusionConfig,
    *,
    encounter_col: str,
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Return eligible encounters and one audit row per matched rule."""
    if encounter_col not in encounters.columns:
        raise ValueError(
            f"Encounter table is missing encounter column {encounter_col!r}"
        )
    if encounters.select(pl.col(encounter_col).is_null().any()).item():
        raise ValueError("Encounter identifiers cannot be null")
    duplicate_count = (
        encounters.group_by(encounter_col)
        .len()
        .filter(pl.col("len") > 1)
        .height
    )
    if duplicate_count:
        raise ValueError(
            "Encounter exclusions require one row per encounter; found "
            f"{duplicate_count} duplicate encounter identifiers"
        )

    encounter_dtype = encounters.schema[encounter_col]
    active_rules = [
        rule for rule in config.rules if config.enabled and rule.enabled
    ]
    required_columns = {rule.column for rule in active_rules}
    missing_columns = sorted(required_columns.difference(encounters.columns))
    if missing_columns:
        raise ValueError(
            "Encounter exclusion rules reference missing columns: "
            f"{missing_columns}"
        )

    if not active_rules:
        if encounters.is_empty():
            raise ValueError("Encounter cohort cannot be empty")
        return encounters, _empty_audit(encounter_dtype)

    audit_frames = []
    match_expressions = []
    for rule in active_rules:
        expression = _rule_expression(rule)
        match_expressions.append(expression)
        configured_value = rule.model_dump(mode="json")["value"]
        audit_frames.append(
            encounters.filter(expression).select(
                pl.col(encounter_col).alias("EncounterEpicCsn"),
                pl.lit(rule.name).alias("exclusion_rule"),
                pl.lit(rule.column).alias("source_column"),
                pl.lit(rule.operator).alias("operator"),
                pl.lit(json.dumps(configured_value, sort_keys=True)).alias(
                    "configured_value"
                ),
                pl.col(rule.column).cast(pl.String).alias("observed_value"),
            )
        )

    excluded_expression = pl.any_horizontal(match_expressions)
    eligible = encounters.filter(~excluded_expression)
    if eligible.is_empty():
        raise ValueError("Encounter exclusions removed every encounter")

    audit = pl.concat(audit_frames, how="vertical").sort(
        "EncounterEpicCsn", "exclusion_rule"
    )
    excluded_ids = audit.select("EncounterEpicCsn").unique()
    if not eligible.join(
        excluded_ids,
        left_on=encounter_col,
        right_on="EncounterEpicCsn",
        how="inner",
    ).is_empty():
        raise AssertionError("Eligible and excluded encounter cohorts overlap")
    if eligible.height + excluded_ids.height != encounters.height:
        raise AssertionError("Encounter exclusion counts do not reconcile")

    return eligible, audit
