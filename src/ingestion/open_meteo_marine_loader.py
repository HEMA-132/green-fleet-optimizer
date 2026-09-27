"""Open-Meteo Marine API client and preprocessing pipeline."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
import requests

logger = logging.getLogger(__name__)


class OpenMeteoMarineClient:
    """Thin client for the Open-Meteo Marine API."""

    DEFAULT_BASE_URL = "https://marine-api.open-meteo.com/v1/marine"
    DEFAULT_TIMEZONE = "auto"
    DEFAULT_VARIABLES = [
        "wave_height",
        "wave_direction",
        "wave_period",
        "wind_wave_height",
        "wind_wave_direction",
        "swell_wave_height",
        "swell_wave_direction",
        "ocean_current_velocity",
        "ocean_current_direction",
        "sea_surface_temperature",
    ]

    def __init__(
        self,
        base_url: str | None = None,
        timeout: int = 30,
        max_retries: int = 3,
        backoff_seconds: float = 1.0,
    ) -> None:
        self.base_url = (base_url or self.DEFAULT_BASE_URL).rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds

    @staticmethod
    def _validate_coordinates(latitude: float, longitude: float) -> None:
        if not -90.0 <= float(latitude) <= 90.0:
            raise ValueError("latitude must be between -90 and 90 degrees.")
        if not -180.0 <= float(longitude) <= 180.0:
            raise ValueError("longitude must be between -180 and 180 degrees.")

    @staticmethod
    def _normalize_variables(variables: Iterable[str] | None) -> list[str]:
        requested = list(variables or OpenMeteoMarineClient.DEFAULT_VARIABLES)
        normalized = []
        for item in requested:
            value = str(item).strip()
            if value:
                normalized.append(value)
        if not normalized:
            raise ValueError("At least one marine variable must be requested.")
        return normalized

    @staticmethod
    def _coerce_date(date_value: str) -> str:
        if isinstance(date_value, datetime):
            return date_value.date().isoformat()
        value = str(date_value).strip()
        if len(value) != 10 or value.count("-") != 2:
            raise ValueError("Dates must be provided in YYYY-MM-DD format.")
        return value

    def _request(self, params: dict[str, Any]) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                response = requests.Session().get(
                    self.base_url,
                    params=params,
                    timeout=self.timeout,
                    headers={"Accept": "application/json", "User-Agent": "green-fleet-optimizer/1.0"},
                )
                if response.status_code == 429:
                    raise RuntimeError("Open-Meteo API rate limit reached. Please retry later.")
                response.raise_for_status()
                payload = response.json()
                return payload
            except Exception as exc:  # pragma: no cover - defensive branch for real HTTP/network failures
                last_error = exc
                if attempt < self.max_retries:
                    logger.warning("Open-Meteo request failed on attempt %s/%s: %s", attempt, self.max_retries, exc)
                    continue
                raise RuntimeError(f"Open-Meteo API request failed after {self.max_retries} attempts: {exc}") from exc

        if last_error is not None:
            raise RuntimeError(f"Open-Meteo API request failed: {last_error}")
        raise RuntimeError("Open-Meteo API request failed.")

    def fetch_hourly_data(
        self,
        latitude: float,
        longitude: float,
        start_date: str,
        end_date: str,
        variables: list[str] | None = None,
        timezone: str = DEFAULT_TIMEZONE,
        **_: Any,
    ) -> dict[str, Any]:
        self._validate_coordinates(latitude, longitude)
        requested_variables = self._normalize_variables(variables)
        start = self._coerce_date(start_date)
        end = self._coerce_date(end_date)

        params: dict[str, Any] = {
            "latitude": float(latitude),
            "longitude": float(longitude),
            "start_date": start,
            "end_date": end,
            "hourly": ",".join(requested_variables),
            "timezone": timezone,
        }

        payload = self._request(params)
        if not isinstance(payload, dict):
            raise ValueError("Missing required marine response fields: response is not a JSON object.")
        hourly = payload.get("hourly")
        if not isinstance(hourly, dict):
            raise ValueError("Missing required marine response fields: hourly payload is missing.")
        if "time" not in hourly:
            raise ValueError("Missing required marine response fields: hourly.time is missing.")
        missing = [variable for variable in requested_variables if variable not in hourly]
        if missing:
            raise ValueError(f"Missing required hourly variables: {missing}")

        return payload

    def fetch_batch_hourly_data(
        self,
        coordinates: list[tuple[float, float]],
        start_date: str,
        end_date: str,
        variables: list[str] | None = None,
        timezone: str = DEFAULT_TIMEZONE,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for latitude, longitude in coordinates:
            results.append(
                self.fetch_hourly_data(
                    latitude=latitude,
                    longitude=longitude,
                    start_date=start_date,
                    end_date=end_date,
                    variables=variables,
                    timezone=timezone,
                )
            )
        return results


class OpenMeteoMarinePreprocessor:
    """Fetch, validate, normalize, and store marine-weather data."""

    def __init__(self, client: OpenMeteoMarineClient | None = None, output_dir: str | Path = "data/processed/marine"):
        self.client = client or OpenMeteoMarineClient()
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.raw_dir = Path("data/raw/marine")
        self.raw_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def schema_definition() -> dict[str, dict[str, str]]:
        return {
            "timestamp": {"type": "datetime", "unit": "ISO8601", "description": "Observation timestamp in local time."},
            "latitude": {"type": "float", "unit": "degrees", "description": "Latitude of the observation."},
            "longitude": {"type": "float", "unit": "degrees", "description": "Longitude of the observation."},
            "source": {"type": "string", "unit": "n/a", "description": "Source system name."},
            "wave_height_m": {"type": "float", "unit": "m", "description": "Wave height in metres."},
            "wave_direction_deg": {"type": "float", "unit": "deg", "description": "Mean wave direction in degrees from north."},
            "wave_period_s": {"type": "float", "unit": "s", "description": "Wave period in seconds."},
            "wind_wave_height_m": {"type": "float", "unit": "m", "description": "Wind wave height in metres."},
            "wind_wave_direction_deg": {"type": "float", "unit": "deg", "description": "Wind wave direction in degrees from north."},
            "swell_wave_height_m": {"type": "float", "unit": "m", "description": "Swell wave height in metres."},
            "swell_wave_direction_deg": {"type": "float", "unit": "deg", "description": "Swell wave direction in degrees from north."},
            "ocean_current_velocity_m_s": {"type": "float", "unit": "m/s", "description": "Ocean current velocity in metres per second."},
            "ocean_current_direction_deg": {"type": "float", "unit": "deg", "description": "Ocean current direction in degrees from north."},
            "sea_surface_temperature_c": {"type": "float", "unit": "°C", "description": "Sea surface temperature in Celsius."},
        }

    @staticmethod
    def unit_metadata() -> dict[str, str]:
        return {
            "wave_height": "m",
            "wave_direction": "deg",
            "wave_period": "s",
            "wind_wave_height": "m",
            "wind_wave_direction": "deg",
            "swell_wave_height": "m",
            "swell_wave_direction": "deg",
            "ocean_current_velocity": "m/s",
            "ocean_current_direction": "deg",
            "sea_surface_temperature": "°C",
        }

    @staticmethod
    def _record_unit_conversion(variable: str, from_unit: str, to_unit: str, row_count: int) -> dict[str, Any]:
        return {
            "variable": variable,
            "from_unit": from_unit,
            "to_unit": to_unit,
            "rows_converted": row_count,
            "applied": True,
        }

    @staticmethod
    def _canonicalize_value(variable: str, value: Any, source_unit: str | None) -> tuple[Any, str | None]:
        if value is None or value == "":
            return None, None

        if isinstance(value, str):
            value = float(value)

        if variable in {"wave_height", "wave_period", "wind_wave_height", "swell_wave_height"}:
            if source_unit in {"ft", "feet", "foot", "ft/s"}:
                converted = float(value) * 0.3048
                return converted, "m"
            return float(value), source_unit or "m"

        if variable == "ocean_current_velocity":
            if source_unit in {"km/h", "kmh"}:
                converted = float(value) / 3.6
                return converted, "m/s"
            if source_unit in {"kn", "knot", "knots"}:
                converted = float(value) * 0.514444
                return converted, "m/s"
            return float(value), source_unit or "m/s"

        if variable == "sea_surface_temperature":
            if source_unit in {"F", "°F", "fahrenheit"}:
                converted = (float(value) - 32.0) * 5.0 / 9.0
                return converted, "°C"
            return float(value), source_unit or "°C"

        return float(value), source_unit or "n/a"

    @staticmethod
    def _flag_invalid_values(df: pd.DataFrame) -> list[int]:
        invalid_indexes: list[int] = []
        for idx, row in df.iterrows():
            for column in [
                "wave_height_m",
                "wave_direction_deg",
                "wave_period_s",
                "wind_wave_height_m",
                "wind_wave_direction_deg",
                "swell_wave_height_m",
                "swell_wave_direction_deg",
                "ocean_current_velocity_m_s",
                "ocean_current_direction_deg",
                "sea_surface_temperature_c",
            ]:
                if column not in df.columns:
                    continue
                value = row.get(column)
                if pd.isna(value):
                    continue
                numeric = float(value)
                if column.endswith("_deg") and not 0.0 <= numeric <= 360.0:
                    invalid_indexes.append(int(idx))
                elif column.endswith("_m") and numeric < 0:
                    invalid_indexes.append(int(idx))
                elif column.endswith("_s") and numeric < 0:
                    invalid_indexes.append(int(idx))
                elif column.endswith("_c") and abs(numeric) > 100.0:
                    invalid_indexes.append(int(idx))
        return sorted(set(invalid_indexes))

    def _normalize_payload(self, payload: dict[str, Any], latitude: float, longitude: float) -> tuple[pd.DataFrame, dict[str, Any]]:
        if not isinstance(payload, dict) or not isinstance(payload.get("hourly"), dict):
            raise ValueError("Missing required marine response fields: hourly payload is missing.")

        hourly = payload["hourly"]
        time_values = hourly.get("time") or []
        if not isinstance(time_values, list) or not time_values:
            raise ValueError("Missing required marine response fields: hourly.time is missing.")

        source = payload.get("source", "Open-Meteo Marine API")
        units = payload.get("hourly_units", {})
        variable_names = [
            "wave_height",
            "wave_direction",
            "wave_period",
            "wind_wave_height",
            "wind_wave_direction",
            "swell_wave_height",
            "swell_wave_direction",
            "ocean_current_velocity",
            "ocean_current_direction",
            "sea_surface_temperature",
        ]
        rows: list[dict[str, Any]] = []
        unit_conversions: list[dict[str, Any]] = []

        for idx, timestamp in enumerate(time_values):
            row: dict[str, Any] = {
                "timestamp": timestamp,
                "latitude": float(latitude),
                "longitude": float(longitude),
                "source": source,
            }
            for variable in variable_names:
                if variable not in hourly:
                    continue
                original_value = hourly[variable][idx] if idx < len(hourly[variable]) else None
                source_unit = units.get(variable)
                canonical_value, canonical_unit = self._canonicalize_value(variable, original_value, source_unit)
                if canonical_unit and source_unit and canonical_unit != source_unit:
                    unit_conversions.append(
                        self._record_unit_conversion(variable, source_unit, canonical_unit, 1)
                    )
                row[f"{variable}_canonical"] = canonical_value
                if variable == "wave_height":
                    row["wave_height_m"] = canonical_value
                elif variable == "wave_direction":
                    row["wave_direction_deg"] = canonical_value
                elif variable == "wave_period":
                    row["wave_period_s"] = canonical_value
                elif variable == "wind_wave_height":
                    row["wind_wave_height_m"] = canonical_value
                elif variable == "wind_wave_direction":
                    row["wind_wave_direction_deg"] = canonical_value
                elif variable == "swell_wave_height":
                    row["swell_wave_height_m"] = canonical_value
                elif variable == "swell_wave_direction":
                    row["swell_wave_direction_deg"] = canonical_value
                elif variable == "ocean_current_velocity":
                    row["ocean_current_velocity_m_s"] = canonical_value
                elif variable == "ocean_current_direction":
                    row["ocean_current_direction_deg"] = canonical_value
                elif variable == "sea_surface_temperature":
                    row["sea_surface_temperature_c"] = canonical_value
            rows.append(row)

        df = pd.DataFrame(rows)
        if df.empty:
            df = pd.DataFrame(
                columns=[
                    "timestamp",
                    "latitude",
                    "longitude",
                    "source",
                    "wave_height_m",
                    "wave_direction_deg",
                    "wave_period_s",
                    "wind_wave_height_m",
                    "wind_wave_direction_deg",
                    "swell_wave_height_m",
                    "swell_wave_direction_deg",
                    "ocean_current_velocity_m_s",
                    "ocean_current_direction_deg",
                    "sea_surface_temperature_c",
                ]
            )

        duplicate_timestamps = int(df["timestamp"].duplicated().sum())
        null_value_count = int(df.isna().sum().sum())
        invalid_indexes = self._flag_invalid_values(df)
        quality_meta = {
            "latitude": float(latitude),
            "longitude": float(longitude),
            "source_api": "https://marine-api.open-meteo.com/v1/marine",
            "retrieval_timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "processing_version": "1.0.0",
            "null_value_count": null_value_count,
            "duplicate_timestamp_count": duplicate_timestamps,
            "duplicate_timestamps": df.loc[df["timestamp"].duplicated(), "timestamp"].tolist(),
            "invalid_value_indexes": invalid_indexes,
            "invalid_value_count": len(invalid_indexes),
            "unit_conversions": unit_conversions,
            "requested_variables": [name for name in variable_names if name in hourly],
            "units": {name: units.get(name, self.unit_metadata().get(name, "unknown")) for name in variable_names if name in hourly},
        }
        return df, quality_meta

    def process(
        self,
        latitude: float,
        longitude: float,
        start_date: str,
        end_date: str,
        variables: list[str] | None = None,
        timezone: str = "auto",
    ) -> dict[str, Any]:
        raw_payload = self.client.fetch_hourly_data(
            latitude=latitude,
            longitude=longitude,
            start_date=start_date,
            end_date=end_date,
            variables=variables,
            timezone=timezone,
        )

        raw_path = self.raw_dir / "open_meteo_marine_raw.json"
        raw_path.write_text(json.dumps(raw_payload, indent=2, default=str), encoding="utf-8")

        cleaner_df, quality_meta = self._normalize_payload(raw_payload, latitude, longitude)
        if cleaner_df.empty:
            cleaner_df = pd.DataFrame(columns=list(self.schema_definition().keys()))

        clean_csv_path = self.output_dir / "open_meteo_marine_clean.csv"
        clean_parquet_path = self.output_dir / "open_meteo_marine_clean.parquet"
        schema_path = self.output_dir / "schema.json"
        report_json_path = self.output_dir / "data_quality_report.json"
        report_md_path = self.output_dir / "data_quality_report.md"

        cleaned_df = cleaner_df.copy()
        schema_columns = list(self.schema_definition().keys())
        if not cleaned_df.empty:
            cleaned_df = cleaned_df.reindex(columns=schema_columns)
        else:
            cleaned_df = pd.DataFrame(columns=schema_columns)
        cleaned_df.to_csv(clean_csv_path, index=False)
        if not clean_parquet_path.exists():
            cleaned_df.to_parquet(clean_parquet_path, index=False)

        schema_path.write_text(json.dumps(self.schema_definition(), indent=2), encoding="utf-8")

        quality_record = {
            "dataset_name": "open_meteo_marine",
            "source_api": quality_meta["source_api"],
            "latitude": latitude,
            "longitude": longitude,
            "start_date": start_date,
            "end_date": end_date,
            "requested_variables": variables or self.client.DEFAULT_VARIABLES,
            "source_provenance": {
                "api_url": quality_meta["source_api"],
                "retrieval_timestamp_utc": quality_meta["retrieval_timestamp_utc"],
                "processing_version": quality_meta["processing_version"],
            },
            "original_row_count": int(len(raw_payload.get("hourly", {}).get("time", []))),
            "processed_row_count": int(len(cleaned_df)),
            "null_value_count": int(quality_meta["null_value_count"]),
            "duplicate_timestamp_count": int(quality_meta["duplicate_timestamp_count"]),
            "duplicate_timestamps": quality_meta["duplicate_timestamps"],
            "invalid_value_count": int(quality_meta["invalid_value_count"]),
            "invalid_value_indexes": quality_meta["invalid_value_indexes"],
            "unit_conversions": quality_meta["unit_conversions"],
            "units": quality_meta["units"],
            "missing_values": cleaned_df.isna().sum().to_dict(),
            "columns_detected": list(cleaned_df.columns),
            "schema": self.schema_definition(),
            "raw_response_path": str(raw_path),
            "clean_csv_path": str(clean_csv_path),
            "clean_parquet_path": str(clean_parquet_path),
            "transformations_performed": [
                "Fetched hourly marine observations from the official Open-Meteo Marine API.",
                "Preserved the original raw JSON payload without modifying the source response.",
                "Validated required hourly fields and coordinate bounds.",
                "Normalized marine variables into a tabular schema keyed by timestamp and location.",
                "Recorded nulls, duplicate timestamps, invalid values, and unit conversions in quality metadata.",
                "Persisted cleaned CSV, Parquet, schema, and quality-report artifacts.",
            ],
        }
        report_json_path.write_text(json.dumps(quality_record, indent=2, default=str), encoding="utf-8")

        md_lines = [
            "# Open-Meteo Marine Data Quality Report",
            "",
            f"- Dataset: {quality_record['dataset_name']}",
            f"- Source API: {quality_record['source_api']}",
            f"- Latitude: {latitude}",
            f"- Longitude: {longitude}",
            f"- Date range: {start_date} to {end_date}",
            f"- Processed row count: {quality_record['processed_row_count']}",
            "",
            "## Schema",
            "",
            json.dumps(quality_record["schema"], indent=2),
            "",
            "## Missing values",
            "",
            json.dumps(quality_record["missing_values"], indent=2),
            "",
            "## Duplicate timestamps",
            "",
            str(quality_record["duplicate_timestamp_count"]),
            "",
            "## Invalid values",
            "",
            str(quality_record["invalid_value_count"]),
            "",
            "## Unit conversions",
            "",
            json.dumps(quality_record["unit_conversions"], indent=2),
            "",
            "## Transformations performed",
        ]
        for item in quality_record["transformations_performed"]:
            md_lines.append(f"- {item}")
        report_md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

        return {
            "processed_rows": int(len(cleaned_df)),
            "raw_response_path": str(raw_path),
            "clean_csv_path": str(clean_csv_path),
            "clean_parquet_path": str(clean_parquet_path),
            "schema_path": str(schema_path),
            "quality_report_json": str(report_json_path),
            "quality_report_md": str(report_md_path),
            "dataframe": cleaned_df,
            "null_value_count": int(quality_meta["null_value_count"]),
            "duplicate_timestamps": int(quality_meta["duplicate_timestamp_count"]),
            "quality_record": quality_record,
        }
