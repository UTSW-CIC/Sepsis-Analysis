from pydantic import model_validator
from .common import ThresholdingConfig, BoundConfig
from typing import ClassVar
from ..dataconfig import bp_config

class PhysiologicalBoundsConfig(ThresholdingConfig):
    """Shared Layer-1 mechanism: null any value outside what a LIVING human
    body can produce. Subclasses bind this to one data domain (flowsheets,
    labs) so each can be enabled/disabled independently.

    A subclass declares only REQUIRED_SIGNALS (loud-fail guarantee) and
    _DEFAULTS (the bounds). No method duplication.
    """

    REQUIRED_SIGNALS: ClassVar[set] = set()
    _DEFAULTS: ClassVar[dict] = {}

    @model_validator(mode="after")
    def validate_signals(self) -> "PhysiologicalBoundsConfig":
        missing = self.REQUIRED_SIGNALS - set(self.thresholds.keys())
        if missing:
            raise ValueError(
                f"{type(self).__name__} requires the following signals "
                f"that are not selected in ThresholdingConfig: {missing}"
            )
        return self

    @classmethod
    def with_defaults(cls, **overrides) -> "PhysiologicalBoundsConfig":
        defaults = {**cls._DEFAULTS}   # shallow copy; never mutate the class dict
        defaults.update(overrides)
        return cls(thresholds=defaults)


class FlowsheetBoundsConfig(PhysiologicalBoundsConfig):
    """Vitals from flowsheets. Toggle independently of labs."""

    REQUIRED_SIGNALS: ClassVar[set] = {"Pulse", "Blood Pressure", "Respirations", "Temperature"}

    _DEFAULTS: ClassVar[dict] = {
        "Pulse":          BoundConfig(upper_bound=250, lower_bound=20),
        "Blood Pressure": BoundConfig(upper_bound=300, lower_bound=40),
        "Respirations":   BoundConfig(upper_bound=60, lower_bound=4),
        "Temperature":    BoundConfig(upper_bound=113, lower_bound=77),  # Fahrenheit
    }


class BloodPressureBoundsConfig(PhysiologicalBoundsConfig):
    REQUIRED_SIGNALS: ClassVar[set] = {bp_config.sys_col, bp_config.dia_col, bp_config.map_col}

    _DEFAULTS: ClassVar[dict] = {
        bp_config.sys_col: BoundConfig(upper_bound=300, lower_bound=40),
        bp_config.dia_col: BoundConfig(upper_bound=250, lower_bound=10),
        bp_config.map_col: BoundConfig(upper_bound=300, lower_bound=20),
    }

class LabBoundsConfig(PhysiologicalBoundsConfig):
    """Lab results keyed by Event_Name. Toggle independently of flowsheets."""

    REQUIRED_SIGNALS: ClassVar[set] = {
        "PO2 ART", "FIO2", "WBC", "PLATELETS",
        "CREATININE", "BILIRUBIN, TOTAL", "LACTATE",
        "BUN", "INR", "EGFR CKD EPI CR",
    }

    _DEFAULTS: ClassVar[dict] = {
        # Blood gas
        "PO2 ART": BoundConfig(upper_bound=700, lower_bound=0.0),   # mmHg; obs max 632.5
        "FIO2":    BoundConfig(upper_bound=100, lower_bound=0.0),   # %; >100 impossible

        # Hematology
        "WBC":       BoundConfig(upper_bound=600, lower_bound=0.0),  # 1e9/L; obs 447.75
        "PLATELETS": BoundConfig(upper_bound=3000, lower_bound=0.0), # 1e9/L; obs 1931
        "INR":       BoundConfig(upper_bound=20, lower_bound=0.5),   # ratio; obs 14.08

        # Renal
        "CREATININE":     BoundConfig(upper_bound=40, lower_bound=0.0),   # mg/dL; obs 36.76
        "CREATININE POC": BoundConfig(upper_bound=40, lower_bound=0.0),
        "BUN":            BoundConfig(upper_bound=400, lower_bound=0.0),  # mg/dL; obs 350
        "BUN POC":        BoundConfig(upper_bound=400, lower_bound=0.0),

        # eGFR (reported estimate; ceiling must clear obs 185)
        "EGFR":                          BoundConfig(upper_bound=200, lower_bound=0.0),
        "EGFR CKD EPI CR":               BoundConfig(upper_bound=200, lower_bound=0.0),
        "EGFR CKD EPI CR POC":           BoundConfig(upper_bound=200, lower_bound=0.0),
        "EGFR CR BEDSIDE SCHWARTZ 2009": BoundConfig(upper_bound=200, lower_bound=0.0),  # peds; empty post-exclusion

        # Hepatic
        "TOTAL BILIRUBIN":  BoundConfig(upper_bound=75, lower_bound=0.0),  # mg/dL; obs 65.7
        "BILIRUBIN, TOTAL": BoundConfig(upper_bound=75, lower_bound=0.0),  # spelling variant

        # Perfusion
        "LACTATE":             BoundConfig(upper_bound=50, lower_bound=0.0),  # mmol/L; raised above obs 43.2
        "LACTIC ACID (ISTAT)": BoundConfig(upper_bound=50, lower_bound=0.0),
    }


flowsheet_bounds_config = FlowsheetBoundsConfig.with_defaults()
bp_bounds_config = BloodPressureBoundsConfig.with_defaults()
lab_bounds_config = LabBoundsConfig.with_defaults()