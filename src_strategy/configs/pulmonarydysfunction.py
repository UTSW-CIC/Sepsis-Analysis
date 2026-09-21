"""Configuration for P/F evidence and pulmonary dysfunction transitions."""

from enum import Enum

from pydantic import BaseModel, Field, model_validator

from .dataconfig import DataConfig


class PulmonaryStartCriterionName(str, Enum):
    VENT_DOCUMENTATION = "vent_documentation"
    VENT_ON_OFF = "vent_on_off"
    MECHANICAL_O2 = "mechanical_o2"
    PF_RATIO = "pf_ratio"


class PulmonaryTerminationCriterionName(str, Enum):
    VENT_DOCUMENTATION = "vent_documentation"
    VENT_ON_OFF = "vent_on_off"
    O2_DELIVERY = "o2_delivery"
    PF_RATIO = "pf_ratio"


class VentOnOffConfig(BaseModel):
    grouper: str = "Vent On/Off"
    start_values: list[str] = Field(
        default_factory=lambda: [
            "On Going Hospital Vent",
            "Initial",
            "$ On Going Hospital Vent",
        ]
    )
    termination_values: list[str] = Field(
        # default_factory=lambda: ["Standby", "$ Extubation"]
        default_factory=lambda: ["$ Extubation"]
    )
    null_value_terminates: bool = False 
    start_flag_col: str = "vent_onoff_start_flag"
    termination_flag_col: str = "vent_onoff_termination_flag"

    @model_validator(mode="after")
    def validate_values(self) -> "VentOnOffConfig":
        if set(self.start_values) & set(self.termination_values):
            raise ValueError(
                "Vent On/Off start and termination values cannot overlap"
            )
        return self


class VentDocumentationConfig(BaseModel):
    start_grouper: str = "Vent on Documentation"
    termination_grouper: str = "Vent off Documentation"
    start_flag_col: str = "vent_documentation_start_flag"
    termination_flag_col: str = "vent_documentation_termination_flag"


class PFConfig(DataConfig):
    pao2_grouper_val: str = "PAO2"
    fio2_grouper_val: str = "FIO2"
    threshold: float = 200.0
    time_window_between_pao2_fio2_hrs: float = 2.0

    pf_ratio_col: str = "pf_ratio"
    pao2_value_col: str = "pf_pao2_value"
    pao2_time_col: str = "pf_pao2_time"
    fio2_value_col: str = "pf_fio2_value"
    fio2_fraction_col: str = "pf_fio2_fraction"
    fio2_time_col: str = "pf_fio2_time"
    pf_ratio_time_col: str = "pf_ratio_time"
    pair_status_col: str = "pf_pair_status"
    paired_status: str = "paired"
    invalid_pao2_status: str = "invalid_pao2"
    no_valid_fio2_status: str = "no_valid_fio2_within_window"
    start_flag_col: str = "pf_ratio_start_flag"
    termination_flag_col: str = "pf_ratio_termination_flag"

    @model_validator(mode="after")
    def validate_thresholds(self) -> "PFConfig":
        if self.threshold <= 0:
            raise ValueError("P/F threshold must be positive")
        if self.time_window_between_pao2_fio2_hrs <= 0:
            raise ValueError("P/F pairing window must be positive")
        return self


class O2DeliveryConfig(BaseModel):
    mechanical_grouper: str = "O2 Delivery Mechanical Ventilation"
    mechanical_start_values: list[str] = Field(
        default_factory=lambda: [
            "mechanical ventilator",
            "ventilator",
            "BiPAP",
            "CPAP",
            "NPPV/NIV",
        ]
    )
    termination_groupers: list[str] = Field(
        default_factory=lambda: [
            "O2 Delivery Nasal Cannula",
            "O2 Delivery Simple Face Mask",
            "O2 Delivery Room Air",
        ]
    )
    high_flow_termination_grouper: str = "O2 Delivery High-Flow"
    high_flow_termination_values: list[str] = Field(
        default_factory=lambda: [
            "high-flow nasal cannula",
            "high-flow nasal cannula;heated",
            "high-flow nasal cannula;humidified",
            "humidified;high-flow nasal cannula",
            "high-flow mask",
        ]
    )
    non_rebreather_termination_grouper: str = (
        "O2 Delivery Non-Rebreather Mask"
    )
    non_rebreather_termination_values: list[str] = Field(
        default_factory=lambda: [
            "nonrebreather mask",
            "partial rebreather mask",
            "blender system",
        ]
    )
    start_flag_col: str = "mechanical_o2_start_flag"
    termination_flag_col: str = "o2_delivery_termination_flag"

    @property
    def all_termination_groupers(self) -> list[str]:
        return [
            *self.termination_groupers,
            self.high_flow_termination_grouper,
            self.non_rebreather_termination_grouper,
        ]


class ExcludedEncounterConfig(BaseModel):
    diagnosis_codes: list[str] = Field(
        default_factory=lambda: ["Z99.11", "Z93.0"]
    )
    home_vent_grouper: str = "Vent On/Off"
    home_vent_value: str = "$ Home Vent Used"
    flag_col: str = "pulmonary_exclusion_flag"
    reason_col: str = "pulmonary_exclusion_reason"
    evidence_time_col: str = "pulmonary_exclusion_time"


class PulmonaryDysfunctionConfig(DataConfig):
    vent_onoff: VentOnOffConfig = Field(default_factory=VentOnOffConfig)
    vent_documentation: VentDocumentationConfig = Field(
        default_factory=VentDocumentationConfig
    )
    pf: PFConfig = Field(default_factory=PFConfig)
    o2_delivery: O2DeliveryConfig = Field(default_factory=O2DeliveryConfig)
    exclusions: ExcludedEncounterConfig = Field(
        default_factory=ExcludedEncounterConfig
    )
    selected_start: list[PulmonaryStartCriterionName] = Field(
        default_factory=lambda: list(PulmonaryStartCriterionName)
    )
    selected_termination: list[PulmonaryTerminationCriterionName] = Field(
        default_factory=lambda: [
            PulmonaryTerminationCriterionName.VENT_DOCUMENTATION,
            PulmonaryTerminationCriterionName.VENT_ON_OFF,
            PulmonaryTerminationCriterionName.O2_DELIVERY,
        ]
    )

    start_flag_col: str = "pulmonary_start_flag"
    termination_flag_col: str = "pulmonary_termination_flag"
    transition_state_col: str = "pulmonary_transition_state"
    transition_type_col: str = "pulmonary_transition_type"
    transition_time_col: str = "pulmonary_transition_time"
    state_time_col: str = "pulmonary_state_time"
    segment_start_col: str = "segment_start"
    segment_end_col: str = "segment_end"
    pulmonary_dysfunction_flag: str = "pulmonary_dysfunction_flag"

    @model_validator(mode="after")
    def validate_selected_start(self) -> "PulmonaryDysfunctionConfig":
        if len(self.selected_start) != len(set(self.selected_start)):
            raise ValueError("selected pulmonary start criteria must be unique")
        if not self.selected_start:
            raise ValueError("at least one pulmonary start criterion is required")
        if len(self.selected_termination) != len(
            set(self.selected_termination)
        ):
            raise ValueError(
                "selected pulmonary termination criteria must be unique"
            )
        if not self.selected_termination:
            raise ValueError(
                "at least one pulmonary termination criterion is required"
            )
        return self

    @property
    def required_event_columns(self) -> list[str]:
        return [
            self.encounter_col,
            self.event_dt_col,
            self.grouper_col,
            self.raw_val_col,
        ]

    @property
    def required_pf_columns(self) -> list[str]:
        return [
            self.encounter_col,
            self.pf.pf_ratio_col,
            self.pf.pf_ratio_time_col,
            self.pf.pair_status_col,
        ]


pulmonary_dysfunction_config = PulmonaryDysfunctionConfig()
pf_config = PFConfig()
