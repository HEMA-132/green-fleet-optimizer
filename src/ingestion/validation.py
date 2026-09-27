"""Validation functions for the GreenFleet fuel ingestion pipeline."""

from __future__ import annotations

import re
from typing import Any

import pandas as pd


REQUIRED_COLUMNS = {
    "ship_id",
    "ship_type",
    "route_id",
    "month",
    "distance",
    "fuel_type",
    "fuel_consumption",
    "co2_emissions",
    "weather_conditions",
    "engine_efficiency",
}


def _normalize_column_name(column_name: str) -> str:
    normalized = str(column_name).strip().lower()
    normalized = normalized.replace(" ", "_")
    normalized = normalized.replace("-", "_")
    normalized = re.sub(r"[^a-z0-9_]+", "_", normalized)
    normalized = re.sub(r"_+", "_", normalized)
    return normalized.strip("_")


def _canonicalize_frame_columns(frame: pd.DataFrame) -> pd.DataFrame:
    normalized = frame.copy()
    normalized.columns = [_normalize_column_name(column) for column in normalized.columns]
    return normalized

VALID_FUEL_TYPES = {"Diesel", "HFO"}
VALID_WEATHER_CONDITIONS = {"Calm", "Moderate", "Stormy"}
VALID_SHIP_TYPES = {"Fishing Trawler", "Oil Service Boat", "Surfer Boat", "Tanker Ship"}


def validate_required_columns(frame: pd.DataFrame) -> list[str]:
    normalized = _canonicalize_frame_columns(frame)
    missing = [column for column in REQUIRED_COLUMNS if column not in normalized.columns]
    return missing


def detect_missing_values(frame: pd.DataFrame) -> dict[str, Any]:
    normalized = _canonicalize_frame_columns(frame)
    missing_by_column = normalized.isna().sum().to_dict()
    total_missing = int(normalized.isna().sum().sum())
    return {
        "missing_by_column": missing_by_column,
        "total_missing": total_missing,
        "missing_percent": float((total_missing / max(len(normalized) * len(normalized.columns), 1)) * 100.0),
    }


def detect_duplicate_rows(frame: pd.DataFrame) -> int:
    normalized = _canonicalize_frame_columns(frame)
    return int(normalized.duplicated().sum())


def detect_invalid_records(frame: pd.DataFrame) -> list[int]:
    normalized = _canonicalize_frame_columns(frame)
    invalid_indexes: list[int] = []

    for index, row in normalized.iterrows():
        ship_id = str(row.get("ship_id", "")).strip()
        if not ship_id:
            invalid_indexes.append(int(index))
            continue

        if pd.notna(row.get("distance")) and float(row["distance"]) < 0:
            invalid_indexes.append(int(index))
            continue
        if pd.notna(row.get("fuel_consumption")) and float(row["fuel_consumption"]) < 0:
            invalid_indexes.append(int(index))
            continue
        if pd.notna(row.get("co2_emissions")) and float(row["co2_emissions"]) < 0:
            invalid_indexes.append(int(index))
            continue
        if pd.notna(row.get("engine_efficiency")):
            eff = float(row["engine_efficiency"])
            if eff < 0 or eff > 100:
                invalid_indexes.append(int(index))
                continue

        fuel_type = str(row.get("fuel_type", "")).strip()
        if fuel_type and fuel_type not in VALID_FUEL_TYPES:
            invalid_indexes.append(int(index))
            continue

        weather = str(row.get("weather_conditions", "")).strip()
        if weather and weather not in VALID_WEATHER_CONDITIONS:
            invalid_indexes.append(int(index))
            continue

        ship_type = str(row.get("ship_type", "")).strip()
        if ship_type and ship_type not in VALID_SHIP_TYPES:
            invalid_indexes.append(int(index))
            continue

    return sorted(set(invalid_indexes))


def detect_possible_outliers(frame: pd.DataFrame, numeric_columns: list[str] | None = None) -> list[int]:
    normalized = _canonicalize_frame_columns(frame)
    columns = numeric_columns or ["distance", "fuel_consumption", "co2_emissions", "engine_efficiency"]
    flagged: list[int] = []

    for col in columns:
        if col not in normalized.columns:
            continue
        q1 = normalized[col].quantile(0.25)
        q3 = normalized[col].quantile(0.75)
        iqr = q3 - q1
        lower = q1 - 1.5 * iqr
        upper = q3 + 1.5 * iqr
        flagged.extend(normalized[(normalized[col] < lower) | (normalized[col] > upper)].index.tolist())

    return sorted(set(int(index) for index in flagged))
