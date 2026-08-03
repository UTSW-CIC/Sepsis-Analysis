from .dataconfig import DataConfig
from .aggregator import FeatureColumn
from pydantic import BaseModel, Field
from typing import List

class VentOnOffConfig(DataConfig):
    vent_grouper_val: str = Field(default='Vent On/Off', description="Value in the grouper column that indicates ventilation status.")
    vent_on_status: List[str] = Field(default_factory=lambda: ["On Going Hospital Vent", "Initial", "$ On Going Hospital Vent"], description="Value in the")
    # vent_off_status: List[str] = Field(default_factory=lambda: ["Standby", None], description="Termination events for vent on status")

    vent_on_off_flag: str = Field(default="vent_onoff_flag")


class VentDocumentationConfig(DataConfig):
    vent_doc_on_grouper_val_and_status: str = Field(default="Vent On Documentation")
    vent_document_on_flag: str = Field(default="vent_doc_flag")


class PFConfig(DataConfig):
    pao2_grouper_val: str = Field(default="PAO2", description="")
    fio2_grouper_val: str = Field(default="FIO2", description="")
    do_fiao2_scale: bool = Field(default=True, description="Scale fio2 values to be between 0 and 1")
    pf_lower_threshold: float = Field(default=200, description="lower Threshold for P/F ratio")

    time_window_between_pao2_fio2_hrs: float = 2.0
    fio2_suffix:str = Field(default="_fio2", description="Suffix to be added after joining with pao2")
    pf_ratio_col: str = Field(default="pf_ratio")
    pf_flag: str = Field(default="PF_Ratio_Flag")


class O2DeliveryConfig(DataConfig):
    mechanical_vent_grouper_val: str = Field(default="O2 Delivery Mechanical Ventilation")
    mechanical_vent_on_status: List[str] = Field(default_factory=lambda: ["ventilator", "mechanical ventilator", "CPAP", "NPPV/NIV"])

    mechanical_vent_flag: str = Field(default="o2_vent_flag")

class VentTerminationConfig(DataConfig):
    vent_documentation_grouper_val_and_status: str = Field(default="Vent Off Documentation")

    vent_onoff_grouper_val: str = Field(default="Vent On/Off")
    vent_onoff_status: List[str] = Field(default_factory=lambda: ["Standby"], description="Termination events for vent on status")
    vent_onoff_status_null: bool = True
     
    o2_delivery_grouper_and_status: List[str] = Field(default_factory=lambda: ["O2 Delivery Nasal Cannula", "O2 Delivery Room Air", "O2 Delivery Simple Face Mask"])
    pf_ratio_col: str = PFConfig().pf_ratio_col
    pf_lower_threshold: float = Field(default=200)

    termination_flag: str = Field(default="vent_end_flag")


class ExcludedEncounterConfig(DataConfig):
    vent_dep_raw_val: List[str] = Field(default_factory=lambda: ['Z99.11', 'Z93.0'])

    vent_dep_grouper_val: str = Field(default="Vent On/Off")
    vent_dep_grouper_expr: str = Field(default="$ Home Vent Used")

class PulmonaryDysfunctionConfig(DataConfig):
    vent_onoff_config: VentOnOffConfig = VentOnOffConfig() 
    vent_documentation_config: VentDocumentationConfig = VentDocumentationConfig()
    pf_config: PFConfig = PFConfig()
    o2_delivery_config: O2DeliveryConfig = O2DeliveryConfig()
    vent_termination_config: VentTerminationConfig = VentTerminationConfig()
    excluded_encounters_config: ExcludedEncounterConfig = ExcludedEncounterConfig()

    pulmonary_dysfunction_flag: str = Field(default="pulmonary_dysfunction_flag")

    @property
    def get_all_flag_cols(self):
        return [
            self.vent_onoff_config.vent_on_off_flag,
            self.vent_documentation_config.vent_document_on_flag,
            self.pf_config.pf_flag,
            self.o2_delivery_config.mechanical_vent_flag,
            self.vent_termination_config.termination_flag
        ]
    
    @property
    def set_flag_cols(self):
        return [
            self.vent_onoff_config.vent_on_off_flag,
            self.vent_documentation_config.vent_document_on_flag,
            self.pf_config.pf_flag,
            self.o2_delivery_config.mechanical_vent_flag,
        ]
    
    @property
    def term_flag_col(self):
        return self.vent_termination_config.termination_flag
        
    
    @property
    def pf_ratio_col(self):
        return [
            self.pf_config.pf_ratio_col
        ]

pulmonary_dysfunction_config = PulmonaryDysfunctionConfig()
pf_config = PFConfig() 
    # vent_on_status: str = "Vent on Documentation"
    # vent_off_status: str = "Vent off Documentation"

    # o2_grouper_val: str = "O2 Delivery High-Flow"

    # evt_val_col: str = "evt_vent"
    # evt_dt_col: str = "evt_dt_vent"

    # o2_evt_val_col: str = "evt_o2"
    # o2_evt_dt_col: str = "evt_dt_o2"
    # alias: str = "Last_Vent_Status"
    # vent_alias: str = FeatureColumn.VENT_STATUS_FLAG
    # vent_dt_alias: str = FeatureColumn.VENT_STATUS_TIME
    # o2_alias: str = FeatureColumn.O2_DELIVERY_FLAG
