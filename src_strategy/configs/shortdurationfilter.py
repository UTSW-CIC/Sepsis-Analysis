from math import isfinite

from pydantic import BaseModel, Field, model_validator


class EpisodeFilterConfig(BaseModel):
    """Clinical-neutral settings for one normalized status timeline."""

    status_name: str
    enabled: bool = True
    bridge_unknown: bool = False
    negative_gap_minutes: float = Field(default=20.0, ge=0)
    minimum_positive_minutes: float = Field(default=20.0, ge=0)

    @model_validator(mode="after")
    def validate_thresholds(self) -> "EpisodeFilterConfig":
        if not self.status_name.strip():
            raise ValueError("status_name cannot be empty")
        if not isfinite(self.negative_gap_minutes):
            raise ValueError("negative_gap_minutes must be finite")
        if not isfinite(self.minimum_positive_minutes):
            raise ValueError("minimum_positive_minutes must be finite")
        return self


# The first registered use is exploratory SIRS filtering. It is deliberately
# disabled so it cannot change the current classifier by default.
sirs_episode_filter_config = EpisodeFilterConfig(
    status_name="sirs",
    enabled=True,
    bridge_unknown=True,
    negative_gap_minutes=20.0,
    minimum_positive_minutes=20.0,
)
