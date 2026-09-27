# Global Fishing Watch Data Quality Report

- Dataset: gfw_vessel_identity
- Query: 7831410
- Dataset target: public-global-vessel-identity:latest
- Row count: 1

## Provenance

- Project repo: https://github.com/HEMA-132/green-fleet-optimizer.git
- API docs: https://globalfishingwatch.org/our-apis/documentation
- Source note: Global Fishing Watch vessel-identity API accessed via official v3 endpoints and bearer-token authentication.

## Schema mapping

{
  "vessel_id": "vessel_id",
  "vessel_type": "vessel_type",
  "route_id": null,
  "period": "updated_at",
  "distance": null,
  "fuel_type": null,
  "fuel_consumption": null,
  "co2_emissions": null,
  "weather_condition": null,
  "engine_efficiency": null,
  "speed": "speed_knots"
}

## Missing values

{
  "vessel_id": 0,
  "vessel_type": 1,
  "name": 0,
  "flag": 0,
  "mmsi": 0,
  "imo": 0,
  "speed_knots": 1,
  "updated_at": 1
}

## Transformations performed
- Requested vessel identity data from the official GFW v3 API
- Stored the raw API payload without modifying the source response
- Normalized the vessel payload into a tabular dataset
- Mapped fields into the GreenFleet canonical schema convention
- Persisted cleaned CSV, Parquet, and quality-report outputs
