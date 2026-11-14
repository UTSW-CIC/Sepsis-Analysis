"""Declarative encounter-level cohort exclusion configuration."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


ScalarValue = int | float | str | date | bool
RuleValue = ScalarValue | tuple[ScalarValue, ...]


class EncounterExclusionRule(BaseModel):
    """One auditable single-column encounter exclusion rule."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    column: str = Field(min_length=1)
    operator: Literal["eq", "ne", "gt", "ge", "lt", "le", "in", "not_in"]
    value: RuleValue
    enabled: bool = True
    null_behavior: Literal["retain", "exclude"] = "retain"

    @model_validator(mode="after")
    def validate_value_shape(self) -> "EncounterExclusionRule":
        collection_operator = self.operator in {"in", "not_in"}
        collection_value = isinstance(self.value, tuple)
        if collection_operator and not collection_value:
            raise ValueError(f"Operator {self.operator!r} requires a tuple value")
        if not collection_operator and collection_value:
            raise ValueError(
                f"Operator {self.operator!r} requires a scalar value"
            )
        if collection_value and not self.value:
            raise ValueError("Collection-valued exclusion rules cannot be empty")
        return self


class EncounterExclusionConfig(BaseModel):
    """Encounter cohort policy applied by the Phase 4 V2 data loader."""

    model_config = ConfigDict(frozen=True)

    enabled: bool = True
    match_mode: Literal["any"] = "any"
    rules: tuple[EncounterExclusionRule, ...] = ()

    @model_validator(mode="after")
    def require_unique_rule_names(self) -> "EncounterExclusionConfig":
        names = [rule.name for rule in self.rules]
        if len(names) != len(set(names)):
            raise ValueError("Encounter exclusion rule names must be unique")
        return self


encounter_exclusion_config = EncounterExclusionConfig(
    rules=(
        EncounterExclusionRule(
            name="discharge_after_2026_09_30",
            column="DischargeDateValue",
            operator="gt",
            value=date(2026, 9, 30),
        ),
        EncounterExclusionRule(
            name="cancer_registry_positive",
            column="Cancer_Registry_YN",
            operator="eq",
            value=1,
            enabled=False
        ),
    )
)
