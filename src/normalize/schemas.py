"""
Canonical Data Schemas for FNWM

Defines the normalized data models used throughout the system.

Design Principles:
- All NWM products map to a single canonical schema
- No raw NWM filenames or f### references leak downstream
- Timezone-aware timestamps (always UTC)
- Explicit source tagging for traceability
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, validator


class NWMSource(str, Enum):
    """
    Canonical NWM product sources.

    These are the ONLY products we ingest.
    """
    ANALYSIS_ASSIM = "analysis_assim"
    SHORT_RANGE = "short_range"
    MEDIUM_BLEND = "medium_range_blend"
    NO_DA = "analysis_assim_no_da"


class HydroVariable(str, Enum):
    """
    Hydrology variables we track.
    """
    STREAMFLOW = "streamflow"
    VELOCITY = "velocity"
    QSFC_LAT_RUNOFF = "qSfcLatRunoff"
    QBUCKET = "qBucket"
    QBTM_VERT_RUNOFF = "qBtmVertRunoff"
    NUDGE = "nudge"


class HydroRecord(BaseModel):
    """
    Canonical hydrology record.

    All NWM data is normalized to this schema before storage.
    """
    feature_id: int = Field(..., description="NHDPlus feature ID")
    valid_time: datetime = Field(..., description="Valid time (UTC, timezone-aware)")
    variable: HydroVariable = Field(..., description="Hydrology variable name")
    value: float = Field(..., description="Variable value")
    source: NWMSource = Field(..., description="NWM product source")
    forecast_hour: Optional[int] = Field(None, description="Forecast hour (None for analysis)")

    @validator('valid_time')
    def valid_time_must_be_utc(cls, v):
        """Ensure valid_time is timezone-aware UTC"""
        if v.tzinfo is None:
            raise ValueError("valid_time must be timezone-aware (UTC)")
        return v

    class Config:
        """Pydantic config"""
        use_enum_values = True


class ReachMetadata(BaseModel):
    """
    Metadata about a stream reach.

    Stored in reach_metadata table.
    """
    feature_id: int
    reach_name: Optional[str] = None
    state: Optional[str] = None
    region: Optional[str] = None
    domain: str = "conus"
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    baseline_flow_m3s: Optional[float] = Field(
        None,
        description="Long-term mean flow for percentile calculations"
    )
    baseline_period: Optional[str] = Field(
        None,
        description="Period used for baseline (e.g., '1991-2020')"
    )


class UserObservation(BaseModel):
    """
    User-submitted trip report or hatch observation.

    Used for validation loop (EPIC 7).
    """
    feature_id: int
    observation_time: datetime
    observation_type: str  # 'trip_report' or 'hatch_sighting'
    species: Optional[str] = None
    hatch_name: Optional[str] = None
    success_rating: Optional[int] = Field(None, ge=1, le=5)
    notes: Optional[str] = None
    user_id: Optional[str] = Field(None, description="Anonymized user ID")

    @validator('observation_time')
    def observation_time_must_be_utc(cls, v):
        """Ensure observation_time is timezone-aware UTC"""
        if v.tzinfo is None:
            raise ValueError("observation_time must be timezone-aware (UTC)")
        return v


class IngestionLog(BaseModel):
    """
    Log entry for data ingestion monitoring.
    """
    product: str
    cycle_time: datetime
    domain: str = "conus"
    status: str  # 'running', 'success', 'failed'
    records_ingested: Optional[int] = None
    error_message: Optional[str] = None
    started_at: datetime
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None


class ComputedScore(BaseModel):
    """
    Cached species or hatch score.

    Stored in computed_scores table.
    """
    feature_id: int
    score_type: str  # 'species' or 'hatch'
    score_target: str  # Species name or hatch name
    valid_time: datetime
    score_value: float = Field(..., ge=0.0, le=1.0)
    rating: str  # 'poor', 'fair', 'good', 'excellent'
    components: dict  # JSON breakdown of score components
    explanation: str
    confidence: str  # 'high', 'medium', 'low'

    @validator('valid_time')
    def valid_time_must_be_utc(cls, v):
        """Ensure valid_time is timezone-aware UTC"""
        if v.tzinfo is None:
            raise ValueError("valid_time must be timezone-aware (UTC)")
        return v
