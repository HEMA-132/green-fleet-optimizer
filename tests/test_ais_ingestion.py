import csv
import json
from pathlib import Path

import zstandard as zstd

from src.ingestion.ais_loader import AISDataLoader


COLUMNS = [
    "mmsi", "base_date_time", "longitude", "latitude", "sog", "cog", "heading",
    "vessel_name", "imo", "call_sign", "vessel_type", "status", "length", "width",
    "draft", "cargo", "transceiver",
]


def write_compressed_csv(path: Path, rows: list[dict[str, str]]) -> None:
    payload = __import__("io").StringIO()
    writer = csv.DictWriter(payload, fieldnames=COLUMNS)
    writer.writeheader()
    writer.writerows(rows)
    path.write_bytes(zstd.ZstdCompressor().compress(payload.getvalue().encode("utf-8")))


def test_streaming_ais_ingestion_normalizes_and_reports_quality(tmp_path):
    raw_path = tmp_path / "ais.tgz"
    write_compressed_csv(
        raw_path,
        [
            {
                "mmsi": "001234567", "base_date_time": "2025-01-08 00:00:00", "longitude": "-122.4",
                "latitude": "47.6", "sog": "4.6", "cog": "155.5", "heading": "150", "vessel_name": "TEST",
                "imo": "", "call_sign": "CALL", "vessel_type": "70", "status": "0", "length": "10",
                "width": "3", "draft": "", "cargo": "", "transceiver": "B",
            },
            {
                "mmsi": "001234567", "base_date_time": "2025-01-08 00:00:00", "longitude": "-122.4",
                "latitude": "47.6", "sog": "4.6", "cog": "155.5", "heading": "150", "vessel_name": "TEST",
                "imo": "", "call_sign": "CALL", "vessel_type": "70", "status": "0", "length": "10",
                "width": "3", "draft": "", "cargo": "", "transceiver": "B",
            },
            {
                "mmsi": "001234568", "base_date_time": "2025-01-08 00:01:00", "longitude": "181",
                "latitude": "47.7", "sog": "0", "cog": "", "heading": "", "vessel_name": "BAD",
                "imo": "", "call_sign": "", "vessel_type": "", "status": "", "length": "",
                "width": "", "draft": "", "cargo": "", "transceiver": "B",
            },
        ],
    )

    result = AISDataLoader(raw_path, tmp_path / "processed", chunksize=2).process()
    quality = result["quality_record"]

    assert quality["raw_row_count"] == 3
    assert quality["processed_row_count"] == 1
    assert quality["unique_vessel_count"] == 1
    assert quality["duplicate_observation_count"] == 1
    assert quality["invalid_coordinate_rows"] == 1
    assert quality["timestamp_range_utc"] == ["2025-01-08T00:00:00Z", "2025-01-08T00:00:00Z"]
    assert quality["missing_values_by_raw_column"]["imo"] == 3
    assert Path(result["clean_csv_path"]).stat().st_size > 0
    assert json.loads(Path(result["schema_path"]).read_text(encoding="utf-8"))["timestamp"]["unit"] == "UTC"


def test_non_zstandard_input_is_rejected(tmp_path):
    raw_path = tmp_path / "not-ais.csv"
    raw_path.write_text("mmsi,base_date_time\n1,2025-01-08 00:00:00\n", encoding="utf-8")

    try:
        AISDataLoader(raw_path, tmp_path / "processed").process()
    except ValueError as error:
        assert "Zstandard" in str(error)
    else:
        raise AssertionError("Expected non-Zstandard input to be rejected")


def test_create_sample_keeps_requested_schema_and_valid_rows(tmp_path):
    raw_path = tmp_path / "ais.tgz"
    write_compressed_csv(
        raw_path,
        [
            {
                "mmsi": "123", "base_date_time": "2025-01-08 00:00:00", "longitude": "20",
                "latitude": "10", "sog": "1", "cog": "2", "heading": "3", "vessel_type": "70",
                "length": "10", "width": "3", "draft": "1", "vessel_name": "", "imo": "",
                "call_sign": "", "status": "", "cargo": "", "transceiver": "B",
            },
            {
                "mmsi": "", "base_date_time": "bad", "longitude": "181", "latitude": "10",
                "sog": "", "cog": "", "heading": "", "vessel_type": "", "length": "", "width": "",
                "draft": "", "vessel_name": "", "imo": "", "call_sign": "", "status": "", "cargo": "", "transceiver": "B",
            },
        ],
    )

    output = tmp_path / "ais_sample.csv"
    result = AISDataLoader(raw_path, chunksize=2).create_sample(output, max_rows=10_000)
    sample = __import__("pandas").read_csv(output)

    assert result["sampled_rows"] == 1
    assert sample.columns.tolist() == AISDataLoader.SAMPLE_COLUMNS
    assert sample["latitude"].between(-90, 90).all()
    assert sample["longitude"].between(-180, 180).all()
    assert sample["base_date_time"].iloc[0].endswith("Z")


def test_query_points_from_processed_sample_are_deterministic(tmp_path):
    input_path = Path("data/processed/ais/ais_sample.csv")
    first_output = tmp_path / "query_points_first.csv"
    second_output = tmp_path / "query_points_second.csv"

    first = AISDataLoader.create_query_points(input_path, first_output, target_points=200)
    second = AISDataLoader.create_query_points(input_path, second_output, target_points=200)

    assert first["original_rows"] == 10_000
    assert first["valid_rows"] == 10_000
    assert first["query_point_count"] == 200
    assert first["unique_vessels"] > 0
    assert {key: value for key, value in first.items() if key != "output_path"} == {
        key: value for key, value in second.items() if key != "output_path"
    }
    assert first_output.read_bytes() == second_output.read_bytes()
    assert __import__("pandas").read_csv(first_output).columns.tolist() == [
        "mmsi", "timestamp", "latitude", "longitude", "sog"
    ]
