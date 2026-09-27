# GreenFleet Fuel Data Quality Report

- Dataset name: ship_fuel_efficiency
- Source path: data\raw\fuel\ship_fuel_efficiency.csv
- Original row count: 1440
- Processed row count: 1440
- Column count: 10

## Data lineage

RAW CSV → LOAD → SCHEMA NORMALIZATION → TYPE CONVERSION → VALIDATION → CLEANING → CANONICAL GREENFLEET SCHEMA → PROCESSED DATA

## Source provenance

- Project repository URL: https://github.com/HEMA-132/green-fleet-optimizer.git
- Dataset repository URL: None
- Dataset note: No explicit dataset metadata, notebook, or README section documenting the original source repository or units was found in the project contents.

## Unit verification

No units were explicitly documented in the project README, notebook, or source metadata. The following statuses reflect verified evidence rather than inference.

- Confirmed units: {}
- Inferred units: {
  "distance": {
    "value": "likely nautical miles",
    "basis": "domain inference only; not explicitly documented in project files"
  },
  "fuel_consumption": {
    "value": "likely liters",
    "basis": "domain inference only; not explicitly documented in project files"
  },
  "co2_emissions": {
    "value": "likely kg CO2",
    "basis": "domain inference only; not explicitly documented in project files"
  },
  "engine_efficiency": {
    "value": "likely percent",
    "basis": "domain inference only; not explicitly documented in project files"
  }
}
- Unknown units: {
  "distance": "No explicit unit documentation was found in the README or dataset metadata.",
  "fuel_consumption": "No explicit unit documentation was found in the README or dataset metadata.",
  "co2_emissions": "No explicit unit documentation was found in the README or dataset metadata.",
  "engine_efficiency": "No explicit unit documentation was found in the README or dataset metadata."
}
- Verification note: These units are not confirmed by source documentation; they are only inferred from domain conventions and data semantics.

## Column descriptions
- ship_id: Unique vessel or asset identifier.
- ship_type: Operational source field
- route_id: Operational source field
- month: Operational source field
- distance: Operational source field
- fuel_type: Operational source field
- fuel_consumption: Operational source field
- co2_emissions: Operational source field
- weather_conditions: Operational source field
- engine_efficiency: Operational source field

## Missing-value statistics
{
  "missing_by_column": {
    "ship_id": 0,
    "ship_type": 0,
    "route_id": 0,
    "month": 0,
    "distance": 0,
    "fuel_type": 0,
    "fuel_consumption": 0,
    "co2_emissions": 0,
    "weather_conditions": 0,
    "engine_efficiency": 0
  },
  "total_missing": 0,
  "missing_percent": 0.0
}

## Duplicate count
0

## Invalid record count
0

## Possible outlier count
234

## Categorical distributions
{
  "ship_id": {
    "NG001": 12,
    "NG002": 12,
    "NG003": 12,
    "NG004": 12,
    "NG005": 12,
    "NG006": 12,
    "NG007": 12,
    "NG008": 12,
    "NG009": 12,
    "NG010": 12,
    "NG011": 12,
    "NG012": 12,
    "NG013": 12,
    "NG014": 12,
    "NG015": 12,
    "NG016": 12,
    "NG017": 12,
    "NG018": 12,
    "NG019": 12,
    "NG020": 12,
    "NG021": 12,
    "NG022": 12,
    "NG023": 12,
    "NG024": 12,
    "NG025": 12,
    "NG026": 12,
    "NG027": 12,
    "NG028": 12,
    "NG029": 12,
    "NG030": 12,
    "NG031": 12,
    "NG032": 12,
    "NG033": 12,
    "NG034": 12,
    "NG035": 12,
    "NG036": 12,
    "NG037": 12,
    "NG038": 12,
    "NG039": 12,
    "NG040": 12,
    "NG041": 12,
    "NG042": 12,
    "NG043": 12,
    "NG044": 12,
    "NG045": 12,
    "NG046": 12,
    "NG047": 12,
    "NG048": 12,
    "NG049": 12,
    "NG050": 12,
    "NG051": 12,
    "NG052": 12,
    "NG053": 12,
    "NG054": 12,
    "NG055": 12,
    "NG056": 12,
    "NG057": 12,
    "NG058": 12,
    "NG059": 12,
    "NG060": 12,
    "NG061": 12,
    "NG062": 12,
    "NG063": 12,
    "NG064": 12,
    "NG065": 12,
    "NG066": 12,
    "NG067": 12,
    "NG068": 12,
    "NG069": 12,
    "NG070": 12,
    "NG071": 12,
    "NG072": 12,
    "NG073": 12,
    "NG074": 12,
    "NG075": 12,
    "NG076": 12,
    "NG077": 12,
    "NG078": 12,
    "NG079": 12,
    "NG080": 12,
    "NG081": 12,
    "NG082": 12,
    "NG083": 12,
    "NG084": 12,
    "NG085": 12,
    "NG086": 12,
    "NG087": 12,
    "NG088": 12,
    "NG089": 12,
    "NG090": 12,
    "NG091": 12,
    "NG092": 12,
    "NG093": 12,
    "NG094": 12,
    "NG095": 12,
    "NG096": 12,
    "NG097": 12,
    "NG098": 12,
    "NG099": 12,
    "NG100": 12,
    "NG101": 12,
    "NG102": 12,
    "NG103": 12,
    "NG104": 12,
    "NG105": 12,
    "NG106": 12,
    "NG107": 12,
    "NG108": 12,
    "NG109": 12,
    "NG110": 12,
    "NG111": 12,
    "NG112": 12,
    "NG113": 12,
    "NG114": 12,
    "NG115": 12,
    "NG116": 12,
    "NG117": 12,
    "NG118": 12,
    "NG119": 12,
    "NG120": 12
  },
  "ship_type": {
    "Oil Service Boat": 408,
    "Tanker Ship": 408,
    "Surfer Boat": 324,
    "Fishing Trawler": 300
  },
  "route_id": {
    "Port Harcourt-Lagos": 389,
    "Lagos-Apapa": 388,
    "Escravos-Lagos": 369,
    "Warri-Bonny": 294
  },
  "month": {
    "January": 120,
    "February": 120,
    "March": 120,
    "April": 120,
    "May": 120,
    "June": 120,
    "July": 120,
    "August": 120,
    "September": 120,
    "October": 120,
    "November": 120,
    "December": 120
  },
  "fuel_type": {
    "Diesel": 899,
    "HFO": 541
  },
  "weather_conditions": {
    "Calm": 516,
    "Stormy": 462,
    "Moderate": 462
  }
}

## Numerical summar statistics
{
  "distance": {
    "count": 1440.0,
    "mean": 151.7534,
    "std": 108.4722,
    "min": 20.08,
    "25%": 79.0025,
    "50%": 123.465,
    "75%": 180.78,
    "max": 498.55
  },
  "fuel_consumption": {
    "count": 1440.0,
    "mean": 4844.2465,
    "std": 4892.3528,
    "min": 237.88,
    "25%": 1837.9625,
    "50%": 3060.88,
    "75%": 4870.675,
    "max": 24648.52
  },
  "co2_emissions": {
    "count": 1440.0,
    "mean": 13365.4549,
    "std": 13567.6501,
    "min": 615.68,
    "25%": 4991.485,
    "50%": 8423.255,
    "75%": 13447.12,
    "max": 71871.21
  },
  "engine_efficiency": {
    "count": 1440.0,
    "mean": 82.5829,
    "std": 7.1583,
    "min": 70.01,
    "25%": 76.255,
    "50%": 82.775,
    "75%": 88.8625,
    "max": 94.98
  }
}

## Detected units
{
  "confirmed_units": {},
  "inferred_units": {
    "distance": {
      "value": "likely nautical miles",
      "basis": "domain inference only; not explicitly documented in project files"
    },
    "fuel_consumption": {
      "value": "likely liters",
      "basis": "domain inference only; not explicitly documented in project files"
    },
    "co2_emissions": {
      "value": "likely kg CO2",
      "basis": "domain inference only; not explicitly documented in project files"
    },
    "engine_efficiency": {
      "value": "likely percent",
      "basis": "domain inference only; not explicitly documented in project files"
    }
  },
  "unknown_units": {
    "distance": "No explicit unit documentation was found in the README or dataset metadata.",
    "fuel_consumption": "No explicit unit documentation was found in the README or dataset metadata.",
    "co2_emissions": "No explicit unit documentation was found in the README or dataset metadata.",
    "engine_efficiency": "No explicit unit documentation was found in the README or dataset metadata."
  },
  "verification_note": "These units are not confirmed by source documentation; they are only inferred from domain conventions and data semantics."
}

## Confirmed vs inferred unit status
{
  "confirmed_units": {},
  "inferred_units": {
    "distance": {
      "value": "likely nautical miles",
      "basis": "domain inference only; not explicitly documented in project files"
    },
    "fuel_consumption": {
      "value": "likely liters",
      "basis": "domain inference only; not explicitly documented in project files"
    },
    "co2_emissions": {
      "value": "likely kg CO2",
      "basis": "domain inference only; not explicitly documented in project files"
    },
    "engine_efficiency": {
      "value": "likely percent",
      "basis": "domain inference only; not explicitly documented in project files"
    }
  },
  "unknown_units": {
    "distance": "No explicit unit documentation was found in the README or dataset metadata.",
    "fuel_consumption": "No explicit unit documentation was found in the README or dataset metadata.",
    "co2_emissions": "No explicit unit documentation was found in the README or dataset metadata.",
    "engine_efficiency": "No explicit unit documentation was found in the README or dataset metadata."
  },
  "verification_note": "These units are not confirmed by source documentation; they are only inferred from domain conventions and data semantics."
}

## Transformations performed
- Loaded raw CSV without modifying source file
- Normalized all columns to snake_case
- Cast numeric columns to pandas numeric types
- Standardized empty strings to missing values
- Normalized categorical labels to canonical values
- Detected missing values and duplicates
- Flagged invalid records using domain constraints
- Separated invalid records from possible outliers
- Mapped source columns to GreenFleet canonical schema

## GreenFleet schema mapping
{
  "vessel_id": "ship_id",
  "vessel_type": "ship_type",
  "route_id": "route_id",
  "period": "month",
  "distance": "distance",
  "fuel_type": "fuel_type",
  "fuel_consumption": "fuel_consumption",
  "co2_emissions": "co2_emissions",
  "weather_condition": "weather_conditions",
  "engine_efficiency": "engine_efficiency",
  "cargo_capacity": null,
  "cargo_load": null,
  "speed": null,
  "wind_speed": null,
  "wave_height": null,
  "current_speed": null
}

## Fields unavailable
[
  "cargo_capacity",
  "cargo_load",
  "speed",
  "wind_speed",
  "wave_height",
  "current_speed"
]

## Known limitations
- No vessel-specific cargo capacity or load fields are present.
- No weather API or ocean conditions are available in this dataset.
- No vessel speed or current data are available in the source CSV.

## Future data requirements
- IMO DCS reporting data for fleet-level emissions and fuel usage.
- Vessel metadata including cargo capacity, speed, and design characteristics.
- AIS or route telemetry for time-stamped vessel movement.
- Weather and ocean-condition APIs for wind, wave, and current values.