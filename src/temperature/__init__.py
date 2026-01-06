"""
Temperature Integration Module

Integrates Open-Meteo weather API to provide air temperature data
for stream reach centroids.

This module enables thermal suitability calculations and species
scoring based on temperature conditions.
"""

from .open_meteo import OpenMeteoClient
from .schemas import (
    TemperatureReading,
    OpenMeteoResponse,
    TemperatureQuery,
    TemperatureIngestionResult,
    TemperatureBatchResult,
)

__all__ = [
    "OpenMeteoClient",
    "TemperatureReading",
    "OpenMeteoResponse",
    "TemperatureQuery",
    "TemperatureIngestionResult",
    "TemperatureBatchResult",
]
