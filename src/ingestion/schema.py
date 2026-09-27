"""Canonical GreenFleet schema and mapping utilities."""

from __future__ import annotations

from collections import OrderedDict
from typing import Any

GREENFLEET_CANONICAL_SCHEMA: OrderedDict[str, dict[str, Any]] = OrderedDict(
    [
        ("vessel_id", {"description": "Unique vessel or asset identifier.", "source": "ship_id", "available": True}),
        ("vessel_type", {"description": "Primary vessel category or class.", "source": "ship_type", "available": True}),
        ("route_id", {"description": "Operational route or voyage corridor identifier.", "source": "route_id", "available": True}),
        ("period", {"description": "Reporting period or month label used in the source dataset.", "source": "month", "available": True}),
        ("distance", {"description": "Distance covered during the reporting period.", "source": "distance", "available": True}),
        ("fuel_type", {"description": "Fuel type used during the period.", "source": "fuel_type", "available": True}),
        ("fuel_consumption", {"description": "Fuel consumed during the period.", "source": "fuel_consumption", "available": True}),
        ("co2_emissions", {"description": "CO2 emissions emitted during the period.", "source": "CO2_emissions", "available": True}),
        ("weather_condition", {"description": "Observed weather condition for the voyage or period.", "source": "weather_conditions", "available": True}),
        ("engine_efficiency", {"description": "Engine efficiency percentage reported by the source.", "source": "engine_efficiency", "available": True}),
        ("cargo_capacity", {"description": "Maximum cargo capacity of the vessel.", "source": None, "available": False}),
        ("cargo_load", {"description": "Cargo mass or payload loaded during the reporting period.", "source": None, "available": False}),
        ("speed", {"description": "Vessel speed in operational units.", "source": None, "available": False}),
        ("wind_speed", {"description": "Wind speed at the operating period.", "source": None, "available": False}),
        ("wave_height", {"description": "Wave height at the operating period.", "source": None, "available": False}),
        ("current_speed", {"description": "Ocean current speed at the operating period.", "source": None, "available": False}),
    ]
)


def _snake_case(value: str) -> str:
    normalized = str(value).strip().lower().replace(" ", "_").replace("-", "_")
    import re
    normalized = re.sub(r"[^a-z0-9_]+", "_", normalized)
    normalized = re.sub(r"_+", "_", normalized)
    return normalized.strip("_")


def map_dataset_to_canonical_schema(frame) -> dict[str, str | None]:
    """Map current source columns to the GreenFleet canonical schema."""
    normalized = {str(key).lower(): key for key in frame.columns}
    mapping: dict[str, str | None] = {}

    direct_aliases = {
        "vessel_id": ["ship_id"],
        "vessel_type": ["ship_type"],
        "route_id": ["route_id"],
        "period": ["month"],
        "distance": ["distance"],
        "fuel_type": ["fuel_type"],
        "fuel_consumption": ["fuel_consumption"],
        "co2_emissions": ["co2_emissions", "co2 emissions"],
        "weather_condition": ["weather_conditions", "weather_condition"],
        "engine_efficiency": ["engine_efficiency"],
        "cargo_capacity": [None],
        "cargo_load": [None],
        "speed": [None],
        "wind_speed": [None],
        "wave_height": [None],
        "current_speed": [None],
    }

    for canonical_field, aliases in direct_aliases.items():
        resolved = None
        for alias in aliases:
            if alias is None:
                continue
            key = str(alias).lower()
            if key in normalized:
                resolved = _snake_case(normalized[key])
                break
        mapping[canonical_field] = resolved

    return mapping


def schema_available_fields() -> list[str]:
    return [field for field, info in GREENFLEET_CANONICAL_SCHEMA.items() if info["available"]]


def schema_unavailable_fields() -> list[str]:
    return [field for field, info in GREENFLEET_CANONICAL_SCHEMA.items() if not info["available"]]
