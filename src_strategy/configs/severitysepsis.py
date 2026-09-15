"""
Sepsis 1: suspected infection + two or more SIRS criteria
Sepsis 2: suspected infection + one or more organ dysfunctions
Sepsis 3: Sepsis 2 + septic shock
"""

from math import isfinite

from pydantic import Field, model_validator

from .dataconfig import DataConfig
from .organdysfunction import OrganDysfunctionConfig, organdysfunction_config
from .pulmonarydysfunction import (
    PulmonaryDysfunctionConfig,
    pulmonary_dysfunction_config,
)
from .septicshock import SepticShockConfig, septicshock_config
from .sirscalculator import SIRSConfig, sirs_config
from .suspected_infection import (
    SuspectedInfectionConfig,
    suspected_infection_config,
)


class SeveritySepsisConfig(DataConfig):
    suspected_infection_config: SuspectedInfectionConfig = (
        suspected_infection_config
    )
    sirs_config: SIRSConfig = sirs_config
    organdysfunction_config: OrganDysfunctionConfig = organdysfunction_config
    pulmonarydysfunction_config: PulmonaryDysfunctionConfig = (
        pulmonary_dysfunction_config
    )
    septicshock_config: SepticShockConfig = septicshock_config

    infection_2_sirs_forward_hrs: float = Field(
        default=24,
        description="Number of hours to look forward for sepsis 1",
    )
    infection_2_sirs_backward_hrs: float = Field(
        default=24,
        description="Number of hours to look backward for sepsis 1",
    )

    infection_anchor_id_col: str = "infection_anchor_id"
    sirs_episode_id_col: str = "sirs_episode_id"
    effective_sirs_positive_flag_col: str = "effective_sirs_positive_flag"
    sirs_filter_applied_col: str = "sirs_filter_applied"
    sepsis1_flag_col: str = "sepsis_1_flag"
    sepsis1_dt_col: str = "sepsis_1_dt"
    sepsis1_earliest_evidence_dt_col: str = "sepsis_1_earliest_evidence_dt"
    sepsis1_association_count_col: str = "sepsis_1_association_count"
    sepsis1_anchor_count_col: str = "sepsis_1_anchor_count"
    sepsis1_sirs_episode_count_col: str = "sepsis_1_sirs_episode_count"

    infection_2_organdysfunction_forward_hrs: float = Field(
        default=48,
        description="Number of hours to look forward for sepsis 2",
    )
    infection_2_organdysfunction_backward_hrs: float = Field(
        default=48,
        description="Number of hours to look backward for sepsis 2",
    )
    organ_episode_id_col: str = "organ_episode_id"
    sepsis2_flag_col: str = "sepsis_2_flag"
    sepsis2_dt_col: str = "sepsis_2_dt"
    sepsis2_earliest_evidence_dt_col: str = (
        "sepsis_2_earliest_evidence_dt"
    )
    sepsis2_association_count_col: str = "sepsis_2_association_count"
    sepsis2_anchor_count_col: str = "sepsis_2_anchor_count"
    sepsis2_organ_episode_count_col: str = (
        "sepsis_2_organ_episode_count"
    )

    infection_2_shock_dysfunction_forward_hrs: float = Field(
        default=48,
        description="Number of hours to look forward for septic shock",
    )
    infection_2_shock_dysfunction_backward_hrs: float = Field(
        default=48,
        description="Number of hours to look backward for septic shock",
    )
    shock_episode_id_col: str = "shock_episode_id"
    shock_point_id_col: str = "shock_point_id"
    sepsis3_flag_col: str = "sepsis_3_flag"
    sepsis3_dt_col: str = "sepsis_3_dt"
    sepsis3_earliest_evidence_dt_col: str = (
        "sepsis_3_earliest_evidence_dt"
    )
    sepsis3_association_count_col: str = "sepsis_3_association_count"
    sepsis3_anchor_count_col: str = "sepsis_3_anchor_count"
    sepsis3_organ_episode_count_col: str = (
        "sepsis_3_organ_episode_count"
    )
    sepsis3_shock_evidence_count_col: str = (
        "sepsis_3_shock_evidence_count"
    )

    sepsis_state_period_from_infection_hrs: float = Field(
        default=24 * 14,
        description=(
            "Number of hours to look forward and backward from infection for "
            "sepsis state"
        ),
    )  # 14 days

    septic_shock_suffix: str = Field(
        default="_septicshock",
        description=(
            "Suffix used for septic shock detection criteria when joined with "
            "other criteria"
        ),
    )
    earliest_sepsis1_instance: str = Field(
        default="earliest_sepsis1_instance",
        description="Column name for earliest sepsis 1 instance",
    )
    earliest_sepsis2_instance: str = Field(
        default="earliest_sepsis2_instance",
        description="Column name for earliest sepsis 2 instance",
    )
    earliest_sepsis3_instance: str = Field(
        default="earliest_sepsis3_instance",
        description="Column name for earliest sepsis 3 instance",
    )

    @model_validator(mode="after")
    def validate_windows(self) -> "SeveritySepsisConfig":
        windows = {
            "infection_2_sirs_forward_hrs": self.infection_2_sirs_forward_hrs,
            "infection_2_sirs_backward_hrs": self.infection_2_sirs_backward_hrs,
            "infection_2_organdysfunction_forward_hrs": (
                self.infection_2_organdysfunction_forward_hrs
            ),
            "infection_2_organdysfunction_backward_hrs": (
                self.infection_2_organdysfunction_backward_hrs
            ),
            "infection_2_shock_dysfunction_forward_hrs": (
                self.infection_2_shock_dysfunction_forward_hrs
            ),
            "infection_2_shock_dysfunction_backward_hrs": (
                self.infection_2_shock_dysfunction_backward_hrs
            ),
        }
        invalid = [
            name
            for name, value in windows.items()
            if not isfinite(value) or value < 0
        ]
        if invalid:
            raise ValueError(
                f"Sepsis association windows must be finite and non-negative: {invalid}"
            )
        return self


severitysepsisconfig = SeveritySepsisConfig()
