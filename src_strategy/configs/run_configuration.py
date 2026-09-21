"""Explicit registry of configuration used by the active clinical run."""

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, Field

from .dataconfig import bp_config
from .organdysfunction import organdysfunction_config
from .pulmonarydysfunction import pf_config, pulmonary_dysfunction_config
from .septicshock import septicshock_config
from .severitysepsis import severitysepsisconfig
from .shortdurationfilter import (
    bp_episode_filter_config,
    sirs_episode_filter_config,
)
from .sirscalculator import sirs_config
from .suspected_infection import suspected_infection_config


_NESTED_SEVERITY_CONFIG_FIELDS = {
    "suspected_infection_config",
    "sirs_config",
    "organdysfunction_config",
    "pulmonarydysfunction_config",
    "septicshock_config",
}


class RunIdentityConfig(BaseModel):
    """Committed semantic labels used above an individual run directory."""

    dataset_version: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]*$")
    algorithm_variant: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]*$")
    clinical_definition_version: str = Field(min_length=1)


run_identity_config = RunIdentityConfig(
    dataset_version="phase3_2026-06-05",
    algorithm_variant="first_per_organ_type",
    clinical_definition_version="3_1",
)


def active_run_configuration_sections() -> dict[
    str,
    BaseModel | Mapping[str, Any],
]:
    """Return result-affecting configuration executed by `main_strategy.py`."""
    # Each nested clinical configuration is registered independently below.
    # Keep only Sepsis association/composition settings in this section so the
    # canonical snapshot has one obvious location for every setting.
    sepsis_composition = severitysepsisconfig.model_dump(
        mode="json",
        exclude=_NESTED_SEVERITY_CONFIG_FIELDS,
    )

    return {
        "blood_pressure_input": bp_config,
        "pf_ratio_builder": pf_config,
        "pulmonary_dysfunction": pulmonary_dysfunction_config,
        "organ_dysfunction": organdysfunction_config,
        "suspected_infection": suspected_infection_config,
        "sirs": sirs_config,
        "septic_shock": septicshock_config,
        "sepsis_composition": sepsis_composition,
        "sirs_episode_filter": sirs_episode_filter_config,
        "bp_episode_filter": bp_episode_filter_config,
    }
