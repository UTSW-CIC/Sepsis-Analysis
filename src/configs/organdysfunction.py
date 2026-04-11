from pydantic import BaseModel, Field
from typing import List 
from .dataconfig import DataConfig
from .aggregator import FeatureColumn, BaselineColumn, vent_config, VentConfig

class CardiovascularConfig(BaseModel):
    lactate_col: FeatureColumn      = FeatureColumn.LAST_LACTATE_6H
    lactate_threshold: float            = 2
    flag_col: str = "cardiovascular_failure_flag"

class RenalConfig(BaseModel):
    creatinine_col: FeatureColumn   = FeatureColumn.LAST_CREATININE_12H
    egfr_col: FeatureColumn         = FeatureColumn.LAST_EGFR_12H
    baseline_creatinine_col: str    = BaselineColumn.BASELINE_CREATININE
    baseline_egfr_col: str          = BaselineColumn.BASELINE_eGFR
    creatinine_threshold: float     = 2.0
    egfr_multiplier: float             = 0.5
    creatinine_multiplier: float    = 2.0
    flag_col: str = "renal_failure_flag"

class HepaticConfig(BaseModel):
    bilirubin_col: FeatureColumn    = FeatureColumn.LAST_BILIRUBIN_12H
    baseline_bilirubin_col: BaselineColumn     = BaselineColumn.BASELINE_BILIRUBIN
    bilirubin_threshold: float      = 2.0
    bilirubin_multiplier: float     = 2.0
    flag_col: str = "hepatic_failure_flag"

class CoagulationConfig(BaseModel):
    platelets_col: FeatureColumn    = FeatureColumn.LAST_PLATELETS_24H
    inr_col: FeatureColumn          = FeatureColumn.LAST_INR_12H
    aptt_col: FeatureColumn         = FeatureColumn.LAST_APTT_24H
    baseline_platelets_col: BaselineColumn     = BaselineColumn.BASELINE_PLATELETS
    platelets_threshold: float      = 100.0
    inr_threshold: float            = 1.5
    aptt_threshold: float           = 60.0
    platelets_multiplier: float        = 0.5
    # Flags
    inr_flag: str = "inr_criteria_flag"
    aptt_flag: str = "aptt_criteria_flag"
    platelets50_flag: str = "platelets50_criteria_flag"
    platelets100_flag: str = "platelets100_criteria_flag"

    # Final flag
    flag_col: str = "coagulation_failure_flag"

class NeurologicalConfig(BaseModel):
    gcs_col: FeatureColumn          = FeatureColumn.LAST_GCS_12H
    gcs_threshold: float            = 15.0
    flag_col: str = "neurological_failure_flag"

class PulmonaryConfig(BaseModel):
    vent_config: VentConfig = vent_config
    vent_col: FeatureColumn         = FeatureColumn.VENT_STATUS_FLAG
    vent_on_status: str = "Vent on Documentation"
    vent_off_status: str = "Vent off Documentation"
    flag_col: str = "pulmonary_failure_flag"

class BaselineConfig(BaseModel):
    baseline_creatinine_col: str = "Baseline_Creatinine"
    baseline_egfr_col: str = "Baseline_eGFR"
    baseline_bilirubin_col: str = "Baseline_Bilirubin"
    baseline_platelets_col: str = "Baseline_Platelets"
    # baseline_inr_col: str = "Baseline_INR"
    baseline_SBP_col: str ="Baseline_SBP"
    baseline_resp_rate_col: str = "Baseline_RespiratoryRate"
    baseline_pulse_col: str = "Baseline_PulseRate"
    baseline_wbc_col: str = "Baseline_WBC"

    @property
    def columns(self) -> List[str]:
        return [
            self.baseline_creatinine_col,
            self.baseline_egfr_col,
            self.baseline_bilirubin_col,
            self.baseline_platelets_col,
            # self.baseline_inr_col,
            self.baseline_SBP_col,
            self.baseline_resp_rate_col,
            self.baseline_pulse_col,
            self.baseline_wbc_col
        ]

class OrganDysfunctionConfig(DataConfig):
    cardiovascular: CardiovascularConfig    = CardiovascularConfig()
    renal: RenalConfig                      = RenalConfig()
    hepatic: HepaticConfig                  = HepaticConfig()
    coagulation: CoagulationConfig          = CoagulationConfig()
    neurological: NeurologicalConfig        = NeurologicalConfig()
    pulmonary: PulmonaryConfig              = PulmonaryConfig()
    baseline: BaselineConfig                = BaselineConfig()
    flag_col: str = "organ_dysfunction_total"


organdysfunction_config = OrganDysfunctionConfig()