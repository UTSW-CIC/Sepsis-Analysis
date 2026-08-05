from ...configs.sirscalculator import (
    SIRSConfig,
    SIRSCriterionName,
    sirs_config,
)
from ...pipeline import Pipeline, SumReducer
from .criteria import (
    HeartRateCriterion,
    RespiratoryRateCriterion,
    TemperatureCriterion,
    WBCCriterion,
)


SIRS_CRITERION_REGISTRY = {
    SIRSCriterionName.TEMPERATURE: TemperatureCriterion,
    SIRSCriterionName.HEART_RATE: HeartRateCriterion,
    SIRSCriterionName.RESPIRATORY_RATE: RespiratoryRateCriterion,
    SIRSCriterionName.WBC: WBCCriterion,
}


class SIRSPipeline(Pipeline):
    def __init__(self, config: SIRSConfig = sirs_config):
        criteria = [
            SIRS_CRITERION_REGISTRY[name](config)
            for name in config.selected
        ]
        reducer = SumReducer(score_col=config.sirs_score_col)
        super().__init__(config, criteria, reducer)


def build_sirs_pipeline(config: SIRSConfig = sirs_config) -> SIRSPipeline:
    return SIRSPipeline(config)
