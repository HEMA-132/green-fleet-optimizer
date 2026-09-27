"""Spatial-temporal join utilities for vessel and marine-environment data."""

from __future__ import annotations

import math
from typing import Any

import pandas as pd


class VesselMarineJoiner:
    """Match vessel observations to nearest marine environment records.

    The join is intentionally conservative: it only emits a match when a vessel
    row and a marine row are both valid and fall within the configured spatial and
    temporal tolerances. This keeps the join honest and avoids fabricating missing
    route or environmental values.
    """

    def __init__(
        self,
        max_time_delta_seconds: float = 3600.0,
        max_distance_km: float = 50.0,
        vessel_time_column: str = "timestamp",
        vessel_latitude_column: str = "latitude",
        vessel_longitude_column: str = "longitude",
        marine_time_column: str = "timestamp",
        marine_latitude_column: str = "latitude",
        marine_longitude_column: str = "longitude",
    ) -> None:
        self.max_time_delta_seconds = float(max_time_delta_seconds)
        self.max_distance_km = float(max_distance_km)
        self.vessel_time_column = vessel_time_column
        self.vessel_latitude_column = vessel_latitude_column
        self.vessel_longitude_column = vessel_longitude_column
        self.marine_time_column = marine_time_column
        self.marine_latitude_column = marine_latitude_column
        self.marine_longitude_column = marine_longitude_column

    @staticmethod
    def _resolve_column(frame: pd.DataFrame, *candidate_names: str) -> str | None:
        lookup = {str(column).strip().lower(): column for column in frame.columns}
        for candidate in candidate_names:
            key = str(candidate).strip().lower()
            if key in lookup:
                return lookup[key]
        return None

    @staticmethod
    def _normalize_timestamp_series(series: pd.Series) -> pd.Series:
        if series.empty:
            return pd.Series(pd.NaT, index=series.index, dtype="datetime64[ns, UTC]")
        parsed = pd.to_datetime(series, errors="coerce", utc=True)
        return parsed

    @staticmethod
    def _validate_lat_lon(latitude: Any, longitude: Any) -> None:
        lat = float(latitude)
        lon = float(longitude)
        if not -90.0 <= lat <= 90.0:
            raise ValueError("latitude must be between -90 and 90 degrees.")
        if not -180.0 <= lon <= 180.0:
            raise ValueError("longitude must be between -180 and 180 degrees.")

    @staticmethod
    def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        radius_km = 6371.0
        phi1 = math.radians(float(lat1))
        phi2 = math.radians(float(lat2))
        delta_phi = math.radians(float(lat2) - float(lat1))
        delta_lambda = math.radians(float(lon2) - float(lon1))
        a = (
            math.sin(delta_phi / 2.0) ** 2
            + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
        )
        c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
        return radius_km * c

    def _marine_candidates(
        self,
        vessel_row: pd.Series,
        marine_frame: pd.DataFrame,
        vessel_ts: pd.Timestamp,
    ) -> pd.DataFrame:
        marine_time_col = self._resolve_column(marine_frame, self.marine_time_column)
        marine_lat_col = self._resolve_column(marine_frame, self.marine_latitude_column)
        marine_lon_col = self._resolve_column(marine_frame, self.marine_longitude_column)
        if marine_time_col is None or marine_lat_col is None or marine_lon_col is None:
            raise ValueError("Marine frame is missing required timestamp/latitude/longitude columns.")

        marine_subset = marine_frame.copy()
        marine_subset["_marine_timestamp_utc"] = self._normalize_timestamp_series(marine_subset[marine_time_col])

        valid_rows = marine_subset[marine_subset["_marine_timestamp_utc"].notna()].copy()
        if valid_rows.empty:
            return pd.DataFrame(columns=list(marine_subset.columns) + ["_time_delta_seconds", "_distance_km"])

        latitudes = pd.to_numeric(valid_rows[marine_lat_col], errors="coerce")
        longitudes = pd.to_numeric(valid_rows[marine_lon_col], errors="coerce")
        valid_rows = valid_rows.loc[latitudes.notna() & longitudes.notna()].copy()
        valid_rows["_distance_km"] = valid_rows.apply(
            lambda row: self._haversine_km(
                float(vessel_row[self.vessel_latitude_column]),
                float(vessel_row[self.vessel_longitude_column]),
                float(row[marine_lat_col]),
                float(row[marine_lon_col]),
            ),
            axis=1,
        )
        valid_rows["_time_delta_seconds"] = (
            (valid_rows["_marine_timestamp_utc"] - vessel_ts).dt.total_seconds().abs()
        )
        mask = (valid_rows["_time_delta_seconds"] <= self.max_time_delta_seconds) & (
            valid_rows["_distance_km"] <= self.max_distance_km
        )
        return valid_rows.loc[mask].copy()

    def join(
        self,
        vessel_frame: pd.DataFrame,
        marine_frame: pd.DataFrame,
    ) -> pd.DataFrame:
        if vessel_frame.empty:
            return vessel_frame.copy()

        vessel_time_col = self._resolve_column(vessel_frame, self.vessel_time_column)
        vessel_lat_col = self._resolve_column(vessel_frame, self.vessel_latitude_column)
        vessel_lon_col = self._resolve_column(vessel_frame, self.vessel_longitude_column)
        if vessel_time_col is None or vessel_lat_col is None or vessel_lon_col is None:
            raise ValueError("Vessel frame is missing required timestamp/latitude/longitude columns.")

        result = vessel_frame.copy()
        result["match_status"] = "rejected"
        result["matched_marine_timestamp"] = pd.NA
        result["matched_marine_latitude"] = pd.NA
        result["matched_marine_longitude"] = pd.NA
        result["time_difference_seconds"] = pd.NA
        result["spatial_distance_km"] = pd.NA
        result["duplicate_match_count"] = 0
        result["provenance"] = "join:unmatched"

        for idx, row in vessel_frame.iterrows():
            timestamp_value = row.get(vessel_time_col)
            latitude_value = row.get(vessel_lat_col)
            longitude_value = row.get(vessel_lon_col)

            try:
                vessel_ts = pd.to_datetime(timestamp_value, errors="raise", utc=True)
                self._validate_lat_lon(latitude_value, longitude_value)
            except (TypeError, ValueError):
                continue

            if pd.isna(vessel_ts):
                continue

            candidate_matches = self._marine_candidates(row, marine_frame, vessel_ts)
            if candidate_matches.empty:
                continue

            best_match = candidate_matches.sort_values(
                ["_time_delta_seconds", "_distance_km"],
                ascending=[True, True],
            ).iloc[0]

            result.at[idx, "match_status"] = "matched"
            result.at[idx, "matched_marine_timestamp"] = pd.Timestamp(best_match["_marine_timestamp_utc"]).isoformat()
            result.at[idx, "matched_marine_latitude"] = float(best_match[self._resolve_column(marine_frame, self.marine_latitude_column)])
            result.at[idx, "matched_marine_longitude"] = float(best_match[self._resolve_column(marine_frame, self.marine_longitude_column)])
            result.at[idx, "time_difference_seconds"] = int(abs(float(best_match["_time_delta_seconds"])))
            result.at[idx, "spatial_distance_km"] = float(best_match["_distance_km"])
            result.at[idx, "duplicate_match_count"] = int(len(candidate_matches))
            result.at[idx, "provenance"] = "join:nearest-neighbor:spatial-temporal"

        return result

    @staticmethod
    def _normalize_timestamp(value: Any) -> pd.Timestamp | pd.NaT:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return pd.NaT
        try:
            parsed = pd.to_datetime(value, errors="raise", utc=True)
        except (TypeError, ValueError):
            return pd.NaT
        if pd.isna(parsed):
            return pd.NaT
        return parsed
