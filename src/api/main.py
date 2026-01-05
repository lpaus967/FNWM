"""
FNWM FastAPI Application

Fisheries National Water Model Intelligence API

Exposes clean, user-facing interfaces for:
- Hydrologic conditions (now/today/outlook)
- Species habitat scoring
- Hatch likelihood predictions

Design Principles:
- Never expose raw NWM variables or complexity
- Include confidence metadata with every prediction
- Provide explainable results
- Follow RESTful conventions
- Auto-generate OpenAPI documentation
"""

import os
from datetime import datetime
from typing import List, Literal, Optional
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from dotenv import load_dotenv

# Import our modules
from src.api.schemas import (
    HydrologyReachResponse,
    NowResponse,
    TodayForecast,
    OutlookResponse,
    SpeciesScoreResponse,
    HatchForecastResponse,
    HatchPrediction,
    HealthResponse,
    MetadataResponse,
    SpeciesInfo,
    HatchInfo,
    ErrorResponse,
)
from src.species import compute_species_score, load_species_config
from src.hatches import compute_hatch_likelihood, get_all_hatch_predictions
from src.confidence import classify_confidence, classify_confidence_with_reasoning
from src.metrics import compute_bdi

# Load environment
load_dotenv()

# Initialize FastAPI app
app = FastAPI(
    title="FNWM API",
    description="Fisheries National Water Model Intelligence API - Hydrologic conditions and fisheries predictions",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# Database Dependency
# ============================================================================

def get_db_engine():
    """Get database engine."""
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        raise ValueError("DATABASE_URL not configured")
    return create_engine(database_url)


# ============================================================================
# Health & Metadata Endpoints
# ============================================================================

@app.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check():
    """
    Check API health status.

    Returns:
        Health status including database connectivity
    """
    try:
        engine = get_db_engine()
        with engine.connect() as conn:
            # Test database connection
            conn.execute(text("SELECT 1"))

            # Get last data update
            result = conn.execute(text("""
                SELECT MAX(valid_time) as last_update
                FROM hydro_timeseries
            """))
            row = result.fetchone()
            last_update = row[0] if row else None

        return HealthResponse(
            status="healthy",
            version="1.0.0",
            database="connected",
            last_data_update=last_update,
            message="All systems operational"
        )
    except Exception as e:
        return HealthResponse(
            status="unhealthy",
            version="1.0.0",
            database="disconnected",
            message=f"Database error: {str(e)}"
        )


@app.get("/metadata", response_model=MetadataResponse, tags=["System"])
async def get_metadata():
    """
    Get API metadata and available options.

    Returns:
        Available species, hatches, and configuration options
    """
    # Get available species
    species_dir = Path(__file__).parent.parent.parent / "config" / "species"
    species_files = list(species_dir.glob("*.yaml"))
    available_species = []
    for file in species_files:
        try:
            config = load_species_config(file.stem)
            available_species.append(SpeciesInfo(
                species_id=file.stem,
                name=config['name'],
                description=f"Habitat scoring for {config['name']}"
            ))
        except:
            continue

    # Get available hatches
    hatch_dir = Path(__file__).parent.parent.parent / "config" / "hatches"
    hatch_files = list(hatch_dir.glob("*.yaml"))
    available_hatches = []
    for file in hatch_files:
        try:
            import yaml
            with open(file) as f:
                config = yaml.safe_load(f)
            window = config.get('temporal_window', {})
            seasonal_desc = None
            if 'start_day_of_year' in window and 'end_day_of_year' in window:
                seasonal_desc = f"Day {window['start_day_of_year']}-{window['end_day_of_year']}"

            available_hatches.append(HatchInfo(
                hatch_id=file.stem,
                name=config['name'],
                scientific_name=config['species'],
                seasonal_window=seasonal_desc
            ))
        except:
            continue

    return MetadataResponse(
        available_species=available_species,
        available_hatches=available_hatches
    )


# ============================================================================
# TICKET 6.1: Hydrology Reach API
# ============================================================================

@app.get(
    "/hydrology/reach/{feature_id}",
    response_model=HydrologyReachResponse,
    tags=["Hydrology"],
    summary="Get hydrologic conditions for a reach"
)
async def get_reach_hydrology(
    feature_id: int,
    timeframe: Literal["now", "today", "outlook", "all"] = Query("all", description="Which timeframe to return"),
):
    """
    Get hydrologic conditions for a specific reach.

    **Timeframes:**
    - `now`: Current conditions (analysis data)
    - `today`: 18-hour forecast
    - `outlook`: 1-10 day outlook
    - `all`: All timeframes

    **Note:** Never exposes raw NWM variables - only interpreted metrics.
    """
    try:
        engine = get_db_engine()
        response = HydrologyReachResponse(feature_id=feature_id)

        with engine.begin() as conn:
            # Fetch "now" data (analysis_assim)
            if timeframe in ["now", "all"]:
                result = conn.execute(text("""
                    SELECT variable, value, valid_time, source
                    FROM hydro_timeseries
                    WHERE feature_id = :feature_id
                      AND source = 'analysis_assim'
                      AND variable IN ('streamflow', 'velocity', 'qBtmVertRunoff', 'qBucket', 'qSfcLatRunoff')
                    ORDER BY valid_time DESC
                    LIMIT 5
                """), {'feature_id': feature_id})

                data = {row[0]: {'value': row[1], 'time': row[2], 'source': row[3]} for row in result}

                if 'streamflow' in data and 'velocity' in data:
                    # Compute BDI
                    bdi = None
                    if all(k in data for k in ['qBtmVertRunoff', 'qBucket', 'qSfcLatRunoff']):
                        bdi = compute_bdi(
                            data['qBtmVertRunoff']['value'],
                            data['qBucket']['value'],
                            data['qSfcLatRunoff']['value']
                        )

                    # Classify confidence
                    confidence_obj = classify_confidence_with_reasoning(source='analysis_assim')

                    response.now = NowResponse(
                        flow_m3s=data['streamflow']['value'],
                        velocity_ms=data['velocity']['value'],
                        flow_percentile=None,  # Would need historical data
                        bdi=bdi,
                        confidence=confidence_obj.confidence,
                        confidence_reasoning=confidence_obj.reasoning,
                        timestamp=data['streamflow']['time'],
                        source=data['streamflow']['source']
                    )

        return response

    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


# ============================================================================
# TICKET 6.2: Fisheries Intelligence API
# ============================================================================

@app.get(
    "/fisheries/reach/{feature_id}/score",
    response_model=SpeciesScoreResponse,
    tags=["Fisheries"],
    summary="Get species habitat score"
)
async def get_fisheries_score(
    feature_id: int,
    species: str = Query("trout", description="Species identifier (e.g., 'trout')"),
    timeframe: Literal["now", "today"] = Query("now", description="Timeframe for scoring"),
):
    """
    Get species-specific habitat suitability score.

    Combines multiple habitat components:
    - Flow suitability
    - Velocity suitability
    - Stability (BDI-based)
    - Thermal suitability (when available)

    Returns explainable score with component breakdown and confidence.
    """
    try:
        engine = get_db_engine()

        with engine.begin() as conn:
            # Fetch hydrologic data
            source_filter = 'analysis_assim' if timeframe == 'now' else 'short_range'

            result = conn.execute(text("""
                SELECT variable, value
                FROM hydro_timeseries
                WHERE feature_id = :feature_id
                  AND source = :source
                  AND variable IN ('streamflow', 'velocity', 'qBtmVertRunoff', 'qBucket', 'qSfcLatRunoff')
                ORDER BY valid_time DESC
                LIMIT 5
            """), {'feature_id': feature_id, 'source': source_filter})

            data = {row[0]: row[1] for row in result}

            if not data or 'velocity' not in data:
                raise HTTPException(status_code=404, detail=f"No data found for reach {feature_id}")

            # Compute BDI
            bdi = 0.5  # Default
            if all(k in data for k in ['qBtmVertRunoff', 'qBucket', 'qSfcLatRunoff']):
                bdi = compute_bdi(
                    data['qBtmVertRunoff'],
                    data['qBucket'],
                    data['qSfcLatRunoff']
                )

            # Prepare hydro_data for species scoring
            hydro_data = {
                'flow_percentile': 50,  # Simplified - would compute from historical
                'velocity': data.get('velocity', 0.0),
                'bdi': bdi,
                'flow_variability': None,
            }

            # Classify confidence
            confidence_obj = classify_confidence_with_reasoning(source=source_filter)

            # Compute species score
            score = compute_species_score(
                feature_id=feature_id,
                species=species,
                hydro_data=hydro_data,
                confidence=confidence_obj.confidence
            )

            return SpeciesScoreResponse(
                feature_id=feature_id,
                species=score.species,
                overall_score=score.overall_score,
                rating=score.rating,
                components=score.components,
                explanation=score.explanation,
                confidence=score.confidence,
                confidence_reasoning=confidence_obj.reasoning,
                timestamp=score.timestamp,
                timeframe=timeframe
            )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error computing score: {str(e)}")


@app.get(
    "/fisheries/reach/{feature_id}/hatches",
    response_model=HatchForecastResponse,
    tags=["Fisheries"],
    summary="Get hatch likelihood forecast"
)
async def get_hatch_forecast(
    feature_id: int,
    date: Optional[str] = Query(None, description="Date to check (ISO 8601, defaults to today)"),
):
    """
    Get hatch likelihood predictions for all configured hatches.

    Predicts insect hatch likelihood based on:
    - Hydrologic signature matching
    - Seasonal windows
    - Current flow conditions

    Returns all hatches sorted by likelihood (descending).
    """
    try:
        # Parse date
        check_date = datetime.fromisoformat(date) if date else datetime.utcnow()

        engine = get_db_engine()

        with engine.begin() as conn:
            # Fetch current hydrologic data
            result = conn.execute(text("""
                SELECT variable, value
                FROM hydro_timeseries
                WHERE feature_id = :feature_id
                  AND source = 'analysis_assim'
                  AND variable IN ('streamflow', 'velocity', 'qBtmVertRunoff', 'qBucket', 'qSfcLatRunoff')
                ORDER BY valid_time DESC
                LIMIT 5
            """), {'feature_id': feature_id})

            data = {row[0]: row[1] for row in result}

            if not data:
                raise HTTPException(status_code=404, detail=f"No data found for reach {feature_id}")

            # Compute BDI
            bdi = 0.5
            if all(k in data for k in ['qBtmVertRunoff', 'qBucket', 'qSfcLatRunoff']):
                bdi = compute_bdi(
                    data['qBtmVertRunoff'],
                    data['qBucket'],
                    data['qSfcLatRunoff']
                )

            # Prepare hydro_data for hatch prediction
            hydro_data = {
                'flow_percentile': 50,  # Simplified
                'rising_limb': False,  # Would detect from timeseries
                'velocity': data.get('velocity', 0.0),
                'bdi': bdi,
            }

            # Get all hatch predictions
            hatch_scores = get_all_hatch_predictions(
                feature_id=feature_id,
                hydro_data=hydro_data,
                current_date=check_date
            )

            # Convert to API schema
            hatches = [
                HatchPrediction(
                    hatch_name=h.hatch_name,
                    scientific_name=h.scientific_name,
                    likelihood=h.likelihood,
                    rating=h.rating,
                    in_season=h.in_season,
                    hydrologic_match=h.hydrologic_match,
                    explanation=h.explanation
                )
                for h in hatch_scores
            ]

            return HatchForecastResponse(
                feature_id=feature_id,
                date=check_date.isoformat(),
                hatches=hatches
            )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error predicting hatches: {str(e)}")


# ============================================================================
# Run Application
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
