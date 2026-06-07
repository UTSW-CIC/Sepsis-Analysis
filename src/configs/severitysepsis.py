"""
Sepsis 1: Two or more SIRS Criteria are met
Sepsis 2: Sepsis 1 + one or more organ dysfunction
Sepsis 3: Septic shock (There is a dedicated class, and config for this)
"""

from pydantic import Field

from .sirscalculator import SIRSConfig, sirs_config
from .organdysfunction import OrganDysfunctionConfig, organdysfunction_config
from .suspected_infection import suspected_infection_config, SuspectedInfectionConfig
from .dataconfig import DataConfig
from .septicshock import septicshock_config, SepticShockConfig
from .pulmonarydysfunction import pulmonary_dysfunction_config, PulmonaryDysfunctionConfig

class SeveritySepsisConfig(DataConfig):
    suspected_infection_config: SuspectedInfectionConfig = suspected_infection_config
    sirs_config: SIRSConfig = sirs_config
    organdysfunction_config: OrganDysfunctionConfig = organdysfunction_config
    pulmonarydysfunction_config: PulmonaryDysfunctionConfig = pulmonary_dysfunction_config
    septicshock_config: SepticShockConfig = septicshock_config

    infection_2_sirs_forward_hrs: float = Field(default=24, description="Number of hours to look forward for sepsis 1")
    infection_2_sirs_backward_hrs: float = Field(default=24, description="Number of hours to look backward for sepsis 1")

    infection_2_organdysfunction_forward_hrs: float = Field(default=48, description="Number of hours to look forward for sepsis 2")
    infection_2_organdysfunction_backward_hrs: float = Field(default=48, description="Number of hours to look backward for sepsis 2")

    infection_2_shock_dysfunction_forward_hrs: float = Field(default=48, description="Number of hours to look forward for septic shock")
    infection_2_shock_dysfunction_backward_hrs: float = Field(default=48, description="Number of hours to look backward for septic shock")

    sepsis_state_period_from_infection_hrs: float = Field(default=24*14, description="Number of hours to look forward and backward from infection for sepsis state") # 14 days

    septic_shock_suffix: str = Field(default='_septicshock', description="Suffix used for septic shock detection criteria when joined with other criteria")
    earliest_sepsis1_instance: str = Field(default="earliest_sepsis1_instance", description="Column name for earliest sepsis 1 instance")
    earliest_sepsis2_instance: str = Field(default="earliest_sepsis2_instance", description="Column name for earliest sepsis 2 instance")
    earliest_sepsis3_instance: str = Field(default="earliest_sepsis3_instance", description="Column name for earliest sepsis 3 instance")


severitysepsisconfig = SeveritySepsisConfig()