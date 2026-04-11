import polars as pl
import duckdb
from typing import List
from .cardiac import CardiovascularDysfunctionCalculator 
from .coagulation import CoagulationDysfunctionCalculator
from .hepatic import HepaticDysfunctionCalculator
from .pulmonary import PulmonaryDysfunctionCalculator
from .renal import RenalDysfunctionCalculator
from .neuro import NeurologicalDysfunctionCalculator
from src.config import OrganDysfunctionConfig
from src.utils.logger import get_logger

logger = get_logger(__name__)


class OrganDysfunctionCalculator:
    def __init__(self, df_agg: pl.DataFrame,
                 df_all: pl.DataFrame,
                 organdysfunction_config: OrganDysfunctionConfig
    ):
        self.df_agg = df_agg
        self.df_all  = df_all
        self.organdysfunction_config = organdysfunction_config

        logger.info("(IF needed) Joining baseline values to aggregated dataframe for organ dysfunction calculation.")
        self.df_agg_baselines = self._join_baselines_2_agg()
            

        # Sort data frame to avoid multiple sorting throughout the class
        # self.df_agg =self.df_agg.sort(by=[self.organdysfunction_config.encounter_col, self.organdysfunction_config.event_dt_col])
        self.df_agg_baselines = self.df_agg_baselines.sort(by=[self.organdysfunction_config.encounter_col, self.organdysfunction_config.event_dt_col])


    def _join_baselines_2_agg(self):
        # Check if the baseline columns are already in the aggregated dataframe, if yes, skip the join step
        if set(self.organdysfunction_config.baseline.columns).issubset(set(self.df_agg.columns)):
            return self.df_agg

        df_baselines = self.df_all.group_by(self.organdysfunction_config.encounter_col)\
            .agg([pl.col(c).last() for c in self.organdysfunction_config.baseline.columns])
        df_agg = self.df_agg
        df_agg_baselines = duckdb.sql(f"""
            SELECT df_agg.*, df_baselines.*
            FROM df_agg
            LEFT JOIN df_baselines
            ON df_agg.{self.organdysfunction_config.encounter_col} = df_baselines.{self.organdysfunction_config.encounter_col}
        """).pl()

        if f'{self.organdysfunction_config.encounter_col}_1' in df_agg_baselines.columns:
            df_agg_baselines = df_agg_baselines.drop([f'{self.organdysfunction_config.encounter_col}_1'])
        return df_agg_baselines

    
    def _cardiovascular_dysfunction_flag(self) -> pl.DataFrame:
        logger.info("Calculating cardiovascular dysfunction flag.")
        return CardiovascularDysfunctionCalculator(self.df_agg, self.organdysfunction_config.cardiovascular).calculate_cardiovascular_dysfunction_flag()

    def _coagulation_dysfunction_flag(self) -> pl.DataFrame:
        logger.info("Calculating coagulation dysfunction flag.")
        return CoagulationDysfunctionCalculator(self.df_agg_baselines, self.organdysfunction_config.coagulation).calculate_coagulation_dysfunction_flag()


    def _pulmonary_dysfunction_flag(self) -> pl.DataFrame:
        logger.info("Calculating pulmonary dysfunction flag.")
        # Fill vent status forward, and fill remaining nulls with "Vent off" status before calculating pulmonary dysfunction flag
        # self.df_agg = self.df_agg.with_columns(
        #             pl.col(self.organdysfunction_config.pulmonary.vent_col).fill_null(strategy="forward")
        #             .over(self.organdysfunction_config.encounter_col).fill_null(self.organdysfunction_config.pulmonary.vent_off_status)
        #         )
        return PulmonaryDysfunctionCalculator(self.df_agg, self.organdysfunction_config.pulmonary).calculate_pulmonary_dysfunction_flag()


    
    def _renal_dysfunction_flag(self) -> pl.DataFrame:
        logger.info("Calculating renal dysfunction flag.")
        return RenalDysfunctionCalculator(self.df_agg_baselines, self.organdysfunction_config.renal).calculate_renal_dysfunction_flag()
        # return self.df_agg.with_columns(
        #     pl.when(
        #     # Highest creatinine in 24 hours > 2
        #     (
        #         (pl.col(self.organdysfunction_config.renal.creatinine_col.value) > self.organdysfunction_config.renal.creatinine_threshold))&
        #         (pl.col(self.organdysfunction_config.renal.baseline_creatinine_col.value).is_null()) 
        #     )|
        #     # Baseline creatinine * 2 < highest creatinine in 24 hours
        #     (2.0*pl.col(self.organdysfunction_config.renal.baseline_creatinine_col.value) < self.organdysfunction_config.renal.creatinine_col.value)|
        #     # TODO: Wait for Kelsea to send you the condition not depending on baseline eGFR value
        #     # Baseline eGFR / 2 > highest eGFR in 24 hours
        #     (0.5*pl.col(self.organdysfunction_config.renal.baseline_egfr_col.value) > self.organdysfunction_config.renal.egfr_col.value)
        # ).then(pl.lit(1)).otherwise(pl.lit(0)).alias(self.organdysfunction_config.renal.flag_col.value)

    def _hepatic_dysfunction_flag(self) -> pl.DataFrame:
        logger.info("Calculating hepatic dysfunction flag.")
        return HepaticDysfunctionCalculator(self.df_agg_baselines, self.organdysfunction_config.hepatic).calculate_hepatic_dysfunction_flag()

    def _neurological_dysfunction_flag(self) -> pl.DataFrame:
        logger.info("Calculating neurological dysfunction flag.")
        return NeurologicalDysfunctionCalculator(self.df_agg, self.organdysfunction_config.neurological).calculate_neurological_dysfunction_flag()

    # def _hypotensive_flag(self):
    #     df_sys = extract_systolic_bp(self.df_all)
    #     df_all = self.df_all
    #     df_joined = duckdb.sql("""
    #         SELECT *
    #         FROM df_all
    #         LEFT JOIN df_sys
    #         ON df_all.EncounterEpicCsn = df_sys.EncounterEpicCsn
    #         AND df_all.Event_DateTime = df_sys.Event_DateTime
    #         AND df_all.Event_Grouper = df_sys.Event_Grouper
    #     """).pl()

    #     df_joined.with_columns(
    #         pl.when(
    #             (
    #                 (pl.col("sys") < 90) | (pl.col("Baseline_Sys_Bp") < 90)
    #             ) & (pl.col("Event_Grouper") == "Blood Pressure")
    #         ).then(1).otherwise(0).alias("Hypotension_Flag")
    #     )
    #     return df_joined.sort(by=['EncounterEpicCsn', "Event_DateTime"]).with_columns(pl.col("sys").fill_null(strategy="forward").over("EncounterEpicCsn").fill_null(strategy="backward").over("EncounterEpicCsn"))
    
    def _join_tables(self, df_all: pl.DataFrame,
                     list_of_flag_dfs: List[pl.DataFrame],
                     on_cols: List[str] = ["EncounterEpicCsn", "Event_DateTime", "Event_Name"],
                     how: str = 'left'):
        df_comb = None
        for df_flag in list_of_flag_dfs:
            if df_comb is None:
                df_comb = df_flag
            else:
                df_comb = df_comb.join(
                df_flag,
                on=on_cols,
                how=how
            )
            right_cols = [col for col in df_comb.columns if col.endswith("_right")]
            if right_cols:
                df_comb = df_comb.drop(right_cols)

        return df_comb
    
    def _test_matching_flag_frames(self, list_of_flag_dfs):
        # Test for length of frames
        l = len(list_of_flag_dfs[0])
        for df in list_of_flag_dfs:
            assert len(df) == l, "Organdysfunction flags Frames are not the same length"
        
        # Test for matching indices
        df_index = list_of_flag_dfs[0].select(self.organdysfunction_config.encounter_col, self.organdysfunction_config.event_dt_col)
        for df in list_of_flag_dfs:
            assert df_index.equals(df.select(self.organdysfunction_config.encounter_col, self.organdysfunction_config.event_dt_col)), "Organdysfunction flags Frames are not the same length"
         
        logger.info("All flag frames are the same length and have the same indices.")
        
    def _concatenate_flag_dfs(self, list_of_flag_dfs: List[pl.DataFrame])-> pl.DataFrame:
        original_cols = set(list_of_flag_dfs[0].columns)        
        df = list_of_flag_dfs[0]
        for df_flag in list_of_flag_dfs[1:]:
            extra_cols = set(df_flag.columns)-original_cols
            df = pl.concat([df, df_flag.select(extra_cols)], how='horizontal')
        
        return df

    def calculate(self):
        df_pulmonary = self._pulmonary_dysfunction_flag()
        logger.info("----------------------------------------------------------------------------------")
        df_coagulation = self._coagulation_dysfunction_flag()
        logger.info("----------------------------------------------------------------------------------")
        df_cardiovascular = self._cardiovascular_dysfunction_flag()
        logger.info("----------------------------------------------------------------------------------")
        df_renal = self._renal_dysfunction_flag()
        logger.info("----------------------------------------------------------------------------------")
        df_hepatic = self._hepatic_dysfunction_flag()
        logger.info("----------------------------------------------------------------------------------")
        df_neuro = self._neurological_dysfunction_flag()
        logger.info("----------------------------------------------------------------------------------")

        logger.info("Joining organ dysfunction flag dataframes to create final organ dysfunction dataframe.")
        list_of_flag_dfs = [df_cardiovascular, df_coagulation, df_pulmonary, df_renal, df_hepatic, df_neuro]
        for i in range(len(list_of_flag_dfs)):
            list_of_flag_dfs[i] = list_of_flag_dfs[i].sort(by=[self.organdysfunction_config.encounter_col, self.organdysfunction_config.event_dt_col])
            
        self._test_matching_flag_frames(list_of_flag_dfs)

        self.df_organdysfunction = self._concatenate_flag_dfs(list_of_flag_dfs)
        

        # self.df_organdysfunction = self._join_tables(self.df_agg, list_of_flag_dfs, on_cols=[self.organdysfunction_config.encounter_col, self.organdysfunction_config.event_dt_col], how="left")

        logger.info("----------------------------------------------------------------------------------")
        logger.info("Calculating total organ dysfunction flag by summing individual organ dysfunction flags.")
        self.df_organdysfunction = self.df_organdysfunction.with_columns(
            pl.col(self.organdysfunction_config.cardiovascular.flag_col).fill_null(0),
            pl.col(self.organdysfunction_config.coagulation.flag_col).fill_null(0),
            pl.col(self.organdysfunction_config.pulmonary.flag_col).fill_null(0),
            pl.col(self.organdysfunction_config.renal.flag_col).fill_null(0),
            pl.col(self.organdysfunction_config.hepatic.flag_col).fill_null(0),
            pl.col(self.organdysfunction_config.neurological.flag_col).fill_null(0)
        ).with_columns(
           ( pl.col(self.organdysfunction_config.cardiovascular.flag_col)
            + pl.col(self.organdysfunction_config.coagulation.flag_col)
            + pl.col(self.organdysfunction_config.pulmonary.flag_col)
            + pl.col(self.organdysfunction_config.renal.flag_col)
            + pl.col(self.organdysfunction_config.hepatic.flag_col)
            + pl.col(self.organdysfunction_config.neurological.flag_col)).alias(self.organdysfunction_config.flag_col)
        )

        return self.df_organdysfunction

