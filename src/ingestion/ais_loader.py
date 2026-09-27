"""Memory-efficient ingestion for compressed NOAA MarineCadastre AIS broadcasts."""

from __future__ import annotations

import json
import logging
import sqlite3
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import pandas as pd
import zstandard as zstd

logger = logging.getLogger(__name__)


class AISDataLoader:
    """Stream, normalize, validate, and persist a compressed AIS CSV."""

    EXPECTED_MAGIC = b"\x28\xb5\x2f\xfd"
    RAW_COLUMNS = [
        "mmsi",
        "base_date_time",
        "longitude",
        "latitude",
        "sog",
        "cog",
        "heading",
        "vessel_name",
        "imo",
        "call_sign",
        "vessel_type",
        "status",
        "length",
        "width",
        "draft",
        "cargo",
        "transceiver",
    ]
    NUMERIC_COLUMNS = [
        "mmsi",
        "longitude",
        "latitude",
        "sog",
        "cog",
        "heading",
        "vessel_type",
        "status",
        "length",
        "width",
        "draft",
        "cargo",
    ]
    OUTPUT_COLUMNS = [
        "mmsi",
        "timestamp",
        "longitude",
        "latitude",
        "speed_knots",
        "course_over_ground_deg",
        "heading_deg",
        "vessel_name",
        "imo",
        "call_sign",
        "vessel_type",
        "navigation_status",
        "length_m",
        "width_m",
        "draft_m",
        "cargo",
        "transceiver",
    ]
    SAMPLE_COLUMNS = [
        "mmsi",
        "base_date_time",
        "latitude",
        "longitude",
        "sog",
        "cog",
        "heading",
        "vessel_type",
        "length",
        "width",
        "draft",
    ]

    def __init__(
        self,
        raw_path: str | Path,
        output_dir: str | Path = "data/processed/ais",
        chunksize: int = 100_000,
    ) -> None:
        self.raw_path = Path(raw_path)
        self.output_dir = Path(output_dir)
        self.chunksize = int(chunksize)
        if self.chunksize < 1:
            raise ValueError("chunksize must be at least 1.")

    @staticmethod
    def _normalize_column_name(value: str) -> str:
        return str(value).strip().lower().replace(" ", "_").replace("-", "_")

    def _open_csv_stream(self):
        if not self.raw_path.exists():
            raise FileNotFoundError(f"AIS dataset not found at {self.raw_path}")
        with self.raw_path.open("rb") as raw_file:
            magic = raw_file.read(4)
            if magic != self.EXPECTED_MAGIC:
                raise ValueError("AIS input is not a Zstandard-compressed stream.")

        raw_file = self.raw_path.open("rb")
        decompressor = zstd.ZstdDecompressor().stream_reader(raw_file)
        text_stream = __import__("io").TextIOWrapper(decompressor, encoding="utf-8", newline="")
        return raw_file, decompressor, text_stream

    def iter_chunks(self) -> Iterator[pd.DataFrame]:
        raw_file, decompressor, text_stream = self._open_csv_stream()
        try:
            reader = pd.read_csv(
                text_stream,
                chunksize=self.chunksize,
                dtype=str,
                keep_default_na=False,
                na_filter=False,
            )
            for chunk in reader:
                chunk.columns = [self._normalize_column_name(column) for column in chunk.columns]
                yield chunk
        finally:
            text_stream.close()
            decompressor.close()
            raw_file.close()

    def validate_input_format(self) -> None:
        """Validate the source path and compression before allocating indexes."""
        raw_file, decompressor, text_stream = self._open_csv_stream()
        text_stream.close()
        decompressor.close()
        raw_file.close()

    def create_sample(self, output_path: str | Path, max_rows: int = 10_000) -> dict[str, Any]:
        """Write a bounded, valid AIS sample without scanning the full archive."""
        if max_rows < 1 or max_rows > 10_000:
            raise ValueError("max_rows must be between 1 and 10000.")

        sample_rows: list[pd.DataFrame] = []
        sampled_rows = 0
        for chunk in self.iter_chunks():
            normalized = chunk.reindex(columns=self.SAMPLE_COLUMNS).copy()
            normalized["mmsi"] = normalized["mmsi"].replace("", pd.NA).astype("string")
            normalized["base_date_time"] = pd.to_datetime(
                normalized["base_date_time"], errors="coerce", utc=True
            )
            for column in ["latitude", "longitude"]:
                normalized[column] = pd.to_numeric(normalized[column], errors="coerce")

            valid = normalized.loc[
                normalized["mmsi"].notna()
                & normalized["base_date_time"].notna()
                & normalized["latitude"].notna()
                & normalized["longitude"].notna()
                & normalized["latitude"].between(-90, 90)
                & normalized["longitude"].between(-180, 180)
            ].copy()
            remaining = max_rows - sampled_rows
            sample_rows.append(valid.head(remaining))
            sampled_rows += min(len(valid), remaining)
            if sampled_rows >= max_rows:
                break

        sample = pd.concat(sample_rows, ignore_index=True) if sample_rows else pd.DataFrame(columns=self.SAMPLE_COLUMNS)
        sample["base_date_time"] = sample["base_date_time"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        sample.to_csv(output, index=False)

        return {
            "sampled_rows": int(len(sample)),
            "unique_mmsis": int(sample["mmsi"].nunique(dropna=True)),
            "timestamp_range_utc": [
                sample["base_date_time"].min() if not sample.empty else None,
                sample["base_date_time"].max() if not sample.empty else None,
            ],
            "missing_values": sample.isna().sum().to_dict(),
            "output_path": str(output),
        }

    @staticmethod
    def create_query_points(
        input_path: str | Path,
        output_path: str | Path,
        target_points: int = 200,
    ) -> dict[str, Any]:
        """Create deterministic, spatial-temporal query points from an AIS sample."""
        if not 100 <= target_points <= 300:
            raise ValueError("target_points must be between 100 and 300.")

        required_columns = ["mmsi", "base_date_time", "latitude", "longitude", "sog"]
        frame = pd.read_csv(input_path, usecols=required_columns)
        original_rows = len(frame)
        frame["mmsi"] = frame["mmsi"].replace("", pd.NA).astype("string")
        frame["timestamp"] = pd.to_datetime(frame.pop("base_date_time"), errors="coerce", utc=True)
        frame["latitude"] = pd.to_numeric(frame["latitude"], errors="coerce")
        frame["longitude"] = pd.to_numeric(frame["longitude"], errors="coerce")

        valid = frame.loc[
            frame["mmsi"].notna()
            & frame["timestamp"].notna()
            & frame["latitude"].notna()
            & frame["longitude"].notna()
            & frame["latitude"].between(-90, 90)
            & frame["longitude"].between(-180, 180)
        ].copy()

        valid = valid.sort_values(
            ["mmsi", "timestamp", "latitude", "longitude"], kind="mergesort"
        )
        valid["_time_bucket"] = valid["timestamp"].dt.floor("h")
        valid["_latitude_bucket"] = valid["latitude"].floordiv(0.5)
        valid["_longitude_bucket"] = valid["longitude"].floordiv(0.5)
        candidates = valid.drop_duplicates(
            ["mmsi", "_time_bucket", "_latitude_bucket", "_longitude_bucket"],
            keep="first",
        )

        if len(candidates) > target_points:
            positions = [
                round(index * (len(candidates) - 1) / (target_points - 1))
                for index in range(target_points)
            ]
            query_points = candidates.iloc[positions].copy()
        else:
            query_points = candidates.copy()

        query_points = query_points[["mmsi", "timestamp", "latitude", "longitude", "sog"]]
        query_points["timestamp"] = query_points["timestamp"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        query_points.to_csv(output, index=False)

        return {
            "original_rows": int(original_rows),
            "valid_rows": int(len(valid)),
            "query_point_count": int(len(query_points)),
            "unique_vessels": int(query_points["mmsi"].nunique()),
            "timestamp_range": [query_points["timestamp"].min(), query_points["timestamp"].max()],
            "latitude_range": [float(query_points["latitude"].min()), float(query_points["latitude"].max())],
            "longitude_range": [float(query_points["longitude"].min()), float(query_points["longitude"].max())],
            "output_path": str(output),
        }

    @staticmethod
    def _canonicalize_chunk(chunk: pd.DataFrame) -> pd.DataFrame:
        normalized = chunk.copy()
        for column in normalized.columns:
            normalized[column] = normalized[column].map(
                lambda value: value.strip() if isinstance(value, str) else value
            )

        renamed = normalized.rename(
            columns={
                "base_date_time": "timestamp",
                "sog": "speed_knots",
                "cog": "course_over_ground_deg",
                "heading": "heading_deg",
                "status": "navigation_status",
                "length": "length_m",
                "width": "width_m",
                "draft": "draft_m",
            }
        )
        for column in [
            "timestamp",
            "longitude",
            "latitude",
            "speed_knots",
            "course_over_ground_deg",
            "heading_deg",
            "vessel_type",
            "navigation_status",
            "length_m",
            "width_m",
            "draft_m",
            "cargo",
        ]:
            if column not in renamed.columns:
                renamed[column] = pd.NA

        renamed["timestamp"] = pd.to_datetime(renamed["timestamp"], errors="coerce", utc=True)
        for column in [
            "longitude",
            "latitude",
            "speed_knots",
            "course_over_ground_deg",
            "heading_deg",
            "vessel_type",
            "navigation_status",
            "length_m",
            "width_m",
            "draft_m",
            "cargo",
        ]:
            renamed[column] = pd.to_numeric(renamed[column], errors="coerce")

        renamed["mmsi"] = renamed["mmsi"].replace("", pd.NA).astype("string")

        return renamed.reindex(columns=AISDataLoader.OUTPUT_COLUMNS)

    @staticmethod
    def schema_definition() -> dict[str, dict[str, str]]:
        return {
            "mmsi": {"type": "string", "unit": "n/a", "description": "Maritime Mobile Service Identity."},
            "timestamp": {"type": "datetime", "unit": "UTC", "description": "AIS broadcast timestamp normalized to UTC."},
            "longitude": {"type": "float", "unit": "degrees", "description": "Broadcast longitude."},
            "latitude": {"type": "float", "unit": "degrees", "description": "Broadcast latitude."},
            "speed_knots": {"type": "float", "unit": "knots", "description": "Speed over ground."},
            "course_over_ground_deg": {"type": "float", "unit": "degrees", "description": "Course over ground."},
            "heading_deg": {"type": "float", "unit": "degrees", "description": "Vessel heading."},
            "vessel_name": {"type": "string", "unit": "n/a", "description": "Broadcast vessel name."},
            "imo": {"type": "string", "unit": "n/a", "description": "IMO vessel identifier when broadcast."},
            "call_sign": {"type": "string", "unit": "n/a", "description": "Radio call sign when broadcast."},
            "vessel_type": {"type": "integer", "unit": "AIS code", "description": "AIS vessel type code."},
            "navigation_status": {"type": "integer", "unit": "AIS code", "description": "AIS navigation status code."},
            "length_m": {"type": "float", "unit": "m", "description": "Reported vessel length."},
            "width_m": {"type": "float", "unit": "m", "description": "Reported vessel width."},
            "draft_m": {"type": "float", "unit": "m", "description": "Reported vessel draft."},
            "cargo": {"type": "integer", "unit": "AIS code", "description": "AIS cargo code."},
            "transceiver": {"type": "string", "unit": "n/a", "description": "AIS transceiver class."},
        }

    def process(self) -> dict[str, Any]:
        started = time.perf_counter()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        clean_csv_path = self.output_dir / "ais_clean.csv"
        schema_path = self.output_dir / "schema.json"
        report_json_path = self.output_dir / "data_quality_report.json"
        report_md_path = self.output_dir / "data_quality_report.md"

        if clean_csv_path.exists():
            clean_csv_path.unlink()

        missing_values = {column: 0 for column in self.RAW_COLUMNS}
        unique_vessels = 0
        raw_rows = 0
        processed_rows = 0
        duplicate_observations = 0
        invalid_coordinates = 0
        missing_coordinates = 0
        invalid_timestamps = 0
        min_timestamp = max_timestamp = None
        min_latitude = max_latitude = min_longitude = max_longitude = None
        first_chunk = True

        self.validate_input_format()

        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "duplicate_index.sqlite3"
            connection = sqlite3.connect(database_path)
            connection.execute("PRAGMA journal_mode=OFF")
            connection.execute("PRAGMA synchronous=OFF")
            connection.execute("CREATE TABLE vessels (mmsi TEXT PRIMARY KEY)")
            connection.execute("CREATE TABLE observations (key INTEGER PRIMARY KEY)")
            connection.execute("CREATE TEMP TABLE current_keys (key INTEGER PRIMARY KEY)")

            for chunk in self.iter_chunks():
                raw_rows += len(chunk)
                for column in self.RAW_COLUMNS:
                    if column in chunk.columns:
                        missing_values[column] += int((chunk[column] == "").sum())

                cleaned = self._canonicalize_chunk(chunk)
                invalid_timestamps += int(cleaned["timestamp"].isna().sum())
                missing_coordinates += int(
                    (cleaned["latitude"].isna() | cleaned["longitude"].isna()).sum()
                )
                coordinate_present = cleaned["latitude"].notna() & cleaned["longitude"].notna()
                invalid_mask = coordinate_present & (
                    (cleaned["latitude"] < -90)
                    | (cleaned["latitude"] > 90)
                    | (cleaned["longitude"] < -180)
                    | (cleaned["longitude"] > 180)
                )
                invalid_coordinates += int(invalid_mask.sum())

                valid_rows = cleaned.loc[
                    cleaned["mmsi"].notna()
                    & cleaned["timestamp"].notna()
                    & coordinate_present
                    & ~invalid_mask
                ].copy()
                if not valid_rows.empty:
                    connection.executemany(
                        "INSERT OR IGNORE INTO vessels VALUES (?)",
                        [(str(mmsi),) for mmsi in valid_rows["mmsi"].unique()],
                    )
                    key_frame = valid_rows[["mmsi", "timestamp", "longitude", "latitude"]].astype("string")
                    observation_keys = pd.util.hash_pandas_object(key_frame, index=False).astype("int64")
                    valid_rows["_observation_key"] = observation_keys.to_numpy()
                    unique_keys = [(int(key),) for key in observation_keys.unique()]
                    connection.execute("DELETE FROM current_keys")
                    connection.executemany("INSERT OR IGNORE INTO current_keys VALUES (?)", unique_keys)
                    new_keys = {
                        int(row[0])
                        for row in connection.execute(
                            "SELECT current_keys.key FROM current_keys "
                            "LEFT JOIN observations ON observations.key = current_keys.key "
                            "WHERE observations.key IS NULL"
                        )
                    }
                    duplicate_observations += len(valid_rows) - len(new_keys)
                    connection.executemany("INSERT OR IGNORE INTO observations VALUES (?)", unique_keys)
                    valid_rows = valid_rows.loc[
                        valid_rows["_observation_key"].isin(new_keys)
                        & ~valid_rows["_observation_key"].duplicated()
                    ].drop(columns=["_observation_key"])

                processed_rows += len(valid_rows)
                if not valid_rows.empty:
                    timestamps = valid_rows["timestamp"]
                    current_min = timestamps.min()
                    current_max = timestamps.max()
                    min_timestamp = current_min if min_timestamp is None else min(min_timestamp, current_min)
                    max_timestamp = current_max if max_timestamp is None else max(max_timestamp, current_max)
                    min_latitude = valid_rows["latitude"].min() if min_latitude is None else min(min_latitude, valid_rows["latitude"].min())
                    max_latitude = valid_rows["latitude"].max() if max_latitude is None else max(max_latitude, valid_rows["latitude"].max())
                    min_longitude = valid_rows["longitude"].min() if min_longitude is None else min(min_longitude, valid_rows["longitude"].min())
                    max_longitude = valid_rows["longitude"].max() if max_longitude is None else max(max_longitude, valid_rows["longitude"].max())
                    output = valid_rows.copy()
                    output["timestamp"] = output["timestamp"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
                    output.to_csv(clean_csv_path, mode="w" if first_chunk else "a", header=first_chunk, index=False)
                    first_chunk = False
                connection.commit()

            unique_vessels = int(connection.execute("SELECT COUNT(*) FROM vessels").fetchone()[0])
            connection.close()

        if first_chunk:
            pd.DataFrame(columns=self.OUTPUT_COLUMNS).to_csv(clean_csv_path, index=False)

        processing_seconds = round(time.perf_counter() - started, 3)
        quality_record = {
            "dataset_name": "noaa_marinecadastre_ais_broadcast_points",
            "raw_source_path": str(self.raw_path),
            "raw_file_size_bytes": self.raw_path.stat().st_size,
            "compression_format": "Zstandard frame containing a direct CSV stream",
            "raw_columns": self.RAW_COLUMNS,
            "processed_columns": self.OUTPUT_COLUMNS,
            "raw_row_count": raw_rows,
            "processed_row_count": processed_rows,
            "unique_vessel_count": unique_vessels,
            "timestamp_range_utc": [
                min_timestamp.isoformat().replace("+00:00", "Z") if min_timestamp is not None else None,
                max_timestamp.isoformat().replace("+00:00", "Z") if max_timestamp is not None else None,
            ],
            "geographic_range": {
                "latitude": [min_latitude, max_latitude],
                "longitude": [min_longitude, max_longitude],
            },
            "missing_values_by_raw_column": missing_values,
            "missing_coordinate_rows": missing_coordinates,
            "invalid_coordinate_rows": invalid_coordinates,
            "invalid_timestamp_rows": invalid_timestamps,
            "duplicate_observation_count": duplicate_observations,
            "processing_seconds": processing_seconds,
            "processed_file_size_bytes": clean_csv_path.stat().st_size,
            "chunksize": self.chunksize,
            "source_provenance": {
                "source": "NOAA MarineCadastre AIS Broadcast Points",
                "raw_file_preserved": True,
                "transformations": [
                    "Streamed Zstandard-compressed CSV without extraction.",
                    "Normalized source names into stable AIS output names.",
                    "Normalized timestamps to UTC.",
                    "Removed rows missing required MMSI, timestamp, or valid coordinates.",
                    "Removed duplicate observations keyed by MMSI, timestamp, longitude, and latitude.",
                ],
            },
            "schema": self.schema_definition(),
            "clean_csv_path": str(clean_csv_path),
        }
        schema_path.write_text(json.dumps(self.schema_definition(), indent=2), encoding="utf-8")
        report_json_path.write_text(json.dumps(quality_record, indent=2, default=str), encoding="utf-8")
        report_md_path.write_text(self._markdown_report(quality_record), encoding="utf-8")
        return {
            "dataframe": None,
            "clean_csv_path": str(clean_csv_path),
            "schema_path": str(schema_path),
            "quality_report_json": str(report_json_path),
            "quality_report_md": str(report_md_path),
            "quality_record": quality_record,
        }

    @staticmethod
    def _markdown_report(record: dict[str, Any]) -> str:
        return "\n".join(
            [
                "# NOAA MarineCadastre AIS Data Quality Report",
                "",
                f"- Raw rows: {record['raw_row_count']}",
                f"- Processed rows: {record['processed_row_count']}",
                f"- Unique vessels: {record['unique_vessel_count']}",
                f"- Timestamp range (UTC): {record['timestamp_range_utc']}",
                f"- Geographic range: {record['geographic_range']}",
                f"- Missing coordinate rows: {record['missing_coordinate_rows']}",
                f"- Invalid coordinate rows: {record['invalid_coordinate_rows']}",
                f"- Duplicate observations removed: {record['duplicate_observation_count']}",
                f"- Processing time (seconds): {record['processing_seconds']}",
                f"- Processed file size (bytes): {record['processed_file_size_bytes']}",
                "",
                "## Source columns",
                "",
                ", ".join(record["raw_columns"]),
                "",
                "## Missing values",
                "",
                "```json",
                json.dumps(record["missing_values_by_raw_column"], indent=2),
                "```",
                "",
                "## Provenance",
                "",
                "The raw compressed source was preserved unchanged. AIS rows were streamed in bounded chunks; no synthetic values were introduced.",
                "",
            ]
        )
