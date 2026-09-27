# Open-Meteo Marine Data Quality Report

- Dataset: open_meteo_marine
- Source API: https://marine-api.open-meteo.com/v1/marine
- Latitude: 41.0
- Longitude: -8.0
- Date range: 2026-09-25 to 2026-09-25
- Processed row count: 1

## Schema

{
  "timestamp": {
    "type": "datetime",
    "unit": "ISO8601",
    "description": "Observation timestamp in local time."
  },
  "latitude": {
    "type": "float",
    "unit": "degrees",
    "description": "Latitude of the observation."
  },
  "longitude": {
    "type": "float",
    "unit": "degrees",
    "description": "Longitude of the observation."
  },
  "source": {
    "type": "string",
    "unit": "n/a",
    "description": "Source system name."
  },
  "wave_height_m": {
    "type": "float",
    "unit": "m",
    "description": "Wave height in metres."
  },
  "wave_direction_deg": {
    "type": "float",
    "unit": "deg",
    "description": "Mean wave direction in degrees from north."
  },
  "wave_period_s": {
    "type": "float",
    "unit": "s",
    "description": "Wave period in seconds."
  },
  "wind_wave_height_m": {
    "type": "float",
    "unit": "m",
    "description": "Wind wave height in metres."
  },
  "wind_wave_direction_deg": {
    "type": "float",
    "unit": "deg",
    "description": "Wind wave direction in degrees from north."
  },
  "swell_wave_height_m": {
    "type": "float",
    "unit": "m",
    "description": "Swell wave height in metres."
  },
  "swell_wave_direction_deg": {
    "type": "float",
    "unit": "deg",
    "description": "Swell wave direction in degrees from north."
  },
  "ocean_current_velocity_m_s": {
    "type": "float",
    "unit": "m/s",
    "description": "Ocean current velocity in metres per second."
  },
  "ocean_current_direction_deg": {
    "type": "float",
    "unit": "deg",
    "description": "Ocean current direction in degrees from north."
  },
  "sea_surface_temperature_c": {
    "type": "float",
    "unit": "\u00b0C",
    "description": "Sea surface temperature in Celsius."
  }
}

## Missing values

{
  "timestamp": 0,
  "latitude": 0,
  "longitude": 0,
  "source": 0,
  "wave_height_m": 0,
  "wave_direction_deg": 1,
  "wave_period_s": 1,
  "wind_wave_height_m": 1,
  "wind_wave_direction_deg": 1,
  "swell_wave_height_m": 1,
  "swell_wave_direction_deg": 1,
  "ocean_current_velocity_m_s": 1,
  "ocean_current_direction_deg": 1,
  "sea_surface_temperature_c": 1
}

## Duplicate timestamps

0

## Invalid values

0

## Unit conversions

[]

## Transformations performed
- Fetched hourly marine observations from the official Open-Meteo Marine API.
- Preserved the original raw JSON payload without modifying the source response.
- Validated required hourly fields and coordinate bounds.
- Normalized marine variables into a tabular schema keyed by timestamp and location.
- Recorded nulls, duplicate timestamps, invalid values, and unit conversions in quality metadata.
- Persisted cleaned CSV, Parquet, schema, and quality-report artifacts.
