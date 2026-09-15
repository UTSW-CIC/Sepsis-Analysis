"""Strategy/Registry composition for septic-shock criteria."""

from ...configs.septicshock import (
    SepticShockConfig,
    SepticShockCriterionName,
    septicshock_config,
)
from ...pipeline import AnyReducer, Pipeline
from .criteria import (
    EffectiveHypotensionCriterion,
    Lactate4Criterion,
    MAP65Criterion,
    SBP90Criterion,
    SBPDelta40Criterion,
    VasopressorCriterion,
)


SEPTIC_SHOCK_CRITERION_REGISTRY = {
    SepticShockCriterionName.SBP_90: SBP90Criterion,
    SepticShockCriterionName.SBP_DELTA_40: SBPDelta40Criterion,
    SepticShockCriterionName.MAP_65: MAP65Criterion,
    SepticShockCriterionName.LACTATE_4: Lactate4Criterion,
    SepticShockCriterionName.VASOPRESSOR: VasopressorCriterion,
}


class SepticShockPipeline(Pipeline):
    def __init__(
        self,
        config: SepticShockConfig = septicshock_config,
        *,
        use_filtered_hypotension: bool = False,
    ):
        criteria = [
            SEPTIC_SHOCK_CRITERION_REGISTRY[name](config)
            for name in config.selected
        ]
        if use_filtered_hypotension:
            bp_names = {
                SepticShockCriterionName.SBP_90,
                SepticShockCriterionName.SBP_DELTA_40,
                SepticShockCriterionName.MAP_65,
            }
            for name, criterion in zip(config.selected, criteria):
                if name in bp_names:
                    # Retain raw BP flags as evidence, but let only the existing
                    # duration-filter result contribute to shock composition.
                    criterion.role = "evidence"
            if any(name in bp_names for name in config.selected):
                criteria.append(EffectiveHypotensionCriterion(config))
        super().__init__(config, criteria, AnyReducer(config.flag_col))


def build_septic_shock_pipeline(
    config: SepticShockConfig = septicshock_config,
    *,
    use_filtered_hypotension: bool = False,
) -> SepticShockPipeline:
    return SepticShockPipeline(
        config,
        use_filtered_hypotension=use_filtered_hypotension,
    )
