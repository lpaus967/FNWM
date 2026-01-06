"""
API Response Schemas for FNWM

Pydantic models for all API endpoints. These define the contract between
the API and clients.

Design Principles:
- Never expose raw NWM variables (folders, f###, etc.)
- All timestamps are UTC, ISO 8601 format
- Include confidence metadata with every prediction
- Provide explanations for all derived values
- Use clear, user-facing field names
"""

from typing import Optional, List, Literal, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field


# ============================================================================
# Hydrology API Schemas (Ticket 6.1)
# ============================================================================

class NowResponse(BaseModel):
    """Current hydrologic conditions (analysis data)."""

    flow_m3s: float = Field(..., description="Current streamflow (m³/s)")
    velocity_ms: float = Field(..., description="Current velocity (m/s)")
    flow_percentile: Optional[float] = Field(None, description="Flow percentile (0-100)", ge=0, le=100)
    bdi: Optional[float] = Field(None, description="Baseflow Dominance Index (0-1)", ge=0, le=1)
    air_temperature_f: Optional[float] = Field(None, description="Air temperature (°F)")
    water_temperature_est_f: Optional[float] = Field(None, description="Estimated water temperature (°F)")
    confidence: str = Field(..., description="Confidence level (high/medium/low)")
    confidence_reasoning: Optional[str] = Field(None, description="Why this confidence level")
    timestamp: datetime = Field(..., description="Valid time (UTC)")
    source: str = Field(..., description="Data source (e.g., analysis_assim)")


class TodayForecast(BaseModel):
    """Single forecast hour."""

    hour: int = Field(..., description="Forecast hour (1-18)")
    valid_time: datetime = Field(..., description="Valid time (UTC)")
    flow_m3s: float = Field(..., description="Forecast streamflow (m³/s)")
    velocity_ms: float = Field(..., description="Forecast velocity (m/s)")
    rising_limb_detected: bool = Field(..., description="Rising limb detected")
    rising_limb_intensity: Optional[str] = Field(None, description="Intensity if detected (weak/moderate/strong)")
    confidence: str = Field(..., description="Confidence level for this hour")


class OutlookResponse(BaseModel):
    """Medium-range outlook (1-10 days)."""

    trend: Literal["rising", "falling", "stable"] = Field(..., description="Overall flow trend")
    confidence: str = Field(..., description="Confidence level (high/medium/low)")
    mean_flow_m3s: float = Field(..., description="Mean forecast flow (m³/s)")
    min_flow_m3s: float = Field(..., description="Minimum forecast flow (m³/s)")
    max_flow_m3s: float = Field(..., description="Maximum forecast flow (m³/s)")
    ensemble_spread: Optional[float] = Field(None, description="Forecast uncertainty (CV)")
    interpretation: Optional[str] = Field(None, description="Human-readable interpretation")


class HydrologyReachResponse(BaseModel):
    """Complete hydrology response for a reach."""

    feature_id: int = Field(..., description="NHD reach feature ID")
    now: Optional[NowResponse] = Field(None, description="Current conditions")
    today: Optional[List[TodayForecast]] = Field(None, description="Today's forecast (f001-f018)")
    outlook: Optional[OutlookResponse] = Field(None, description="Medium-range outlook")
    generated_at: datetime = Field(default_factory=datetime.utcnow, description="When response was generated")


# ============================================================================
# Fisheries Intelligence API Schemas (Ticket 6.2)
# ============================================================================

class SpeciesScoreResponse(BaseModel):
    """Species habitat suitability score."""

    feature_id: int = Field(..., description="NHD reach feature ID")
    species: str = Field(..., description="Species name (e.g., 'Coldwater Trout')")
    overall_score: float = Field(..., ge=0, le=1, description="Overall habitat score (0-1)")
    rating: Literal["poor", "fair", "good", "excellent"] = Field(..., description="Qualitative rating")

    components: Dict[str, float] = Field(..., description="Component scores breakdown")
    explanation: str = Field(..., description="Human-readable explanation")
    confidence: str = Field(..., description="Confidence level (high/medium/low)")
    confidence_reasoning: Optional[str] = Field(None, description="Why this confidence level")

    timestamp: datetime = Field(default_factory=datetime.utcnow, description="When score was computed")
    timeframe: str = Field(..., description="Timeframe (now/today)")


class HatchPrediction(BaseModel):
    """Single hatch likelihood prediction."""

    hatch_name: str = Field(..., description="Common name (e.g., 'Green Drake')")
    scientific_name: str = Field(..., description="Scientific name")
    likelihood: float = Field(..., ge=0, le=1, description="Likelihood score (0-1)")
    rating: Literal["unlikely", "possible", "likely", "very_likely"] = Field(..., description="Qualitative rating")

    in_season: bool = Field(..., description="Whether currently in seasonal window")
    hydrologic_match: Dict[str, bool] = Field(..., description="Condition-by-condition matches")
    explanation: str = Field(..., description="Human-readable explanation")


class HatchForecastResponse(BaseModel):
    """Hatch forecast for a reach."""

    feature_id: int = Field(..., description="NHD reach feature ID")
    date: str = Field(..., description="Date checked (ISO 8601)")
    hatches: List[HatchPrediction] = Field(..., description="All hatch predictions, sorted by likelihood")
    generated_at: datetime = Field(default_factory=datetime.utcnow, description="When forecast was generated")


# ============================================================================
# Error Responses
# ============================================================================

class ErrorResponse(BaseModel):
    """Standard error response."""

    error: str = Field(..., description="Error type")
    message: str = Field(..., description="Human-readable error message")
    detail: Optional[str] = Field(None, description="Additional details")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="When error occurred")


# ============================================================================
# Health Check
# ============================================================================

class HealthResponse(BaseModel):
    """API health status."""

    status: Literal["healthy", "degraded", "unhealthy"] = Field(..., description="Overall status")
    version: str = Field(..., description="API version")
    database: Literal["connected", "disconnected"] = Field(..., description="Database status")
    last_data_update: Optional[datetime] = Field(None, description="When data was last updated")
    message: Optional[str] = Field(None, description="Additional status info")


# ============================================================================
# Metadata / Info
# ============================================================================

class SpeciesInfo(BaseModel):
    """Available species information."""

    species_id: str = Field(..., description="Species identifier (e.g., 'trout')")
    name: str = Field(..., description="Common name")
    description: Optional[str] = Field(None, description="Description")


class HatchInfo(BaseModel):
    """Available hatch information."""

    hatch_id: str = Field(..., description="Hatch identifier (e.g., 'green_drake')")
    name: str = Field(..., description="Common name")
    scientific_name: str = Field(..., description="Scientific name")
    seasonal_window: Optional[str] = Field(None, description="Typical season (e.g., 'Mid-May to Late June')")


class MetadataResponse(BaseModel):
    """API metadata and available options."""

    available_species: List[SpeciesInfo] = Field(..., description="Species available for scoring")
    available_hatches: List[HatchInfo] = Field(..., description="Hatches available for prediction")
    confidence_levels: List[str] = Field(default=["high", "medium", "low"], description="Possible confidence values")
    timeframes: List[str] = Field(default=["now", "today", "outlook"], description="Available timeframes")
