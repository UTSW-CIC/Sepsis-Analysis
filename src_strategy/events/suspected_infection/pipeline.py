import polars as pl

from ...configs.suspected_infection import (
    SuspectedInfectionConfig,
    SuspectedInfectionCriterionName,
    suspected_infection_config,
)
from .criteria import (
    AntibioticCultureCriterion,
    CodeSepsisCriterion,
    LactateCultureCriterion,
    SuspectedInfectionCriterion,
    SuspectedInfectionFlowsheetCriterion,
)


SUSPECTED_INFECTION_CRITERION_REGISTRY: dict[
    SuspectedInfectionCriterionName,
    type[SuspectedInfectionCriterion],
] = {
    SuspectedInfectionCriterionName.ANTIBIOTIC_CULTURE: AntibioticCultureCriterion,
    SuspectedInfectionCriterionName.LACTATE_CULTURE: LactateCultureCriterion,
    SuspectedInfectionCriterionName.CODE_SEPSIS: CodeSepsisCriterion,
    SuspectedInfectionCriterionName.FLOWSHEET: SuspectedInfectionFlowsheetCriterion,
}


class SuspectedInfectionPipeline:
    """Run registered infection criteria and combine their evidence long frames."""

    def __init__(
        self,
        config: SuspectedInfectionConfig = suspected_infection_config,
    ):
        self.config = config
        self.criteria = [
            SUSPECTED_INFECTION_CRITERION_REGISTRY[name](config)
            for name in config.selected
        ]

    def process(self, df: pl.DataFrame) -> pl.DataFrame:
        evidence_frames = [criterion.detect(df) for criterion in self.criteria]
        result = pl.concat(evidence_frames, how="vertical")
        return result.sort(
            self.config.encounter_col,
            self.config.value_name_dt_col,
            self.config.value_type_col,
            self.config.variable_name_col,
        )

    def detect_infection_longframe(self, df: pl.DataFrame) -> pl.DataFrame:
        """Compatibility name for the old long-frame entry point."""
        return self.process(df)


def build_suspected_infection_pipeline(
    config: SuspectedInfectionConfig = suspected_infection_config,
) -> SuspectedInfectionPipeline:
    return SuspectedInfectionPipeline(config)
