from pydantic import BaseModel, Field
from .dataconfig import DataConfig, data_config 
from typing import Optional

class AntibioticBloodCultureConfig(DataConfig):
    antibiotic_type_name: str = Field(default="IV Antibiotics",
                                       description="Type name for antibiotic")

    antibiotic_excluded_type_names: Optional[str] = Field(default='Perioperative Antibiotics', description="Excluded type names for antibiotic")

    blood_culture_grouper_val: str = Field(default="Blood Culture Order",
                                            description="Grouper value for blood culture")

    antibiotic_datetime_col: str = Field(default="iv_dt", description="Column name for antibiotic event datetime")
    blood_culture_datetime_col: str = Field(default="culture_dt", description="Column name for blood culture event datetime")
    antibiotic_evname_col: str = Field(default="iv_name", description="Column name for antibiotic event name")
    blood_culture_evname_col: str = Field(default="culture_name", description="Column name for blood culture event name")

    first_time_ev_col: str = Field(default="first_ev_time_iv_culture", description="Column name for first event datetime between antibiotic and blood culture")

    forward_tolerance: str = Field(default="24h", description="Forward tolerance for antibiotic and blood culture events")
    backward_tolerance: str = Field(default="72h", description="Backward tolerance for antibiotic and blood culture events")

    flag_val: str = Field(default="antibiotic_culture", description="Value to flag suspected infection based on antibiotic and blood culture events")
    flag_col: str = Field(default="ev_type_iv_culture", description="Column name to flag suspected infection based on antibiotic and blood culture events")

class LactateBloodCultureConfig(DataConfig):
    lactate_grouper_val: str = Field(default="Lactate", description="Grouper value for lactate")
    blood_culture_grouper_val: str = Field(default="Blood Culture Order", description="Grouper value for blood culture")

    lactate_datetime_col: str = Field(default="lactate_dt", description="Column name for lactate event datetime")
    blood_culture_datetime_col: str = Field(default="culture_dt", description="Column name for blood culture event datetime")
    blood_culture_evname_col: str = Field(default="culture_name", description="Column name for blood culture event name")

    first_time_ev_col: str = Field(default="first_ev_time_lactcult", description="Column name for first event datetime between lactate and blood culture")

    tolerance: str = Field(default="6 hours", description="Tolerance for lactate and blood culture events")

    flag_val: str = Field(default="lactate_culture", description="Value to flag suspected infection based on lactate and blood culture events")
    flag_col: str = Field(default="ev_type_lactate_culture", description="Column name to flag suspected infection based on lactate and blood culture events")

class CodeSepsisConfig(DataConfig):
    diagnosis_grouper_val: str = Field(default="Code Sepsis Page", description="Grouper value for sepsis diagnosis codes")
    diagnosis_time_col: str = Field(default="first_ev_time_codesepsis", description="Column name for sepsis diagnosis code event datetime")
    flag_val: str = Field(default="sepsis_diagnosis_code", description="Value to flag suspected infection based on sepsis diagnosis codes")
    flag_col: str = Field(default="ev_type_sepsis_diag_code", description="Column name to flag suspected infection based on sepsis diagnosis codes")

class SuspectedInfectionFlowsheetConfig(DataConfig):
    flowsheet_grouper_val: str = Field(default="Suspected Infection", description="Grouper value for suspected infection flowsheet events")
    raw_val_col_value: str = Field(default="Yes", description="Raw value in the flowsheet events to flag suspected infection")

    flowsheet_time_col: str = Field(default="first_ev_time_flowsheet", description="Column name for suspected infection flowsheet event datetime")

    flag_val: str = Field(default="suspected_infection_flowsheet", description="Value to flag suspected infection based on flowsheet events")
    flag_col: str = Field(default="ev_type_suspected_infection_flowsheet", description="Column name to flag suspected infection based on flowsheet events")

class SuspectedInfectionConfig(DataConfig):
    antibiotic_blood_culture_config: AntibioticBloodCultureConfig = AntibioticBloodCultureConfig()
    lactate_culture_config: LactateBloodCultureConfig = LactateBloodCultureConfig()
    code_sepsis_config: CodeSepsisConfig = CodeSepsisConfig()
    suspected_infection_flowsheet_config: SuspectedInfectionFlowsheetConfig = SuspectedInfectionFlowsheetConfig()

    lactate_culture_suffix: str = Field(default="_lactcult", description="Suffix used for Lactate and Blood culture infection detection criteria when joined with other criteria")
    diagnosis_codesepsis_suffix: str = Field(default="_codesepsis", description="Suffix used for Diagnosis Code Sepsis detection criteria when joined with other criteria")
    flowsheet_infection_suffix: str = Field(default="_suspectedinfection", description="Suffix used for Flowsheet Infection detection criteria when joined with other criteria")

    earliest_infection_time_col: str = Field(default="infection_time", description="Column name for earliest infection time detected among all criteria")
    earliest_infection_type_col: str = Field(default="first_ev_type", description="Column name for infection event type indicating which criteria were the earliest for suspected infection detection")
    infection_type_col: str = Field(default="infection_ev_type", description="Column name for infection event type indicating which criteria were met for suspected infection detection")

    variable_name_col: str = Field(default="criterion", description="Column name for infection event type indicating which criteria were met for suspected infection detection")
    value_name_dt_col :str = Field(default="infect_dt", description="Column name for infection event datetime")
    value_type_col: str = Field(default="suspicion_infection_type", description="Column name for infection event type indicating which criteria were met for suspected infection detection")

    antibiotic_culture_longval: str = Field(default="IV+Culture", description="Long value for antibiotic and blood culture infection detection criteria")
    lactate_culture_longval: str = Field(default="LACTATE+CULTURE", description="Long value for lactate and blood culture infection detection criteria")
    codesepsis_longval: str = Field(default="CODE_SEPSIS_ORDER", description="Long value for sepsis diagnosis code infection detection criteria")
    flowsheet_longval: str = Field(default="FLOWSHEET_SUSPECTED_INFECTION", description="Long value for suspected infection flowsheet infection detection criteria")

    @property
    def dt_columns(self):
        return [
            self.antibiotic_blood_culture_config.antibiotic_datetime_col,
            self.antibiotic_blood_culture_config.blood_culture_datetime_col,
            self.lactate_culture_config.lactate_datetime_col,

            self.lactate_culture_config.blood_culture_datetime_col+self.lactate_culture_suffix,

            self.code_sepsis_config.diagnosis_time_col,

            self.suspected_infection_flowsheet_config.flowsheet_time_col,
        ]
    



# suspected_infection_config = SuspectedInfectionConfig()
suspected_infection_config = SuspectedInfectionConfig(
    antibiotic_blood_culture_config = AntibioticBloodCultureConfig(
        antibiotic_type_name = "IV Antibiotics - First",
    )
)