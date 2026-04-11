"""
Sepsis 1: Two or more SIRS Criteria are met
Sepsis 2: Sepsis 1 + one or more organ dysfunction
Sepsis 3: Septic shock (There is a dedicated class, and config for this)
"""


from .sirscalculator import SIRSConfig, sirs_config
from .organdysfunction import OrganDysfunctionConfig, organdysfunction_config
from .suspected_infection import suspected_infection_config, SuspectedInfectionConfig
from .dataconfig import DataConfig
from .septicshock import septicshock_config, SepticShockConfig

class SeveritySepsisConfig(DataConfig):
    suspected_infection_config: SuspectedInfectionConfig = suspected_infection_config
    sirs_config: SIRSConfig = sirs_config
    organdysfunction_config: OrganDysfunctionConfig = organdysfunction_config
    septicshock_config: SepticShockConfig = septicshock_config


severitysepsisconfig = SeveritySepsisConfig()