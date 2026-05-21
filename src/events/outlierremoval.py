from dataclasses import dataclass, field
from typing import Dict, Tuple, Optional
import polars as pl
import numpy as np


@dataclass
class VitalBounds:
    """Absolute physiological bounds for a vital sign."""
    min_value: float
    max_value: float


@dataclass
class VitalConfig:
    """Configuration for outlier detection on a single vital."""
    bounds: VitalBounds
    time_window_hours: float = 8.0
    mad_threshold: float = 3.0
    min_readings: int = 5


@dataclass
class OutlierRemovalConfig:
    """Configuration for the outlier removal pipeline."""
    encounter_col: str = "EncounterEpicCsn"
    timestamp_col: str = "Timestamp"
    value_col: str = "Value"
    vital_name_col: str = "VitalName"  # column that identifies which vital this row is

    vitals: Dict[str, VitalConfig] = field(default_factory=lambda: {
        "Temperature": VitalConfig(bounds=VitalBounds(85, 110)),   # adjust F vs C
        "Pulse": VitalConfig(bounds=VitalBounds(20, 250)),
        "Respiration": VitalConfig(bounds=VitalBounds(4, 60)),
        "SBP": VitalConfig(bounds=VitalBounds(40, 300)),
    })


class VitalOutlierRemoval:
    def __init__(self, config: OutlierRemovalConfig):
        self.config = config

    def run(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Main entry point. Processes each vital type separately,
        returns the cleaned dataframe with outlier rows dropped.

        Args:
            df: transactional dataframe containing vital sign rows
                Must have columns: encounter_col, timestamp_col, value_col, vital_name_col

        Returns:
            df with outlier rows removed and a flag column indicating removal reason
        """
        results = []

        for vital_name, vital_config in self.config.vitals.items():

            # Filter to rows for this vital
            df_vital = df.filter(pl.col(self.config.vital_name_col) == vital_name)

            if df_vital.height == 0:
                continue

            # Stage 1: absolute bounds
            df_vital = self._apply_absolute_bounds(df_vital, vital_config)

            # Stage 2: temporal contextual outliers (per encounter)
            df_vital = self._apply_temporal_outlier_removal(df_vital, vital_config)

            results.append(df_vital)

        # Combine cleaned vitals back
        df_cleaned_vitals = pl.concat(results) if results else pl.DataFrame()

        # Get all non-vital rows (diagnosis, admin, etc.) — untouched
        all_vital_names = list(self.config.vitals.keys())
        df_non_vitals = df.filter(~pl.col(self.config.vital_name_col).is_in(all_vital_names))

        # Combine
        return pl.concat([df_non_vitals, df_cleaned_vitals]).sort(
            [self.config.encounter_col, self.config.timestamp_col]
        )

    def _apply_absolute_bounds(
        self, df: pl.DataFrame, config: VitalConfig
    ) -> pl.DataFrame:
        """
        Stage 1: Remove rows where the value falls outside
        absolute physiological bounds.
        """
        return df.filter(
            (pl.col(self.config.value_col) >= config.bounds.min_value)
            & (pl.col(self.config.value_col) <= config.bounds.max_value)
        )

    def _apply_temporal_outlier_removal(
        self, df: pl.DataFrame, config: VitalConfig
    ) -> pl.DataFrame:
        """
        Stage 2: For each encounter, detect readings that deviate
        from their local temporal context using MAD within a time window.

        If an encounter has fewer than min_readings after Stage 1,
        skip temporal detection and keep all remaining rows.
        """
        encounter_col = self.config.encounter_col
        timestamp_col = self.config.timestamp_col
        value_col = self.config.value_col

        # Process per encounter
        encounters = df[encounter_col].unique().to_list()
        keep_indices = []

        for enc in encounters:
            df_enc = df.filter(pl.col(encounter_col) == enc).sort(timestamp_col)

            # Insufficient data — keep all
            if df_enc.height < config.min_readings:
                keep_indices.extend(df_enc["_row_idx"].to_list())
                continue

            timestamps = df_enc[timestamp_col].to_numpy()
            values = df_enc[value_col].to_numpy()
            row_indices = df_enc["_row_idx"].to_numpy()

            for i in range(len(values)):
                current_time = timestamps[i]

                # Find all readings within ±time_window_hours
                window_hours = config.time_window_hours
                time_diffs_hours = np.abs(
                    (timestamps - current_time) / np.timedelta64(1, 'h')
                )
                in_window = time_diffs_hours <= window_hours

                # Exclude current point from window calculation
                in_window[i] = False
                window_values = values[in_window]

                # If fewer than 2 neighbors in window, can't compute MAD — keep
                if len(window_values) < 2:
                    keep_indices.append(row_indices[i])
                    continue

                # Compute MAD
                median = np.median(window_values)
                mad = np.median(np.abs(window_values - median))

                # MAD can be 0 if most values are identical
                # Use a small floor to avoid division by zero
                # 1.4826 converts MAD to standard deviation equivalent
                mad_scaled = max(mad * 1.4826, 0.01)

                deviation = abs(values[i] - median) / mad_scaled

                if deviation <= config.mad_threshold:
                    keep_indices.append(row_indices[i])
                # else: outlier, don't add to keep_indices

        return df.filter(pl.col("_row_idx").is_in(keep_indices))

    def fit_transform(self, df: pl.DataFrame) -> Tuple[pl.DataFrame, pl.DataFrame]:
        """
        Run outlier removal and also return a report of what was removed.

        Returns:
            (cleaned_df, removed_df)
        """
        # Add row index for tracking
        df = df.with_row_index("_row_idx")

        cleaned = self.run(df)

        # Find removed rows
        kept_indices = cleaned["_row_idx"].to_list()
        removed = df.filter(~pl.col("_row_idx").is_in(kept_indices))

        # Clean up index column
        cleaned = cleaned.drop("_row_idx")
        removed = removed.drop("_row_idx")

        return cleaned, removed

if __name__ == "__main__" :
    config = OutlierRemovalConfig(
        encounter_col="EncounterEpicCsn",
        timestamp_col="Taken_Instant",
        value_col="Value",
        vital_name_col="FlowsheetDisplayName",
        vitals={
            "TEMPERATURE": VitalConfig(bounds=VitalBounds(85, 110), mad_threshold=3.0),
            "PULSE": VitalConfig(bounds=VitalBounds(20, 250), mad_threshold=3.0),
            "RESPIRATIONS": VitalConfig(bounds=VitalBounds(4, 60), mad_threshold=3.0),
            "BLOOD PRESSURE": VitalConfig(bounds=VitalBounds(40, 300), mad_threshold=3.0),
        },
    )

    remover = VitalOutlierRemoval(config)
    df_cleaned, df_removed = remover.fit_transform(df_vitals)

    # Inspect what was removed
    print(f"Removed {df_removed.height} rows out of {df_vitals.height}")
    print(df_removed.group_by("FlowsheetDisplayName").len())