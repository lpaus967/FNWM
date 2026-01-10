"""
USGS Water Services Data Schemas

Pydantic models for USGS Instantaneous Values API responses.
"""

from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class USGSParameter(BaseModel):
    """USGS parameter code information."""
    parameter_cd: str = Field(..., alias='parameterCd')
    name: str
    description: Optional[str] = None
    unit_cd: Optional[str] = Field(None, alias='unitCd')
    unit_name: Optional[str] = None

    class Config:
        populate_by_name = True


class USGSValue(BaseModel):
    """Individual measurement value."""
    value: str
    qualifiers: List[str] = []
    date_time: datetime = Field(..., alias='dateTime')

    class Config:
        populate_by_name = True


class USGSVariable(BaseModel):
    """Variable metadata from USGS response."""
    variable_code: str = Field(..., alias='variableCode')
    variable_name: str = Field(..., alias='variableName')
    variable_description: str = Field(..., alias='variableDescription')
    value_type: str = Field(..., alias='valueType')
    unit_code: str = Field(..., alias='unit')
    no_data_value: float = Field(..., alias='noDataValue')

    class Config:
        populate_by_name = True


class USGSTimeSeries(BaseModel):
    """Time series data for a specific parameter."""
    site_code: str
    variable: USGSVariable
    values: List[USGSValue]
    source_info: Optional[Dict[str, Any]] = None

    class Config:
        populate_by_name = True


class USGSSiteData(BaseModel):
    """Complete site data with all time series."""
    site_code: str
    site_name: str
    time_series: List[USGSTimeSeries] = []

    class Config:
        populate_by_name = True


class USGSInstantaneousValue(BaseModel):
    """
    Processed instantaneous value reading from USGS.

    This is a simplified model for storing in the database.
    """
    site_id: str
    parameter_cd: str
    parameter_name: str
    value: float
    unit: str
    datetime: datetime
    qualifiers: List[str] = []
    is_provisional: bool = True

    class Config:
        populate_by_name = True


class USGSFetchResult(BaseModel):
    """Result of fetching USGS data."""
    site_id: str
    success: bool
    data: Optional[List[USGSInstantaneousValue]] = None
    error: Optional[str] = None
    fetched_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True
