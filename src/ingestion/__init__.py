"""Ingestion utilities for GreenFleet data sources."""

from .fuel_loader import FuelDataLoader
from .fuel_preprocessor import GreenFleetFuelPreprocessor
from .gfw_loader import GFWApiClient, GFWDataPreprocessor
from .ais_loader import AISDataLoader
from .historical_marine_api import HistoricalMarineClient, HistoricalMarineConfig, retrieve_historical_marine_data
from .open_meteo_marine_loader import OpenMeteoMarineClient, OpenMeteoMarinePreprocessor
from .spatial_temporal_join import VesselMarineJoiner
from .schema import GREENFLEET_CANONICAL_SCHEMA, map_dataset_to_canonical_schema

__all__ = [
    "FuelDataLoader",
    "GreenFleetFuelPreprocessor",
    "GFWApiClient",
    "GFWDataPreprocessor",
    "AISDataLoader",
    "HistoricalMarineClient",
    "HistoricalMarineConfig",
    "retrieve_historical_marine_data",
    "OpenMeteoMarineClient",
    "OpenMeteoMarinePreprocessor",
    "VesselMarineJoiner",
    "GREENFLEET_CANONICAL_SCHEMA",
    "map_dataset_to_canonical_schema",
]
