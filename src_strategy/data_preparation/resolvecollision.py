import polars as pl
from collections import defaultdict
from typing import List

from ..configs.dataconfig import DataConfig, DataInputOutputConfig
from ..configs.collision import CollisionConfig, ResolutionStrategy
from ..utils.logger import get_logger


logger = get_logger(__name__)

class ResolveCollision:
    def __init__(self, collision_config: CollisionConfig, input_output_config: DataInputOutputConfig = None):
        self.collision_config = collision_config
        self.input_output_config = input_output_config
        self._set_groupers_to_resolve()

    def _set_groupers_to_resolve(self):
        self.groupers_to_resolve = sorted(list(self.collision_config.features_resolutions_dict.keys()))
    
    def _check_grouper_to_resolve_existence(self, collisions:pl.DataFrame):
        """
        For every grouper in self.groupers_to_resolve, make sure that it exists and count how many collisions occurred for
        that grouper, and maybe # of collisions per encounter, and rank encounters by # of collisions?
        """
        logger.info(f'Counting collisions ...')
        tab = collisions.sort(
            by='count', descending=True
        )
        logger.info(f'# of collisions: {collisions.shape[0]} ...')
        logger.info(f"Maximum # of collisions per encounter: {collisions['count'].max()} for {self.collision_config.grouper_col} {collisions[self.collision_config.grouper_col][0]} for encounter {collisions[self.collision_config.encounter_col][0]} to {collisions[self.collision_config.event_dt_col][0]}...")
        logger.info(f'There are {collisions.filter(pl.col("count") == pl.col("count").max()).shape[0]} encounters with maximum # of collisions...')
        logger.info(f'Collisions counts by {self.collision_config.grouper_col}: {collisions[self.collision_config.grouper_col].value_counts(sort=True)}')

        groupers_with_no_collisions = set(self.groupers_to_resolve)-set(collisions[self.collision_config.grouper_col].unique())
        if len(groupers_with_no_collisions) > 0:
            logger.info(f'Groupers with no collisions: {groupers_with_no_collisions}')

        if self.input_output_config is not None:
            tab.write_csv(self.input_output_config.meta_output_path +'/collisions.csv')
        return collisions

    def _save_extreme_diff(self, df: pl.DataFrame, collisions_resolved: pl.DataFrame, extreme_ratio:float=0.5):
        df_inner = df.join(
            collisions_resolved, on=[self.collision_config.encounter_col, self.collision_config.event_dt_col, self.collision_config.grouper_col, self.collision_config.type_col], how='inner'
        )
        df_map_extreme = df_inner.filter(
            ((pl.col("map")-pl.col("map_right")).abs()/pl.col("map")) > extreme_ratio
        ).sort(by=[self.collision_config.encounter_col, self.collision_config.event_dt_col])
        df_sys_extreme = df_inner.filter(
            ((pl.col("sys")-pl.col("sys_right")).abs()/pl.col("sys")) > extreme_ratio
        ).sort(by=[self.collision_config.encounter_col, self.collision_config.event_dt_col])
        if df_map_extreme.shape[0] > 0:
            logger.info(f"Mean Arterial blood pressure at extreme values ratio of {extreme_ratio}: {df_map_extreme} ")
            if self.input_output_config is not None:
                logger.info(f"Saving Mean Arterial blood pressure extreme values to {self.input_output_config.meta_output_path}/map_extreme.csv")
                df_map_extreme.write_csv(self.input_output_config.meta_output_path +'/map_extreme.csv')
        else:
            logger.info(f"No Mean Arterial blood pressure extreme values found")

        if df_sys_extreme.shape[0] > 0:
            logger.info(f"Systolic blood pressure at extreme values ratio of {extreme_ratio}: {df_sys_extreme} ")
            if self.input_output_config is not None:
                logger.info(f"Saving Systolic blood pressure extreme values to {self.input_output_config.meta_output_path}/map_extreme.csv")
                df_sys_extreme.write_csv(self.input_output_config.meta_output_path +'/sys_extreme.csv')
        else:
            logger.info(f"No Systolic blood pressure extreme values found")


    def resolve_bp_collisions(self, df: pl.DataFrame, collisions: pl.DataFrame) -> pl.DataFrame:
        df_with_collisions = df.join(
            collisions.filter(
                pl.col(self.collision_config.grouper_col) == 'Blood Pressure'
            ), on=[self.collision_config.encounter_col, self.collision_config.event_dt_col, self.collision_config.grouper_col], how='inner'
        )
        resolved_list = []
        for key, feat_dict in self.collision_config.features_resolutions_dict.items():
            if key != 'map' and key != 'sys':
                continue
            expr = pl.col(feat_dict.val_col)
            picked = self._set_strategy_expression(expr, key)
            resolved = df_with_collisions.group_by(
                self.collision_config.encounter_col,
                self.collision_config.event_dt_col
            ).agg(
                picked.alias(feat_dict.val_col)
            )
            resolved_list.append(resolved)

        assert len(resolved_list) == 2, 'Expected 2 resolved dataframes (map and sys)'
        assert len( set(resolved_list[0][self.collision_config.encounter_col].unique()).intersection(set(resolved_list[1][self.collision_config.encounter_col].unique())) ) == resolved_list[0][self.collision_config.encounter_col].n_unique(), f'{self.collision_config.encounter_col} should be the same in both dataframes'
        assert len( set(resolved_list[0][self.collision_config.event_dt_col].unique()).intersection(set(resolved_list[1][self.collision_config.event_dt_col].unique())) ) == resolved_list[0][self.collision_config.event_dt_col].n_unique(), f'{self.collision_config.event_dt_col} should be the same in both dataframes'
        df_bp_no_collisions = resolved_list[0].join(resolved_list[1], on=[self.collision_config.encounter_col, self.collision_config.event_dt_col], how='inner').with_columns(
            pl.lit("Blood Pressure").alias(self.collision_config.grouper_col),
            pl.lit("Flowsheet").alias(self.collision_config.type_col)
        )
        self._save_extreme_diff(df, df_bp_no_collisions, extreme_ratio=0.5)
        return df_bp_no_collisions


    def _set_strategy_expression(self, expr: pl.Expr, grouper:str):
        if self.collision_config.features_resolutions_dict[grouper].strategy == ResolutionStrategy.MAX:
            picked = expr.max()
        elif self.collision_config.features_resolutions_dict[grouper].strategy == ResolutionStrategy.MIN:
            picked = expr.min()
        elif self.collision_config.features_resolutions_dict[grouper].strategy == ResolutionStrategy.WORST:
            severity = pl.max_horizontal(expr-self.collision_config.features_resolutions_dict[grouper].upper_bound,
                                            self.collision_config.features_resolutions_dict[grouper].lower_bound-expr)
            picked = expr.sort_by(severity).last()
        else:
            raise NotImplemented(f'Unknown strategy {self.collision_config.features_resolutions_dict[grouper].strategy}')
        return picked


    def detect_collisions(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Detect all instants with collision per group in self.grouper_to_resolve
        """
        d = defaultdict(list)
        for _, featdict in self.collision_config.features_resolutions_dict.items():
            d[self.collision_config.grouper_col].append(featdict.grouper_col_val)
            d[self.collision_config.type_col].append(featdict.type_col_val)
            # d["key"].append(_)

        # df_unified_bp = df.with_columns(
        #     pl.when(
        #         pl.col(self.collision_config.grouper_col) == "Arterial Blood Pressure Mean"
        #     ).then(pl.lit("Blood Pressure")).otherwise(pl.col(self.collision_config.grouper_col)).alias(self.collision_config.grouper_col)
        # )

        collisions =  df.join(
                    pl.DataFrame( d ).explode(pl.col(self.collision_config.grouper_col)).unique()
                    ,on=[self.collision_config.grouper_col, self.collision_config.type_col], how='inner'
                ).group_by(
                    self.collision_config.encounter_col, 
                    self.collision_config.event_dt_col, 
                    self.collision_config.grouper_col,
                    self.collision_config.type_col
                ).agg(
                    pl.len().alias('count')
                ).filter(
                    pl.col('count') > 1
                )
        self.groupers_to_resolve_ = collisions[self.collision_config.grouper_col].unique().to_list()
        return collisions

    def _resolve(self, df: pl.DataFrame, collision: pl.DataFrame) -> pl.DataFrame:
        if not hasattr(self, 'groupers_to_resolve_'):
            raise Exception('self.groupers_to_resolve_ is not set. Please call detect_collisions() method first.')
        core_df = df.join(
            collision,
            on=[self.collision_config.encounter_col, self.collision_config.event_dt_col, self.collision_config.grouper_col],
            how='inner'
        )
        resolved_list = []
        for grouper in self.groupers_to_resolve_:
            if grouper == 'Blood Pressure' or grouper == 'Arterial Blood Pressure Mean' or grouper == 'sys' or grouper =='map':
                continue
            expr = pl.col(self.collision_config.features_resolutions_dict[grouper].val_col)
            sub = core_df.filter( (pl.col(self.collision_config.grouper_col) == grouper) & expr.is_not_null())

            if self.collision_config.features_resolutions_dict[grouper].strategy == ResolutionStrategy.MAX:
                picked = expr.max()
            elif self.collision_config.features_resolutions_dict[grouper].strategy == ResolutionStrategy.MIN:
                picked = expr.min()
            elif self.collision_config.features_resolutions_dict[grouper].strategy == ResolutionStrategy.WORST:
                severity = pl.max_horizontal(expr-self.collision_config.features_resolutions_dict[grouper].upper_bound,
                                             self.collision_config.features_resolutions_dict[grouper].lower_bound-expr)
                picked = expr.sort_by(severity).last()
            else:
                raise NotImplemented(f'Unknown strategy {self.collision_config.features_resolutions_dict[grouper].strategy}')

            resolved_list.append(
                sub.group_by(
                    self.collision_config.encounter_col,
                    self.collision_config.event_dt_col
                ).agg(
                    value=picked
                ).with_columns(
                    pl.lit(self.collision_config.features_resolutions_dict[grouper].grouper_col_val).alias(self.collision_config.grouper_col),
                    pl.lit(self.collision_config.features_resolutions_dict[grouper].type_col_val).alias(self.collision_config.type_col),
                )
            )
        return pl.concat(resolved_list, how='vertical').explode(self.collision_config.grouper_col)
        

    def _analyze_bp(self, df: pl.DataFrame, resolved_collisions_bp: pl.DataFrame = None):

        df_with_collision_resolved = df.join(
            resolved_collisions_bp,
            on=[self.collision_config.encounter_col, self.collision_config.event_dt_col, self.collision_config.grouper_col],
            how='inner'
        )
        resolved_dict = {} 
        for val_col in ['sys', 'map']:
            # Analyze for all groupers except Blood Pressure
            resolved_with_missed = df_with_collision_resolved.filter(
                pl.col(val_col) != pl.col(val_col+'_right')
            ).select(
                self.collision_config.encounter_col,
                self.collision_config.event_dt_col,
                self.collision_config.grouper_col,
                val_col,
                val_col+'_right'
            )

            resolved_dict[val_col] = resolved_with_missed.group_by(
                self.collision_config.grouper_col 
            ).agg(
                (pl.col(val_col) < pl.col( val_col+'_right')).sum().alias('resoled_to_max'),
                (pl.col(val_col) > pl.col( val_col+'_right')).sum().alias('resoled_to_min'),
                (pl.col(val_col) == pl.col(val_col+'_right')).sum().alias('resoled_to_same(error)')
            )

        return resolved_dict 



    def _analyze(self, df: pl.DataFrame, resolved_collisions: pl.DataFrame = None):

        df_with_collision_resolved = df.join(
            resolved_collisions.rename({"value": self.collision_config.val_col}),
            on=[self.collision_config.encounter_col, self.collision_config.event_dt_col, self.collision_config.grouper_col],
            how='left'
        )
        # Analyze for all groupers except Blood Pressure
        resolved_with_missed = df_with_collision_resolved.filter(
            pl.col(self.collision_config.val_col) != pl.col(self.collision_config.val_col+'_right')
        ).select(
            self.collision_config.encounter_col,
            self.collision_config.event_dt_col,
            self.collision_config.grouper_col,
            self.collision_config.val_col,
            self.collision_config.val_col+'_right'
        )

        resolved_with_missed = resolved_with_missed.group_by(
            self.collision_config.grouper_col 
        ).agg(
            (pl.col(self.collision_config.val_col) < pl.col(self.collision_config.val_col+'_right')).sum().alias('resoled_to_max'),
            (pl.col(self.collision_config.val_col) > pl.col(self.collision_config.val_col+'_right')).sum().alias('resoled_to_min'),
            (pl.col(self.collision_config.val_col) == pl.col(self.collision_config.val_col+'_right')).sum().alias('resoled_to_same(error)')
        )

        return resolved_with_missed

    def _monitor_output_validation(self, resolved_collisions_all: pl.DataFrame):
        # Monitoring
        dups = resolved_collisions_all.group_by(
            self.collision_config.encounter_col,
            self.collision_config.event_dt_col,
            self.collision_config.grouper_col
        ).agg(pl.len()).filter(pl.col("len")>1)
        dups_all = resolved_collisions_all.join(dups, on=[self.collision_config.encounter_col, self.collision_config.event_dt_col, self.collision_config.grouper_col], how='inner')
        dups_all.filter(pl.col("NumericValue").is_not_null())
        if self.input_output_config is not None:
            dups_all.write_csv(self.input_output_config.meta_output_path + '/allowed_duplicate.csv')
        logger.info(f'Duplicates with numerical value in resolved_collisions_all: {dups_all.select("Type", "Event_Grouper").unique()}. NOTE: Lactate is allowed to exist since it can be duplicated with Lactate (Type=Procedure)')

    def _remove_collisions_rows_on(self, df: pl.DataFrame, collision_frames: List[pl.DataFrame], on: List[str]):
        df_no_collisions = None
        for frame in collision_frames:
            if df_no_collisions is None:
                df_no_collisions = df.join(frame, on=on, how='anti')
            else:
                df_no_collisions = df_no_collisions.join(frame, on=on, how='anti')
        return df_no_collisions


    def resolve(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        NOTE: This method does not work for Blood Pressure. The main assumption is that all of the values are stored in self.collision_config.val_col, however the Blood Pressure values are stored in sys, and map 
                - For now, it is okay since we do not have any Blood Pressure collisions. However, this needs to be handeled appropriately in the future
        """
        logger.info(f'Resolving collisions in groupers: {self.groupers_to_resolve}...')
        collisions = self.detect_collisions(df)
        if len(collisions) == 0:
            logger.info(f'No collisions found.')
            return df
        collisions = self._check_grouper_to_resolve_existence(collisions)
        resolved_collisions_bp = self.resolve_bp_collisions(df, collisions)
        resolved_collisions = self._resolve(df, collisions)

        # Log stats about the resolved collisions versus the original
        resolved_stats = self._analyze(df, resolved_collisions)
        resolved_bp_stats_dict = self._analyze_bp(df, resolved_collisions_bp)
        logger.info(f'Resolved collisions stats: {resolved_stats}')
        logger.info(f'Resolved Systolic blood pressure collisions stats: {resolved_bp_stats_dict["sys"]}')
        logger.info(f'Resolved Mean Arterial blood pressure collisions stats: {resolved_bp_stats_dict["map"]}')

        resolved_collisions = resolved_collisions.rename({'value': self.collision_config.val_col})

        df_no_collisions = self._remove_collisions_rows_on(df,
                                                           [resolved_collisions, resolved_collisions_bp],
                                                           [self.collision_config.encounter_col, self.collision_config.event_dt_col, self.collision_config.grouper_col, self.collision_config.type_col])


        assert (df.shape[0]-collisions['count'].sum()) == df_no_collisions.shape[0], f'Expected {df.shape[0]-collisions["count"].sum()} rows for df_no_collisions, but got {df_no_collisions.shape[0]}'

        df_resolved_subset_numval = resolved_collisions.join(
            df,
            on=resolved_collisions.columns,
            how='inner'
        ).unique(subset=[self.collision_config.encounter_col, self.collision_config.event_dt_col, self.collision_config.grouper_col, self.collision_config.val_col, self.collision_config.type_col])

        df_resolved_subset_bp = resolved_collisions_bp.join(
            df,
            on=resolved_collisions_bp.columns,
            how='inner'
        ).unique(subset=[self.collision_config.encounter_col, self.collision_config.event_dt_col, self.collision_config.grouper_col, self.collision_config.val_col, self.collision_config.type_col])

        assert df_no_collisions.shape[1] == df_resolved_subset_bp.shape[1] == df_resolved_subset_numval.shape[1], 'Expected df_no_collisions and df_resolved_subset_numval and df_resolved_subset_bp to have the same number of columns'

        resolved_collisions_all = pl.concat([df_no_collisions, df_resolved_subset_numval.select(df_no_collisions.columns), df_resolved_subset_bp.select(df_no_collisions.columns)], how='vertical') 

        self._monitor_output_validation(resolved_collisions_all)        

        return resolved_collisions_all 