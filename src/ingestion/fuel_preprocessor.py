"""Preprocessing pipeline for GreenFleet fuel consumption data."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pandas as pd

from .fuel_loader import FuelDataLoader
from .schema import GREENFLEET_CANONICAL_SCHEMA, map_dataset_to_canonical_schema
from .validation import detect_invalid_records, detect_missing_values, detect_possible_outliers, validate_required_columns

logger = logging.getLogger(__name__)


class GreenFleetFuelPreprocessor:
    """Load, clean, validate, and export the fuel dataset."""

    def __init__(self, source_path: str | Path):
        self.source_path = Path(source_path)
        self.loader = FuelDataLoader(self.source_path)
        self.output_dir = Path("data/processed/fuel")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _source_provenance() -> dict[str, Any]:
        try:
            git_config = Path(".git/config").read_text(encoding="utf-8")
            remote_url = None
            for line in git_config.splitlines():
                if line.strip().startswith("url = "):
                    remote_url = line.split("=", 1)[1].strip()
                    break
        except FileNotFoundError:
            remote_url = None

        return {
            "project_repository_url": remote_url,
            "dataset_repository_url": None,
            "dataset_source_note": "No explicit dataset metadata, notebook, or README section documenting the original source repository or units was found in the project contents.",
            "source_file_path": "data/raw/fuel/ship_fuel_efficiency.csv",
        }

    @staticmethod
    def _unit_verification() -> dict[str, Any]:
        return {
            "confirmed_units": {},
            "inferred_units": {
                "distance": {
                    "value": "likely nautical miles",
                    "basis": "domain inference only; not explicitly documented in project files",
                },
                "fuel_consumption": {
                    "value": "likely liters",
                    "basis": "domain inference only; not explicitly documented in project files",
                },
                "co2_emissions": {
                    "value": "likely kg CO2",
                    "basis": "domain inference only; not explicitly documented in project files",
                },
                "engine_efficiency": {
                    "value": "likely percent",
                    "basis": "domain inference only; not explicitly documented in project files",
                },
            },
            "unknown_units": {
                "distance": "No explicit unit documentation was found in the README or dataset metadata.",
                "fuel_consumption": "No explicit unit documentation was found in the README or dataset metadata.",
                "co2_emissions": "No explicit unit documentation was found in the README or dataset metadata.",
                "engine_efficiency": "No explicit unit documentation was found in the README or dataset metadata.",
            },
            "verification_note": "These units are not confirmed by source documentation; they are only inferred from domain conventions and data semantics.",
        }

    def process(self) -> dict[str, Any]:
        raw_df = self.loader.load_raw_csv()
        renamed_df = self.loader.normalize_columns(raw_df)

        numeric_columns = [
            "distance",
            "fuel_consumption",
            "co2_emissions",
            "engine_efficiency",
        ]
        renamed_df = self.loader.coerce_numeric_columns(renamed_df, numeric_columns)
        renamed_df = self.loader.standardize_string_columns(renamed_df, ["ship_id", "ship_type", "route_id", "month", "fuel_type", "weather_conditions"])
        renamed_df = self.loader.canonicalize_categorical_values(renamed_df)

        original_row_count = len(raw_df)
        missing_stats = self.loader.detect_missing_values(renamed_df)
        duplicate_count = self.loader.detect_duplicate_rows(renamed_df)
        invalid_indexes = self.loader.detect_invalid_records(renamed_df)
        possible_outlier_indexes = self.loader.detect_possible_outliers(renamed_df, numeric_columns)

        cleaned_df = renamed_df.copy()
        if invalid_indexes:
            cleaned_df = cleaned_df.drop(index=invalid_indexes).copy()

        processed_row_count = len(cleaned_df)

        schema_mapping = map_dataset_to_canonical_schema(cleaned_df)
        quality_record = {
            "dataset_name": "ship_fuel_efficiency",
            "source_path": str(self.source_path),
            "source_type": "CSV",
            "source_provenance": self._source_provenance(),
            "unit_verification": self._unit_verification(),
            "original_row_count": original_row_count,
            "processed_row_count": processed_row_count,
            "column_count": int(cleaned_df.shape[1]),
            "columns_detected": list(cleaned_df.columns),
            "data_types": {column: str(dtype) for column, dtype in cleaned_df.dtypes.items()},
            "missing_values": missing_stats,
            "duplicate_count": duplicate_count,
            "invalid_record_count": len(invalid_indexes),
            "possible_outlier_count": len(possible_outlier_indexes),
            "possible_outlier_indexes": possible_outlier_indexes,
            "invalid_record_indexes": invalid_indexes,
            "categorical_distributions": {
                column: cleaned_df[column].value_counts(dropna=False).to_dict()
                for column in ["ship_id", "ship_type", "route_id", "month", "fuel_type", "weather_conditions"]
                if column in cleaned_df.columns
            },
            "numerical_summary_statistics": cleaned_df[numeric_columns].describe().round(4).to_dict(),
            "detected_units": self._unit_verification(),
            "schema_mapping": schema_mapping,
            "canonical_schema": dict(GREENFLEET_CANONICAL_SCHEMA),
            "transformations_performed": [
                "Loaded raw CSV without modifying source file",
                "Normalized all columns to snake_case",
                "Cast numeric columns to pandas numeric types",
                "Standardized empty strings to missing values",
                "Normalized categorical labels to canonical values",
                "Detected missing values and duplicates",
                "Flagged invalid records using domain constraints",
                "Separated invalid records from possible outliers",
                "Mapped source columns to GreenFleet canonical schema",
            ],
            "fields_available_for_ml": [
                "distance",
                "fuel_type",
                "fuel_consumption",
                "co2_emissions",
                "weather_conditions",
                "engine_efficiency",
                "ship_type",
                "month",
                "route_id",
            ],
            "fields_unavailable": [
                "cargo_capacity",
                "cargo_load",
                "speed",
                "wind_speed",
                "wave_height",
                "current_speed",
            ],
            "known_limitations": [
                "No vessel-specific cargo capacity or load fields are present.",
                "No weather API or ocean conditions are available in this dataset.",
                "No vessel speed or current data are available in the source CSV.",
            ],
            "future_data_requirements": [
                "IMO DCS reporting data for fleet-level emissions and fuel usage.",
                "Vessel metadata including cargo capacity, speed, and design characteristics.",
                "AIS or route telemetry for time-stamped vessel movement.",
                "Weather and ocean-condition APIs for wind, wave, and current values.",
            ],
        }

        clean_csv_path = self.output_dir / "greenfleet_fuel_clean.csv"
        clean_parquet_path = self.output_dir / "greenfleet_fuel_clean.parquet"
        schema_path = self.output_dir / "schema.json"
        report_json_path = self.output_dir / "data_quality_report.json"
        report_md_path = self.output_dir / "data_quality_report.md"

        cleaned_df.to_csv(clean_csv_path, index=False)
        cleaned_df.to_parquet(clean_parquet_path, index=False)
        schema_path.write_text(json.dumps(dict(GREENFLEET_CANONICAL_SCHEMA), indent=2), encoding="utf-8")
        report_json_path.write_text(json.dumps(quality_record, indent=2, default=str), encoding="utf-8")

        md_lines = [
            "# GreenFleet Fuel Data Quality Report",
            "",
            f"- Dataset name: {quality_record['dataset_name']}",
            f"- Source path: {quality_record['source_path']}",
            f"- Original row count: {quality_record['original_row_count']}",
            f"- Processed row count: {quality_record['processed_row_count']}",
            f"- Column count: {quality_record['column_count']}",
            "",
            "## Data lineage",
            "",
            "RAW CSV → LOAD → SCHEMA NORMALIZATION → TYPE CONVERSION → VALIDATION → CLEANING → CANONICAL GREENFLEET SCHEMA → PROCESSED DATA",
            "",
            "## Source provenance",
            "",
            f"- Project repository URL: {quality_record['source_provenance']['project_repository_url']}",
            f"- Dataset repository URL: {quality_record['source_provenance']['dataset_repository_url']}",
            f"- Dataset note: {quality_record['source_provenance']['dataset_source_note']}",
            "",
            "## Unit verification",
            "",
            "No units were explicitly documented in the project README, notebook, or source metadata. The following statuses reflect verified evidence rather than inference.",
            "",
            f"- Confirmed units: {json.dumps(quality_record['unit_verification']['confirmed_units'], indent=2)}",
            f"- Inferred units: {json.dumps(quality_record['unit_verification']['inferred_units'], indent=2)}",
            f"- Unknown units: {json.dumps(quality_record['unit_verification']['unknown_units'], indent=2)}",
            f"- Verification note: {quality_record['unit_verification']['verification_note']}",
            "",
            "## Column descriptions",
        ]
        for col in cleaned_df.columns:
            md_lines.append(f"- {col}: {GREENFLEET_CANONICAL_SCHEMA.get('vessel_id' if col == 'ship_id' else col, {'description': 'No canonical description provided'})['description'] if col in ['ship_id'] else 'Operational source field'}")

        md_lines.extend([
            "",
            "## Missing-value statistics",
            json.dumps(quality_record["missing_values"], indent=2),
            "",
            "## Duplicate count",
            str(quality_record["duplicate_count"]),
            "",
            "## Invalid record count",
            str(quality_record["invalid_record_count"]),
            "",
            "## Possible outlier count",
            str(quality_record["possible_outlier_count"]),
            "",
            "## Categorical distributions",
            json.dumps(quality_record["categorical_distributions"], indent=2),
            "",
            "## Numerical summar statistics",
            json.dumps(quality_record["numerical_summary_statistics"], indent=2),
            "",
            "## Detected units",
            json.dumps(quality_record["detected_units"], indent=2),
            "",
            "## Confirmed vs inferred unit status",
            json.dumps(quality_record["unit_verification"], indent=2),
            "",
            "## Transformations performed",
        ])
        for item in quality_record["transformations_performed"]:
            md_lines.append(f"- {item}")

        md_lines.extend([
            "",
            "## GreenFleet schema mapping",
            json.dumps(quality_record["schema_mapping"], indent=2),
            "",
            "## Fields unavailable",
            json.dumps(quality_record["fields_unavailable"], indent=2),
            "",
            "## Known limitations",
        ])
        for item in quality_record["known_limitations"]:
            md_lines.append(f"- {item}")
        md_lines.extend(["", "## Future data requirements"])
        for item in quality_record["future_data_requirements"]:
            md_lines.append(f"- {item}")
        report_md_path.write_text("\n".join(md_lines), encoding="utf-8")

        return {
            "clean_df": cleaned_df,
            "processed_rows": processed_row_count,
            "invalid_record_count": len(invalid_indexes),
            "possible_outlier_count": len(possible_outlier_indexes),
            "clean_csv_path": str(clean_csv_path),
            "clean_parquet_path": str(clean_parquet_path),
            "schema_path": str(schema_path),
            "quality_report_json": str(report_json_path),
            "quality_report_md": str(report_md_path),
        }
