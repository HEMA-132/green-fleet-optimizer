"""Loading utilities for raw fuel datasets."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import pandas as pd

from .validation import detect_duplicate_rows, detect_invalid_records, detect_missing_values, detect_possible_outliers

logger = logging.getLogger(__name__)


class FuelDataLoader:
    """Loads and validates the raw GreenFleet fuel CSV data."""

    def __init__(self, csv_path: str | Path):
        self.csv_path = Path(csv_path)

    def load_raw_csv(self) -> pd.DataFrame:
        if not self.csv_path.exists():
            raise FileNotFoundError(f"Dataset not found at {self.csv_path}")

        logger.info("Loading raw CSV from %s", self.csv_path)
        df = pd.read_csv(self.csv_path)
        return df

    @staticmethod
    def normalize_column_name(column_name: str) -> str:
        normalized = str(column_name).strip().lower()
        normalized = normalized.replace(" ", "_")
        normalized = normalized.replace("-", "_")
        normalized = re.sub(r"[^a-z0-9_]+", "_", normalized)
        normalized = re.sub(r"_+", "_", normalized)
        return normalized.strip("_")

    def normalize_columns(self, frame: pd.DataFrame) -> pd.DataFrame:
        renamed = frame.copy()
        renamed.columns = [self.normalize_column_name(col) for col in renamed.columns]
        return renamed

    def detect_missing_values(self, frame: pd.DataFrame) -> dict[str, Any]:
        return detect_missing_values(frame)

    def detect_duplicate_rows(self, frame: pd.DataFrame) -> int:
        return detect_duplicate_rows(frame)

    def detect_invalid_records(self, frame: pd.DataFrame) -> list[int]:
        return detect_invalid_records(frame)

    def detect_possible_outliers(self, frame: pd.DataFrame, numeric_columns: list[str] | None = None) -> list[int]:
        return detect_possible_outliers(frame, numeric_columns)

    @staticmethod
    def coerce_numeric_columns(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
        cleaned = frame.copy()
        for column in columns:
            if column in cleaned.columns:
                cleaned[column] = pd.to_numeric(cleaned[column], errors="coerce")
        return cleaned

    @staticmethod
    def standardize_string_columns(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
        cleaned = frame.copy()
        for column in columns:
            if column in cleaned.columns:
                cleaned[column] = cleaned[column].replace({"": pd.NA})
                cleaned[column] = cleaned[column].map(lambda value: str(value).strip() if pd.notna(value) else pd.NA)
        return cleaned

    @staticmethod
    def canonicalize_categorical_values(frame: pd.DataFrame) -> pd.DataFrame:
        cleaned = frame.copy()

        if "fuel_type" in cleaned.columns:
            cleaned["fuel_type"] = cleaned["fuel_type"].replace({
                "diesel": "Diesel",
                "hfo": "HFO",
                "diesel fuel": "Diesel",
                "heavy fuel oil": "HFO",
            })

        if "weather_conditions" in cleaned.columns:
            cleaned["weather_conditions"] = cleaned["weather_conditions"].replace({
                "calm": "Calm",
                "moderate": "Moderate",
                "stormy": "Stormy",
            })

        if "month" in cleaned.columns:
            cleaned["month"] = cleaned["month"].replace({
                "january": "January",
                "february": "February",
                "march": "March",
                "april": "April",
                "may": "May",
                "june": "June",
                "july": "July",
                "august": "August",
                "september": "September",
                "october": "October",
                "november": "November",
                "december": "December",
            })

        return cleaned
