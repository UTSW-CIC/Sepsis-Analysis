from pydantic import BaseModel, Field
from typing import List

from ..dataconfig import DataConfig, data_config
from ..suspected_infection import suspected_infection_config
from ..severitysepsis import severitysepsisconfig, SeveritySepsisConfig

#TODO: Configuration for spesis POA vs NPOA criteria
class POAvsNPOAConfig(BaseModel):
    period_constraints: dict[str, int] = Field(
        default_factory=lambda: {
            "Arrival_Instant": 48,
            # "FirstAdmissionOrderInstant": 0,
            "InpatientAdmissionInstant": 48,
        }
    )

    @property
    def time_columns(self) -> list[str]:
        return list(self.period_constraints.keys())


class TwoExprAnalysisConfig(DataConfig):
    encounter_level_info_cols: List[str] = Field(default_factory=lambda: [
            "EncounterEpicCsn",
            "Arrival_Instant",
            # "FirstAdmissionOrderInstant",
            "InpatientAdmissionInstant",
            'Death_Flag',
            "DischargeDepartment",
            "Admitted_from_ED",
            "InpatientAdmissionPatientClass",
            "AdmissionType",
            "AdmissionSource",
            "AdmissionOrigin",
            "PrincipalProblem",
            'Original_POA_Condition',
            'Sepsis_Category',
            'Cancer_Registry_YN',
            'HIV_Registry_YN',
            'Immunocrompromised_Registry_YN',
            'CKD_Dialysis_Registry_YN',
            'Solid_Organ_Transplant_Registry_YN',
            'Pregnancy_Registry_YN'
        ]
    )

    poa_config: POAvsNPOAConfig = POAvsNPOAConfig()
    severitysepsisconfig: SeveritySepsisConfig = severitysepsisconfig
    billing_sepsis_col: str = Field(default="Sepsis_Category",
                                    description="Column name for billing sepsis category")
    billing_values_order: List[str] = Field(default_factory=lambda:[
        "NPOA-1",
        "NPOA-2",
        "NPOA-3",
        "POA-1",
        "POA-2",    
        "POA-3",
        "UPOA-1",
        "UPOA-2",
        "UPOA-3"
    ])
    categorical_factors: List[str] = Field(default_factory=lambda: [
        "AdmissionOrigin",
        "AdmissionSource",
        "AdmissionType",
        "PrincipalProblem",
        "suspicion_infection_type"
    ])
    binary_factors: List[str] = Field(default_factory=lambda: [
        "Admitted_from_ED",
        # 'Cancer_Registry_YN',
        # 'HIV_Registry_YN',
        # 'Immunocrompromised_Registry_YN',
        # 'CKD_Dialysis_Registry_YN',
        # 'Solid_Organ_Transplant_Registry_YN',
        # 'Pregnancy_Registry_YN',
        "Death_Flag"
    ])

    cofounding_factors_cols: List[str] = Field(default_factory=lambda: [
        'Cancer_Registry_YN',
        'HIV_Registry_YN',
        'Immunocrompromised_Registry_YN',
        'CKD_Dialysis_Registry_YN',
        'Solid_Organ_Transplant_Registry_YN',
        'Pregnancy_Registry_YN'
    ])
    # principal_problem_col: str = Field(default="PrincipalProblem", description="Column name for principal problem")
    # death_flag_col: str = Field(default="Death_Flag", description="Column name for death flag")

two_experiment_analysis_config = TwoExprAnalysisConfig()