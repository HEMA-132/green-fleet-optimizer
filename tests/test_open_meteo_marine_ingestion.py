import json
from pathlib import Path
from unittest.mock import Mock, patch

import pandas as pd
import pytest

from src.ingestion.open_meteo_marine_loader import (OpenMeteoMarineClient,
                                                    OpenMeteoMarinePreprocessor)


@pytest.fixture
def sample_payload():
    return {
        "latitude": 41.0,
        "longitude": -8.0,
        "timezone": "auto",
        "hourly": {
            "time": ["2026-09-25T00:00", "2026-09-25T01:00"],
            "wave_height": [1.2, 1.6],
            "wave_direction": [120.0, 125.0],
            "wave_period": [7.2, 7.5],
            "wind_wave_height": [1.0, 1.1],
            "wind_wave_direction": [110.0, 118.0],
            "swell_wave_height": [0.8, 0.9],
            "swell_wave_direction": [100.0, 105.0],
            "ocean_current_velocity": [0.35, 0.42],
            "ocean_current_direction": [220.0, 230.0],
            "sea_surface_temperature": [18.1, 18.5],
        },
        "hourly_units": {
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
        },
    }


def test_successful_api_ingestion_and_schema_normalization(sample_payload):
    with patch("requests.Session.get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.raise_for_status.return_value = None
        mock_get.return_value.json.return_value = sample_payload

        client = OpenMeteoMarineClient(timeout=15)
        result = client.fetch_hourly_data(
            latitude=41.0,
            longitude=-8.0,
            start_date="2026-09-25",
            end_date="2026-09-25",
            variables=[
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
            ],
        )

        assert result["latitude"] == 41.0
        assert result["hourly"]["wave_height"][0] == 1.2
        assert "wave_height" in result["hourly"]
        assert mock_get.call_args.kwargs["params"]["latitude"] == 41.0
        assert mock_get.call_args.kwargs["params"]["longitude"] == -8.0

    mocked_client = Mock()
    mocked_client.fetch_hourly_data.return_value = sample_payload
    cleaned_client = OpenMeteoMarineClient(timeout=15)
    cleaned_client.fetch_hourly_data = mocked_client.fetch_hourly_data

    processor = OpenMeteoMarinePreprocessor(client=cleaned_client, output_dir="data/processed/marine")
    output = processor.process(
        latitude=41.0,
        longitude=-8.0,
        start_date="2026-09-25",
        end_date="2026-09-25",
        variables=["wave_height", "wave_direction", "sea_surface_temperature"],
    )

    assert output["processed_rows"] == 2
    assert "timestamp" in output["dataframe"].columns
    assert "wave_height_m" in output["dataframe"].columns
    assert "sea_surface_temperature_c" in output["dataframe"].columns
    assert Path(output["clean_csv_path"]).exists()
    assert Path(output["quality_report_json"]).exists()
    assert Path(output["quality_report_md"]).exists()


def test_missing_variables_raise_error(sample_payload):
    with patch("requests.Session.get") as mock_get:
        incomplete = {"latitude": 41.0, "longitude": -8.0, "hourly": {"time": ["2026-09-25T00:00"]}}
        mock_get.return_value.status_code = 200
        mock_get.return_value.raise_for_status.return_value = None
        mock_get.return_value.json.return_value = incomplete

        client = OpenMeteoMarineClient()
        with pytest.raises(ValueError, match="Missing required hourly variables"):
            client.fetch_hourly_data(
                latitude=41.0,
                longitude=-8.0,
                start_date="2026-09-25",
                end_date="2026-09-25",
                variables=["wave_height", "sea_surface_temperature"],
            )


def test_malformed_response_raises_error():
    with patch("requests.Session.get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.raise_for_status.return_value = None
        mock_get.return_value.json.return_value = {"foo": "bar"}

        client = OpenMeteoMarineClient()
        with pytest.raises(ValueError, match="Missing required marine response fields"):
            client.fetch_hourly_data(
                latitude=41.0,
                longitude=-8.0,
                start_date="2026-09-25",
                end_date="2026-09-25",
                variables=["wave_height"],
            )


def test_null_values_and_duplicate_timestamps_are_flagged():
    payload = {
        "latitude": 41.0,
        "longitude": -8.0,
        "timezone": "auto",
        "hourly": {
            "time": ["2026-09-25T00:00", "2026-09-25T00:00", "2026-09-25T02:00"],
            "wave_height": [1.2, None, 1.7],
            "wave_direction": [120.0, 125.0, None],
            "wave_period": [7.1, 7.1, 7.4],
        },
        "hourly_units": {"wave_height": "m", "wave_direction": "deg", "wave_period": "s"},
    }

    with patch("requests.Session.get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.raise_for_status.return_value = None
        mock_get.return_value.json.return_value = payload

        client = OpenMeteoMarineClient()
        processor = OpenMeteoMarinePreprocessor(client=client, output_dir="data/processed/marine")
        result = processor.process(
            latitude=41.0,
            longitude=-8.0,
            start_date="2026-09-25",
            end_date="2026-09-25",
            variables=["wave_height", "wave_direction", "wave_period"],
        )

        assert result["null_value_count"] >= 1
        assert result["duplicate_timestamps"] >= 1
        assert result["quality_record"]["duplicate_timestamp_count"] >= 1


def test_invalid_coordinates_raise_error():
    client = OpenMeteoMarineClient()
    with pytest.raises(ValueError, match="latitude must be between"):
        client.fetch_hourly_data(91.0, -8.0, "2026-09-25", "2026-09-25", ["wave_height"])

    with pytest.raises(ValueError, match="longitude must be between"):
        client.fetch_hourly_data(41.0, 181.0, "2026-09-25", "2026-09-25", ["wave_height"])


def test_http_errors_and_timeouts_are_handled():
    client = OpenMeteoMarineClient()

    with patch("requests.Session.get", side_effect=TimeoutError):
        with pytest.raises(RuntimeError, match="Open-Meteo API request failed"):
            client.fetch_hourly_data(41.0, -8.0, "2026-09-25", "2026-09-25", ["wave_height"])

    with patch("requests.Session.get") as mock_get:
        mock_get.return_value.status_code = 500
        mock_get.return_value.raise_for_status.side_effect = Exception("server error")
        with pytest.raises(RuntimeError, match="Open-Meteo API request failed"):
            client.fetch_hourly_data(41.0, -8.0, "2026-09-25", "2026-09-25", ["wave_height"])


def test_schema_mapping_and_unit_metadata():
    processor = OpenMeteoMarinePreprocessor(client=Mock(), output_dir="data/processed/marine")
    schema = processor.schema_definition()
    assert "timestamp" in schema
    assert "latitude" in schema
    assert "longitude" in schema
    assert "wave_height_m" in schema
    assert "ocean_current_velocity_m_s" in schema
    assert "sea_surface_temperature_c" in schema

    units = processor.unit_metadata()
    assert "wave_height" in units
    assert units["wave_height"] == "m"
    assert units["ocean_current_velocity"] == "m/s"


def test_raw_response_preservation():
    payload = {
        "latitude": 41.0,
        "longitude": -8.0,
        "hourly": {"time": ["2026-09-25T00:00"], "wave_height": [1.3]},
        "hourly_units": {"wave_height": "m"},
    }

    client = Mock()
    client.fetch_hourly_data.return_value = payload
    processor = OpenMeteoMarinePreprocessor(client=client, output_dir="data/processed/marine")
    output = processor.process(
        latitude=41.0,
        longitude=-8.0,
        start_date="2026-09-25",
        end_date="2026-09-25",
        variables=["wave_height"],
    )

    assert Path(output["raw_response_path"]).exists()
    saved = json.loads(Path(output["raw_response_path"]).read_text(encoding="utf-8"))
    assert saved["hourly"]["wave_height"][0] == 1.3
