from ...configs.organdysfunction import (
    OrganDysfunctionConfig,
    OrganDysfunctionCriterionName,
    organdysfunction_config,
)
from ...pipeline import Pipeline, SumReducer
from .criteria import (
    CardiovascularCriterion,
    CoagulationCriterion,
    HepaticCriterion,
    NeurologicalCriterion,
    PulmonaryCriterion,
    RenalCriterion,
)


ORGAN_DYSFUNCTION_CRITERION_REGISTRY = {
    OrganDysfunctionCriterionName.CARDIOVASCULAR: CardiovascularCriterion,
    OrganDysfunctionCriterionName.PULMONARY: PulmonaryCriterion,
    OrganDysfunctionCriterionName.RENAL: RenalCriterion,
    OrganDysfunctionCriterionName.HEPATIC: HepaticCriterion,
    OrganDysfunctionCriterionName.COAGULATION: CoagulationCriterion,
    OrganDysfunctionCriterionName.NEUROLOGICAL: NeurologicalCriterion,
}


class OrganDysfunctionPipeline(Pipeline):
    def __init__(
        self,
        config: OrganDysfunctionConfig = organdysfunction_config,
    ):
        criteria = [
            ORGAN_DYSFUNCTION_CRITERION_REGISTRY[name](config)
            for name in config.selected
        ]
        reducer = SumReducer(score_col=config.flag_col)
        super().__init__(config, criteria, reducer)


def build_organ_dysfunction_pipeline(
    config: OrganDysfunctionConfig = organdysfunction_config,
) -> OrganDysfunctionPipeline:
    return OrganDysfunctionPipeline(config)
