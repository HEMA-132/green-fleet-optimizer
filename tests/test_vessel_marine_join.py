import pandas as pd
import pytest

from src.ingestion.spatial_temporal_join import VesselMarineJoiner


@pytest.fixture
def vessel_df():
    return pd.DataFrame(
        [
            {
                "vessel_id": "V-1",
                "timestamp": "2024-01-01T00:00:00-05:00",
                "latitude": 10.0,
                "longitude": 20.0,
            },
            {
                "vessel_id": "V-2",
                "timestamp": "2024-01-01T01:00:00Z",
                "latitude": 11.0,
                "longitude": 21.0,
            },
            {
                "vessel_id": "V-3",
                "timestamp": "2024-01-01T02:00:00Z",
                "latitude": 12.0,
                "longitude": 22.0,
            },
        ]
    )


@pytest.fixture
def marine_df():
    return pd.DataFrame(
        [
            {
                "timestamp": "2024-01-01T05:00:00Z",
                "latitude": 10.1,
                "longitude": 20.1,
                "wave_height_m": 1.2,
                "sea_surface_temperature_c": 18.5,
                "source": "open-meteo",
            },
            {
                "timestamp": "2024-01-01T01:00:00Z",
                "latitude": 11.2,
                "longitude": 21.2,
                "wave_height_m": 2.3,
                "sea_surface_temperature_c": 19.0,
                "source": "open-meteo",
            },
            {
                "timestamp": "2024-01-01T02:30:00Z",
                "latitude": 12.0,
                "longitude": 22.0,
                "wave_height_m": 1.8,
                "sea_surface_temperature_c": 20.0,
                "source": "open-meteo",
            },
        ]
    )


def test_timestamp_normalization_to_utc(vessel_df):
    joiner = VesselMarineJoiner()
    normalized = joiner._normalize_timestamp_series(vessel_df["timestamp"])
    assert str(normalized.iloc[0]).endswith("+00:00")
    assert normalized.iloc[0].tzinfo is not None


def test_coordinate_validation_rejects_invalid_values():
    joiner = VesselMarineJoiner()
    with pytest.raises(ValueError):
        joiner._validate_lat_lon(91.0, 0.0)
    with pytest.raises(ValueError):
        joiner._validate_lat_lon(0.0, 181.0)


def test_nearest_temporal_match(vessel_df, marine_df):
    joiner = VesselMarineJoiner(max_time_delta_seconds=3600, max_distance_km=100.0)
    joined = joiner.join(vessel_df, marine_df)
    assert joined["match_status"].tolist()[0] == "matched"
    assert joined["matched_marine_timestamp"].iloc[0] == "2024-01-01T05:00:00+00:00"


def test_nearest_spatial_match(vessel_df, marine_df):
    joiner = VesselMarineJoiner(max_time_delta_seconds=86400, max_distance_km=50.0)
    joined = joiner.join(vessel_df, marine_df)
    assert joined["spatial_distance_km"].iloc[1] >= 0.0
    assert joined["match_status"].iloc[1] == "matched"


def test_tolerance_rejection(vessel_df, marine_df):
    joiner = VesselMarineJoiner(max_time_delta_seconds=60, max_distance_km=1.0)
    joined = joiner.join(vessel_df, marine_df)
    assert joined["match_status"].iloc[2] == "rejected"


def test_missing_coordinates_and_timestamps_are_rejected():
    vessel_df = pd.DataFrame([
        {"vessel_id": "V-4", "timestamp": None, "latitude": 10.0, "longitude": 20.0},
        {"vessel_id": "V-5", "timestamp": "2024-01-01T00:00:00Z", "latitude": None, "longitude": 20.0},
    ])
    marine_df = pd.DataFrame([
        {"timestamp": "2024-01-01T00:00:00Z", "latitude": 10.0, "longitude": 20.0, "wave_height_m": 1.0, "source": "open-meteo"}
    ])
    joiner = VesselMarineJoiner()
    joined = joiner.join(vessel_df, marine_df)
    assert set(joined["match_status"]) == {"rejected"}


def test_duplicate_observations_are_flagged():
    vessel_df = pd.DataFrame([
        {"vessel_id": "V-6", "timestamp": "2024-01-01T00:00:00Z", "latitude": 10.0, "longitude": 20.0},
    ])
    marine_df = pd.DataFrame([
        {"timestamp": "2024-01-01T00:00:00Z", "latitude": 10.0, "longitude": 20.0, "wave_height_m": 1.0, "source": "open-meteo"},
        {"timestamp": "2024-01-01T00:00:00Z", "latitude": 10.0, "longitude": 20.0, "wave_height_m": 1.1, "source": "open-meteo"},
    ])
    joiner = VesselMarineJoiner()
    joined = joiner.join(vessel_df, marine_df)
    assert joined["duplicate_match_count"].iloc[0] == 2


def test_timezone_handling_and_leakage_prevention():
    vessel_df = pd.DataFrame([
        {"vessel_id": "V-7", "timestamp": "2024-01-01T00:00:00-05:00", "latitude": 10.0, "longitude": 20.0},
    ])
    marine_df = pd.DataFrame([
        {"timestamp": "2024-01-01T06:00:00Z", "latitude": 10.0, "longitude": 20.0, "wave_height_m": 1.0, "source": "open-meteo"},
        {"timestamp": "2024-01-01T07:00:00Z", "latitude": 10.0, "longitude": 20.0, "wave_height_m": 1.2, "source": "open-meteo"},
    ])
    joiner = VesselMarineJoiner(max_time_delta_seconds=3600)
    joined = joiner.join(vessel_df, marine_df)
    assert joined["match_status"].iloc[0] == "matched"
    assert joined["time_difference_seconds"].iloc[0] <= 3600
    assert joined["matched_marine_timestamp"].iloc[0].endswith("+00:00")


def test_deterministic_output_and_provenance():
    vessel_df = pd.DataFrame([
        {"vessel_id": "V-8", "timestamp": "2024-01-01T00:00:00Z", "latitude": 10.0, "longitude": 20.0},
        {"vessel_id": "V-8", "timestamp": "2024-01-01T00:10:00Z", "latitude": 10.2, "longitude": 20.2},
    ])
    marine_df = pd.DataFrame([
        {"timestamp": "2024-01-01T00:00:00Z", "latitude": 10.0, "longitude": 20.0, "wave_height_m": 1.0, "source": "open-meteo"},
        {"timestamp": "2024-01-01T00:10:00Z", "latitude": 10.1, "longitude": 20.1, "wave_height_m": 1.2, "source": "open-meteo"},
    ])
    joiner = VesselMarineJoiner(max_time_delta_seconds=86400, max_distance_km=100.0)
    joined = joiner.join(vessel_df, marine_df)
    assert joined["vessel_id"].tolist() == ["V-8", "V-8"]
    assert joined["provenance"].iloc[0].startswith("join:")
