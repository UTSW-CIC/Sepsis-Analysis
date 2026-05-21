from .dataconfig import DataConfig
from typing import List

class SIRSConfig(DataConfig):
    # Grouper values for each SIRS criterion
    temp_grouper_val: str = "Temperature"
    hr_grouper_val: str = "Pulse"
    resp_grouper_val: str = "Respirations"
    wbc_grouper_val: str = "WBC"
    
    # Flag column names
    temp_flag_col: str = "Temp_Abnormal_Flag"
    hr_flag_col: str = "HR_High_Flag"
    resp_flag_col: str = "Resp_Rate_High_Flag"
    wbc_flag_col: str = "WBC_Abnormal_Flag"
    
    # Thresholds for abnormal flags
    temp_lower_threshold: float=96.8
    temp_upper_threshold: float=100.4
    hr_upper_threshold: float=90
    resp_upper_threshold: float=20
    wbc_lower_threshold: float=4
    wbc_upper_threshold: float=12

    # Outputcol
    sirs_score_col: str = "sirs_score"
    
    @property
    def selected_cols(self) -> List[str]:
        return [self.encounter_col, self.event_dt_col, self.event_name_col, self.val_col]

    @property
    def flag_cols(self) -> List[str]:
        return [self.temp_flag_col, self.hr_flag_col, self.resp_flag_col, self.wbc_flag_col]
    


sirs_config = SIRSConfig()