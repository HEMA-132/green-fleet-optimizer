"""Build a leakage-safe fuel prediction dataset from processed source data."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
FUEL_PATH = PROJECT_ROOT / "data/processed/fuel/greenfleet_fuel_clean.csv"
MARINE_PATH = PROJECT_ROOT / "data/processed/marine/historical_marine_observations.csv"
AIS_QUERY_POINTS_PATH = PROJECT_ROOT / "data/processed/ais/ais_marine_query_points.csv"
OUTPUT_DIR = PROJECT_ROOT / "data/processed/modeling"
OUTPUT_PATH = OUTPUT_DIR / "fuel_prediction_dataset.csv"
DATA_DICTIONARY_PATH = OUTPUT_DIR / "data_dictionary.json"

FUEL_REQUIRED_COLUMNS = {
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
TARGET_COLUMNS = ["fuel_consumption", "co2_emissions"]
MONTH_NUMBERS = {
    month: number
    for number, month in enumerate(
        [
            "January",
            "February",
            "March",
            "April",
            "May",
            "June",
            "July",
            "August",
            "September",
            "October",
            "November",
            "December",
        ],
        start=1,
    )
}


def _require_columns(frame: pd.DataFrame, required: set[str], dataset_name: str) -> None:
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"{dataset_name} is missing required columns: {missing}")


def _data_dictionary() -> dict[str, dict[str, str]]:
    return {
        "ship_id": {
            "data_type": "string",
            "role": "identifier",
            "source_dataset": "fuel",
            "description": "Fuel-source vessel identifier; not mapped to marine MMSI values.",
        },
        "ship_type": {
            "data_type": "categorical",
            "role": "feature",
            "source_dataset": "fuel",
            "description": "Fuel-source vessel category.",
        },
        "route_id": {
            "data_type": "categorical",
            "role": "metadata",
            "source_dataset": "fuel",
            "description": "Fuel-source route label retained as operational metadata.",
        },
        "month": {
            "data_type": "categorical",
            "role": "feature",
            "source_dataset": "fuel",
            "description": "Fuel-source reporting month.",
        },
        "distance": {
            "data_type": "float",
            "role": "feature",
            "source_dataset": "fuel",
            "description": "Reported voyage or period distance.",
        },
        "fuel_type": {
            "data_type": "categorical",
            "role": "feature",
            "source_dataset": "fuel",
            "description": "Reported fuel type.",
        },
        "weather_conditions": {
            "data_type": "categorical",
            "role": "feature",
            "source_dataset": "fuel",
            "description": "Reported weather category.",
        },
        "engine_efficiency": {
            "data_type": "float",
            "role": "feature",
            "source_dataset": "fuel",
            "description": "Reported engine efficiency percentage.",
        },
        "distance_per_efficiency": {
            "data_type": "float",
            "role": "feature",
            "source_dataset": "fuel",
            "description": "Distance divided by engine efficiency; zero efficiency yields missing.",
        },
        "efficiency_inverse": {
            "data_type": "float",
            "role": "feature",
            "source_dataset": "fuel",
            "description": "Reciprocal of engine efficiency; zero efficiency yields missing.",
        },
        "month_number": {
            "data_type": "integer",
            "role": "feature",
            "source_dataset": "fuel",
            "description": "Calendar month number derived from the source month label.",
        },
        "fuel_consumption": {
            "data_type": "float",
            "role": "target",
            "source_dataset": "fuel",
            "description": "Fuel consumption target.",
        },
        "co2_emissions": {
            "data_type": "float",
            "role": "target",
            "source_dataset": "fuel",
            "description": "CO2 emissions target.",
        },
    }


def build_modeling_dataset(
    fuel_path: str | Path = FUEL_PATH,
    marine_path: str | Path = MARINE_PATH,
    ais_query_points_path: str | Path = AIS_QUERY_POINTS_PATH,
    output_path: str | Path = OUTPUT_PATH,
    data_dictionary_path: str | Path = DATA_DICTIONARY_PATH,
) -> dict[str, Any]:
    """Build and persist the fuel-only supervised modeling dataset."""
    fuel = pd.read_csv(fuel_path)
    marine = pd.read_csv(marine_path)
    ais_query_points = pd.read_csv(ais_query_points_path)
    _require_columns(fuel, FUEL_REQUIRED_COLUMNS, "Fuel dataset")
    _require_columns(marine, {"mmsi", "timestamp", "latitude", "longitude"}, "Marine dataset")
    _require_columns(ais_query_points, {"mmsi", "timestamp", "latitude", "longitude"}, "AIS query-point dataset")

    fuel_ship_ids = set(fuel["ship_id"].dropna().astype(str))
    marine_mmsis = set(marine["mmsi"].dropna().astype(str))
    direct_key_overlap = fuel_ship_ids.intersection(marine_mmsis)
    marine_joined = False
    join_decision = (
        "Marine observations were not joined to fuel records: fuel uses ship_id while "
        "marine uses MMSI, and the fuel records contain no timestamp or geographic key "
        "to establish a legitimate relationship."
    )

    modeling = fuel.copy()
    modeling["distance"] = pd.to_numeric(modeling["distance"], errors="coerce")
    modeling["engine_efficiency"] = pd.to_numeric(modeling["engine_efficiency"], errors="coerce")
    modeling["fuel_consumption"] = pd.to_numeric(modeling["fuel_consumption"], errors="coerce")
    modeling["co2_emissions"] = pd.to_numeric(modeling["co2_emissions"], errors="coerce")
    modeling["distance_per_efficiency"] = modeling["distance"].div(
        modeling["engine_efficiency"].where(modeling["engine_efficiency"].ne(0))
    )
    modeling["efficiency_inverse"] = modeling["engine_efficiency"].where(
        modeling["engine_efficiency"].ne(0)
    ).rdiv(1)
    modeling["month_number"] = modeling["month"].map(MONTH_NUMBERS).astype("Int64")

    output_columns = [
        "ship_id",
        "ship_type",
        "route_id",
        "month",
        "distance",
        "fuel_type",
        "weather_conditions",
        "engine_efficiency",
        "distance_per_efficiency",
        "efficiency_inverse",
        "month_number",
        "fuel_consumption",
        "co2_emissions",
    ]
    modeling = modeling[output_columns]
    output = Path(output_path)
    dictionary_path = Path(data_dictionary_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    dictionary_path.parent.mkdir(parents=True, exist_ok=True)
    modeling.to_csv(output, index=False)

    dictionary = {
        "dataset": "fuel_prediction_dataset",
        "target_columns": TARGET_COLUMNS,
        "marine_joined": marine_joined,
        "marine_join_decision": join_decision,
        "source_row_counts": {
            "fuel": int(len(fuel)),
            "marine": int(len(marine)),
            "ais_query_points": int(len(ais_query_points)),
        },
        "direct_ship_id_mmsi_overlap_count": len(direct_key_overlap),
        "columns": _data_dictionary(),
    }
    dictionary_path.write_text(json.dumps(dictionary, indent=2), encoding="utf-8")

    missing_values = modeling.isna().sum().to_dict()
    target_distributions = {
        column: modeling[column].describe().to_dict() for column in TARGET_COLUMNS
    }
    categorical_cardinalities = {
        column: int(modeling[column].nunique(dropna=True))
        for column in ["ship_type", "route_id", "month", "fuel_type", "weather_conditions"]
    }
    print(f"Fuel rows: {len(fuel)}")
    print(f"Marine rows: {len(marine)}")
    print(f"Final modeling rows: {len(modeling)}")
    print(f"Missing values: {missing_values}")
    print(f"Target distributions: {target_distributions}")
    print(f"Categorical cardinalities: {categorical_cardinalities}")
    print(f"Marine joined to fuel records: {marine_joined}. {join_decision}")

    return {
        "dataframe": modeling,
        "output_path": str(output),
        "data_dictionary_path": str(dictionary_path),
        "marine_joined": marine_joined,
        "marine_join_decision": join_decision,
        "missing_values": missing_values,
        "target_distributions": target_distributions,
        "categorical_cardinalities": categorical_cardinalities,
    }


if __name__ == "__main__":
    build_modeling_dataset()
