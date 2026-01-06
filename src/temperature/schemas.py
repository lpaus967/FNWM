"""
Temperature Data Models

Pydantic schemas for Open-Meteo temperature data ingestion and storage.
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, validator


class TemperatureReading(BaseModel):
    """Single temperature observation for a stream reach."""

    nhdplusid: int = Field(..., description="NHD reach identifier")
    valid_time: datetime = Field(..., description="Time this temperature reading is valid for (UTC)")
    temperature_2m: Optional[float] = Field(None, description="Air temperature at 2m (°C)")
    apparent_temperature: Optional[float] = Field(None, description="Apparent/feels-like temperature (°C)")
    precipitation: Optional[float] = Field(None, description="Precipitation (mm)")
    cloud_cover: Optional[int] = Field(None, description="Cloud cover (%)", ge=0, le=100)
    source: str = Field(default="open-meteo", description="Data source")
    forecast_hour: Optional[int] = Field(None, description="Forecast hour (0 or None = current)")

    @validator('valid_time')
    def ensure_utc(cls, v):
        """Ensure timestamp is timezone-aware UTC."""
        if v.tzinfo is None:
            raise ValueError("valid_time must be timezone-aware (UTC)")
        return v

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class OpenMeteoResponse(BaseModel):
    """Response from Open-Meteo API."""

    latitude: float = Field(..., description="Location latitude")
    longitude: float = Field(..., description="Location longitude")
    timezone: str = Field(..., description="Timezone of returned data")
    current: Optional[dict] = Field(None, description="Current weather conditions")
    hourly: Optional[dict] = Field(None, description="Hourly forecast data")
    daily: Optional[dict] = Field(None, description="Daily forecast data")


class TemperatureQuery(BaseModel):
    """Query parameters for fetching temperature data."""

    nhdplusid: int = Field(..., description="NHD reach identifier")
    latitude: float = Field(..., description="Centroid latitude", ge=-90, le=90)
    longitude: float = Field(..., description="Centroid longitude", ge=-180, le=180)
    forecast_days: int = Field(default=7, description="Number of forecast days", ge=0, le=16)
    include_current: bool = Field(default=True, description="Include current conditions")


class TemperatureIngestionResult(BaseModel):
    """Result from temperature ingestion operation."""

    nhdplusid: int
    readings_fetched: int
    readings_inserted: int
    errors: list[str] = Field(default_factory=list)
    success: bool

    @property
    def has_errors(self) -> bool:
        """Check if any errors occurred."""
        return len(self.errors) > 0


class TemperatureBatchResult(BaseModel):
    """Result from batch temperature ingestion."""

    total_reaches: int
    successful_reaches: int
    failed_reaches: int
    total_readings_inserted: int
    errors: list[str] = Field(default_factory=list)
    duration_seconds: float

    @property
    def success_rate(self) -> float:
        """Calculate success rate percentage."""
        if self.total_reaches == 0:
            return 0.0
        return (self.successful_reaches / self.total_reaches) * 100
