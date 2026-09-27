# green-fleet-optimizer

GreenFleet Optimizer is a data-first, modular project for ingesting, validating, and normalizing maritime operations data before any optimization or ML work begins.

## Project status

- Real fuel CSV ingestion and validation are implemented and tested.
- The canonical schema is shared across source-specific loaders.
- Global Fishing Watch (GFW) vessel identity ingestion is implemented and validated against the live API contract.
- Open-Meteo Marine ingestion is implemented and tested.
- NOAA MarineCadastre AIS broadcast ingestion is implemented as a streaming Zstandard CSV pipeline.
- The current production stage is the vessel-to-marine spatial-temporal join, which prepares the real observation layer for downstream modeling without inventing missing data.

## NOAA AIS ingestion

The AIS loader in [src/ingestion/ais_loader.py](src/ingestion/ais_loader.py) reads the provided compressed source as a stream. It does not extract or modify the raw archive, and it writes only cleaned output and quality metadata under `data/processed/ais/`.

The loader uses bounded CSV chunks and a temporary disk-backed index for duplicate observations. It normalizes the observed NOAA fields, converts timestamps to UTC, validates coordinates, removes invalid core observations, and records the source schema and quality statistics.

## Join stage

The project now includes a conservative vessel-to-marine join layer in [src/ingestion/spatial_temporal_join.py](src/ingestion/spatial_temporal_join.py). It matches valid vessel observations to the nearest marine environment record only when both timestamps and coordinates are present and fall within configured tolerances.

Key rules:

- timestamps are normalized to UTC before comparison;
- latitude/longitude values are validated before matching;
- matches are rejected when the temporal gap or geographic distance exceeds configured limits;
- provenance metadata is preserved so every row is auditable;
- no synthetic trajectory, speed, or marine values are introduced.

Example usage:

```python
import pandas as pd
from src.ingestion.spatial_temporal_join import VesselMarineJoiner

vessel_df = pd.DataFrame([
   {"vessel_id": "V-1", "timestamp": "2024-01-01T00:00:00-05:00", "latitude": 10.0, "longitude": 20.0}
])
marine_df = pd.DataFrame([
   {"timestamp": "2024-01-01T06:00:00Z", "latitude": 10.0, "longitude": 20.0, "wave_height_m": 1.0, "source": "open-meteo"}
])

joined = VesselMarineJoiner(max_time_delta_seconds=3600, max_distance_km=50.0).join(vessel_df, marine_df)
print(joined[["vessel_id", "match_status", "time_difference_seconds", "spatial_distance_km"]])
```

## Local environment setup

1. Create or activate the project virtual environment.
2. Ensure the project dependencies are installed from `requirements.txt`.
3. Add a `.env` file at the project root with the following value:

   GFW_API_TOKEN=your_token_here

4. Do not print, log, or commit the token itself. Keep it local to the environment.

## GFW API access requirements

This project uses the official Global Fishing Watch API documentation and bearer-token authentication.

- Auth header: `Authorization: Bearer <token>`
- Base URL: `https://gateway.api.globalfishingwatch.org/v3`
- Dataset used by default: `public-global-vessel-identity:latest`
- Token source: `.env` using `python-dotenv`

Official docs referenced for implementation:
- https://globalfishingwatch.org/our-apis/documentation
- https://globalfishingwatch.org/our-apis/documentation/docs/authentication
- https://globalfishingwatch.org/our-apis/documentation/docs/v3/vessels

## Data provenance and usage rules

- Raw files remain untouched under `data/raw/`.
- Processed outputs are written under `data/processed/`.
- API responses are stored under `data/raw/gfw/` without manual editing.
- Any publications or derivative analysis must attribute Global Fishing Watch as required by the API terms of use.

## Example usage

```bash
python -c "from src.ingestion.gfw_loader import GFWApiClient; c=GFWApiClient(); print(c.search_vessels('7831410', limit=3))"
```

This is a small, controlled query used to validate token access and response structure before broader dataset pulls.

## Application Layer

### Architecture

```text
Data/Ingestion
    ↓
Feature/Modeling Dataset
    ↓
Frozen Optimization Engine
    ↓
Application Service
    ↓
Streamlit UI
```

### Application Files

- `src/application/service.py`: Service API exposing option metadata, strict context validation, and optimization execution.
- `src/application/app.py`: Interactive Streamlit web interface for operating context selection and side-by-side optimization comparison.
- `src/application/__init__.py`: Application package exports.

### Service Overview

The `FleetOptimizationService` encapsulates context options discovery (`get_available_options()`), strict input validation (`validate_context(...)`), and dual optimizer execution (`run_optimization(...)`).

### Fixed-Context Optimization Formulation

- **Optimization Decision Variables**: `route_id`, `fuel_type`
- **Fixed Operating Context**: `ship_type`, `month`, `weather_conditions`, `engine_efficiency`
- **Derived Variable**: `distance` is derived strictly from the observed median distance for the selected route. The optimizer cannot independently alter distance.
- **Objective Function**: $0.7 \times \text{normalized predicted fuel} + 0.3 \times \text{normalized predicted CO}_2$ (Minimize).

### Data Integrity Note

Marine observations are NOT joined to fuel records because fuel records lack timestamp and geographic keys required for a defensible join. Marine records remain separate contextual/observational data.

### Verified Scientific Conclusion

> "QPSO matched the classical baseline on the optimization objective and was faster in the tested benchmark, but the experiment does not establish quantum advantage."

### Local Launch Command

```powershell
Set-Location "D:\SOFTWARE\green-fleet-optimizer"
.\.venv\Scripts\streamlit.exe run .\src\application\app.py
```

### Test Command

```powershell
Set-Location "D:\SOFTWARE\green-fleet-optimizer"
.\.venv\Scripts\python.exe -m pytest tests/test_application.py tests/test_optimization.py
```

