"""Historical Open-Meteo Marine retrieval for AIS query points.

This module only retrieves and normalizes marine observations. It does not join
those observations to AIS records or perform any modeling.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
import requests


DEFAULT_MARINE_VARIABLES = [
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


@dataclass(frozen=True)
class HistoricalMarineConfig:
    """Runtime configuration for historical marine retrieval."""

    api_url: str = "https://marine-api.open-meteo.com/v1/marine"
    timeout_seconds: float = 30.0
    max_retries: int = 3
    retry_backoff_seconds: float = 1.0
    coordinate_batch_size: int = 50
    cache_dir: Path = Path("data/raw/marine/historical_cache")
    variables: tuple[str, ...] = field(default_factory=lambda: tuple(DEFAULT_MARINE_VARIABLES))

    def __post_init__(self) -> None:
        if self.max_retries < 1:
            raise ValueError("max_retries must be at least 1.")
        if self.coordinate_batch_size < 1:
            raise ValueError("coordinate_batch_size must be at least 1.")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive.")


class HistoricalMarineClient:
    """Batch and cache historical Open-Meteo Marine requests."""

    def __init__(self, config: HistoricalMarineConfig | None = None) -> None:
        self.config = config or HistoricalMarineConfig()
        self.config.cache_dir.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session()

    @staticmethod
    def _cache_key(
        api_url: str,
        query_date: str,
        coordinates: list[tuple[float, float]],
        variables: tuple[str, ...],
    ) -> str:
        payload = {
            "api_url": api_url,
            "date": query_date,
            "coordinates": coordinates,
            "variables": variables,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _request_batch(
        self,
        query_date: str,
        coordinates: list[tuple[float, float]],
    ) -> tuple[Any, Path]:
        cache_name = self._cache_key(
            self.config.api_url,
            query_date,
            coordinates,
            self.config.variables,
        )
        cache_path = self.config.cache_dir / f"{cache_name}.json"
        if cache_path.exists():
            return json.loads(cache_path.read_text(encoding="utf-8")), cache_path

        params = {
            "latitude": ",".join(str(latitude) for latitude, _ in coordinates),
            "longitude": ",".join(str(longitude) for _, longitude in coordinates),
            "start_date": query_date,
            "end_date": query_date,
            "hourly": ",".join(self.config.variables),
            "timezone": "UTC",
        }
        last_error: Exception | None = None
        for attempt in range(1, self.config.max_retries + 1):
            try:
                response = self.session.get(
                    self.config.api_url,
                    params=params,
                    timeout=self.config.timeout_seconds,
                    headers={
                        "Accept": "application/json",
                        "User-Agent": "green-fleet-optimizer/1.0",
                    },
                )
                response.raise_for_status()
                payload = response.json()
                cache_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
                return payload, cache_path
            except (requests.RequestException, ValueError) as error:
                last_error = error
                if attempt < self.config.max_retries:
                    time.sleep(self.config.retry_backoff_seconds)

        raise RuntimeError(
            f"Historical Open-Meteo request failed after {self.config.max_retries} attempts."
        ) from last_error

    @staticmethod
    def _response_items(payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, dict):
            return [payload]
        if isinstance(payload, list) and all(isinstance(item, dict) for item in payload):
            return payload
        raise ValueError("Historical Open-Meteo response must be an object or list of objects.")

    @staticmethod
    def _hourly_record(item: dict[str, Any], timestamp: pd.Timestamp) -> dict[str, Any]:
        """Return the marine observation for the AIS timestamp's containing UTC hour."""
        hourly = item.get("hourly") or {}
        times = hourly.get("time") or []

        output_names = {
            "wave_height": "wave_height_m",
            "wave_direction": "wave_direction_deg",
            "wave_period": "wave_period_s",
            "wind_wave_height": "wind_wave_height_m",
            "wind_wave_direction": "wind_wave_direction_deg",
            "swell_wave_height": "swell_wave_height_m",
            "swell_wave_direction": "swell_wave_direction_deg",
            "ocean_current_velocity": "ocean_current_velocity_m_s",
            "ocean_current_direction": "ocean_current_direction_deg",
            "sea_surface_temperature": "sea_surface_temperature_c",
        }
        empty_record = {output_name: None for output_name in output_names.values()}
        if not times:
            empty_record["marine_data_available"] = False
            return empty_record

        # Open-Meteo returns hourly timestamps such as 2025-01-08T01:00.
        # Use the containing UTC hour, so an AIS timestamp at 01:23:45 maps to 01:00.
        hourly_timestamps = pd.to_datetime(times, errors="coerce", utc=True)
        target_hour = timestamp.tz_convert("UTC").floor("h")
        matching_indexes = [
            index for index, hourly_timestamp in enumerate(hourly_timestamps)
            if pd.notna(hourly_timestamp) and hourly_timestamp == target_hour
        ]
        if not matching_indexes:
            empty_record["marine_data_available"] = False
            return empty_record

        index = matching_indexes[0]
        record: dict[str, Any] = {}
        for variable, output_name in output_names.items():
            values = hourly.get(variable, [])
            value = values[index] if index < len(values) else None
            if variable == "ocean_current_velocity" and value is not None:
                value = float(value) / 3.6
            record[output_name] = value
        record["marine_data_available"] = any(
            value is not None and not pd.isna(value)
            for value in record.values()
        )
        return record

    @staticmethod
    def _nearest_response_item(
        response_items: list[dict[str, Any]],
        latitude: float,
        longitude: float,
    ) -> dict[str, Any]:
        """Select the closest API grid response when coordinates are rounded by the API."""
        candidates = [
            item
            for item in response_items
            if item.get("latitude") is not None and item.get("longitude") is not None
        ]
        if not candidates:
            return {}
        return min(
            candidates,
            key=lambda item: (
                (float(item["latitude"]) - latitude) ** 2
                + (float(item["longitude"]) - longitude) ** 2
            ),
        )

    @staticmethod
    def _batch_coordinates(
        query_points: pd.DataFrame,
        batch_size: int,
    ) -> Iterable[tuple[str, list[tuple[float, float]], pd.DataFrame]]:
        grouped = query_points.groupby("query_date", sort=True)
        for query_date, date_group in grouped:
            coordinates = list(
                dict.fromkeys(
                    (float(row.latitude), float(row.longitude))
                    for row in date_group.itertuples()
                )
            )
            for start in range(0, len(coordinates), batch_size):
                batch = coordinates[start : start + batch_size]
                coordinate_set = set(batch)
                batch_rows = date_group.loc[
                    date_group.apply(
                        lambda row: (float(row.latitude), float(row.longitude)) in coordinate_set,
                        axis=1,
                    )
                ]
                yield str(query_date), batch, batch_rows

    def retrieve(self, query_points: pd.DataFrame) -> pd.DataFrame:
        """Retrieve marine observations for valid AIS query-point rows."""
        required = {"mmsi", "timestamp", "latitude", "longitude", "sog"}
        missing = sorted(required.difference(query_points.columns))
        if missing:
            raise ValueError(f"Query points are missing required columns: {missing}")

        points = query_points.copy()
        points["timestamp"] = pd.to_datetime(points["timestamp"], errors="coerce", utc=True)
        points["latitude"] = pd.to_numeric(points["latitude"], errors="coerce")
        points["longitude"] = pd.to_numeric(points["longitude"], errors="coerce")
        points = points.loc[
            points["timestamp"].notna()
            & points["latitude"].between(-90, 90)
            & points["longitude"].between(-180, 180)
        ].copy()
        points["query_date"] = points["timestamp"].dt.strftime("%Y-%m-%d")

        records: list[dict[str, Any]] = []
        for query_date, coordinates, batch_rows in self._batch_coordinates(
            points, self.config.coordinate_batch_size
        ):
            payload, cache_path = self._request_batch(query_date, coordinates)
            response_items = self._response_items(payload)
            for row in batch_rows.itertuples(index=False):
                marine_values = self._hourly_record(
                    self._nearest_response_item(
                        response_items,
                        float(row.latitude),
                        float(row.longitude),
                    ),
                    row.timestamp,
                )
                records.append(
                    {
                        "mmsi": row.mmsi,
                        "timestamp": row.timestamp.isoformat(),
                        "latitude": row.latitude,
                        "longitude": row.longitude,
                        "sog": row.sog,
                        **marine_values,
                        "source": "Open-Meteo Historical Marine API",
                        "source_api": self.config.api_url,
                        "query_date": query_date,
                        "cache_path": str(cache_path),
                    }
                )

        return pd.DataFrame(records)


def retrieve_historical_marine_data(
    query_points_path: str | Path = "data/processed/ais/ais_marine_query_points.csv",
    output_path: str | Path = "data/processed/marine/historical_marine_observations.csv",
    config: HistoricalMarineConfig | None = None,
) -> pd.DataFrame:
    """Read AIS query points, retrieve cached/batched marine data, and save records."""
    query_points = pd.read_csv(query_points_path)
    result = HistoricalMarineClient(config).retrieve(query_points)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output, index=False)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Retrieve historical Open-Meteo Marine data for AIS query points.")
    parser.add_argument("--query-points", default="data/processed/ais/ais_marine_query_points.csv")
    parser.add_argument("--output", default="data/processed/marine/historical_marine_observations.csv")
    parser.add_argument("--api-url", default=HistoricalMarineConfig.api_url)
    parser.add_argument("--cache-dir", default=str(HistoricalMarineConfig.cache_dir))
    parser.add_argument("--batch-size", type=int, default=HistoricalMarineConfig.coordinate_batch_size)
    parser.add_argument("--timeout", type=float, default=HistoricalMarineConfig.timeout_seconds)
    parser.add_argument("--retries", type=int, default=HistoricalMarineConfig.max_retries)
    args = parser.parse_args()

    config = HistoricalMarineConfig(
        api_url=args.api_url,
        cache_dir=Path(args.cache_dir),
        coordinate_batch_size=args.batch_size,
        timeout_seconds=args.timeout,
        max_retries=args.retries,
    )
    retrieve_historical_marine_data(args.query_points, args.output, config)


if __name__ == "__main__":
    main()
