import json
import os
from pathlib import Path
from unittest.mock import Mock, patch

import pandas as pd
import pytest
from dotenv import load_dotenv

from src.ingestion.gfw_loader import GFWApiClient, GFWDataPreprocessor

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


def test_gfw_client_uses_bearer_auth_and_default_dataset():
    with patch("requests.Session.get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.raise_for_status.return_value = None
        mock_get.return_value.json.return_value = {
            "entries": [
                {
                    "id": "gfw-123",
                    "name": "Alpha Vessel",
                    "vesselType": "Fishing",
                    "flag": "ESP",
                    "mmsi": "123456789",
                    "imo": "IMO1234567",
                    "speedKnots": 12.4,
                }
            ],
            "total": 1,
        }

        client = GFWApiClient(token="test-token")
        result = client.search_vessels(query="7831410", limit=5)

        assert result["entries"][0]["id"] == "gfw-123"
        assert mock_get.call_args.kwargs["headers"]["Authorization"] == "Bearer test-token"
        assert "public-global-vessel-identity:latest" in mock_get.call_args.kwargs["params"]["datasets[0]"]
        assert "offset" not in mock_get.call_args.kwargs["params"]


def test_gfw_preprocessor_maps_api_payload_to_canonical_schema(tmp_path):
    client = Mock()
    client.search_vessels.return_value = {
        "entries": [
            {
                "id": "gfw-123",
                "name": "Alpha Vessel",
                "vesselType": "Fishing",
                "flag": "ESP",
                "mmsi": "123456789",
                "speedKnots": 12.4,
                "updatedAt": "2025-01-15T00:00:00Z",
            }
        ],
        "total": 1,
    }

    processor = GFWDataPreprocessor(client=client, output_dir=tmp_path)
    output = processor.process(query="7831410", limit=5)

    assert output["processed_rows"] == 1
    assert output["schema_mapping"]["vessel_id"] == "vessel_id"
    assert output["schema_mapping"]["vessel_type"] == "vessel_type"
    assert output["schema_mapping"]["speed"] == "speed_knots"
    assert Path(output["clean_csv_path"]).exists()
    assert Path(output["quality_report_json"]).exists()


@pytest.mark.skipif(not os.getenv("GFW_API_TOKEN"), reason="GFW_API_TOKEN is not configured")
def test_real_gfw_search_query_returns_results():
    client = GFWApiClient()
    result = client.search_vessels(query="7831410", limit=3)

    assert isinstance(result, dict)
    assert "entries" in result or "data" in result
