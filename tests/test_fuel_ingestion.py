from pathlib import Path

import pandas as pd

from src.ingestion.fuel_loader import FuelDataLoader
from src.ingestion.fuel_preprocessor import GreenFleetFuelPreprocessor
from src.ingestion.schema import GREENFLEET_CANONICAL_SCHEMA, map_dataset_to_canonical_schema


DATASET_PATH = Path("data/raw/fuel/ship_fuel_efficiency.csv")


def test_csv_loading_reads_actual_dataset():
    loader = FuelDataLoader(DATASET_PATH)
    df = loader.load_raw_csv()
    assert isinstance(df, pd.DataFrame)
    assert df.shape[0] > 0
    assert df.shape[1] == 10


def test_column_normalization():
    loader = FuelDataLoader(DATASET_PATH)
    df = loader.load_raw_csv()
    normalized = loader.normalize_columns(df)
    expected = {
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
    assert set(normalized.columns) == expected


def test_schema_mapping_contains_expected_fields():
    schema = GREENFLEET_CANONICAL_SCHEMA
    assert "vessel_id" in schema
    assert "vessel_type" in schema
    assert "route_id" in schema
    assert "distance" in schema
    assert "fuel_type" in schema
    assert "fuel_consumption" in schema
    assert "co2_emissions" in schema
    assert "weather_condition" in schema
    assert "engine_efficiency" in schema


def test_mapping_on_actual_dataset():
    loader = FuelDataLoader(DATASET_PATH)
    raw = loader.load_raw_csv()
    mapped = map_dataset_to_canonical_schema(raw)
    assert mapped["vessel_id"] == "ship_id"
    assert mapped["vessel_type"] == "ship_type"
    assert mapped["route_id"] == "route_id"
    assert mapped["distance"] == "distance"
    assert mapped["fuel_type"] == "fuel_type"
    assert mapped["fuel_consumption"] == "fuel_consumption"
    assert mapped["co2_emissions"] == "co2_emissions"
    assert mapped["weather_condition"] == "weather_conditions"
    assert mapped["engine_efficiency"] == "engine_efficiency"


def test_missing_value_and_duplicate_detection():
    loader = FuelDataLoader(DATASET_PATH)
    raw = loader.load_raw_csv()
    missing = loader.detect_missing_values(raw)
    duplicates = loader.detect_duplicate_rows(raw)
    assert missing["total_missing"] == 0
    assert duplicates == 0


def test_invalid_value_detection():
    loader = FuelDataLoader(DATASET_PATH)
    raw = loader.load_raw_csv()
    invalid = loader.detect_invalid_records(raw)
    assert isinstance(invalid, list)
    assert invalid == []


def test_pipeline_generates_processed_outputs():
    preprocessor = GreenFleetFuelPreprocessor(DATASET_PATH)
    output = preprocessor.process()
    assert output["processed_rows"] == 1440
    assert output["invalid_record_count"] == 0
    assert output["possible_outlier_count"] >= 0
    assert Path(output["clean_csv_path"]).exists()
    assert Path(output["clean_parquet_path"]).exists()
    assert Path(output["schema_path"]).exists()
    assert Path(output["quality_report_json"]).exists()
    assert Path(output["quality_report_md"]).exists()
