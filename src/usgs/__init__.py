"""
USGS Water Services Integration

This module provides integration with USGS Water Services API for fetching
real-time streamflow and gage height data from USGS monitoring stations.
"""

from .client import USGSClient
from .schemas import (
    USGSInstantaneousValue,
    USGSSiteData,
    USGSParameter,
    USGSTimeSeries,
)

__all__ = [
    'USGSClient',
    'USGSInstantaneousValue',
    'USGSSiteData',
    'USGSParameter',
    'USGSTimeSeries',
]
