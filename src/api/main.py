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
from src.metrics import compute_bdi, compute_flow_percentile_for_reach, detect_rising_limb, compute_thermal_suitability

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

                    # Compute flow percentile
                    percentile_result = compute_flow_percentile_for_reach(
                        feature_id=feature_id,
                        current_flow=data['streamflow']['value'],
                        timestamp=data['streamflow']['time']
                    )

                    # Fetch temperature data
                    air_temp_f = None
                    water_temp_est_f = None
                    try:
                        temp_result = conn.execute(text("""
                            SELECT temperature_2m
                            FROM temperature_timeseries
                            WHERE nhdplusid = :feature_id
                              AND forecast_hour = 0
                              AND temperature_2m IS NOT NULL
                            ORDER BY valid_time DESC
                            LIMIT 1
                        """), {'feature_id': feature_id})
                        temp_row = temp_result.fetchone()
                        if temp_row:
                            air_temp_c = temp_row[0]
                            water_temp_c = air_temp_c - 3.0  # Air-to-water conversion
                            # Convert to Fahrenheit
                            air_temp_f = round(air_temp_c * 9/5 + 32, 1)
                            water_temp_est_f = round(water_temp_c * 9/5 + 32, 1)
                    except Exception as e:
                        # Temperature data is optional, don't fail if not available
                        pass

                    response.now = NowResponse(
                        flow_m3s=data['streamflow']['value'],
                        velocity_ms=data['velocity']['value'],
                        flow_percentile=percentile_result.get('percentile'),
                        bdi=bdi,
                        air_temperature_f=air_temp_f,
                        water_temperature_est_f=water_temp_est_f,
                        confidence=confidence_obj.confidence,
                        confidence_reasoning=confidence_obj.reasoning,
                        timestamp=data['streamflow']['time'],
                        source=data['streamflow']['source']
                    )

            # Fetch "today" data (short_range f001-f018)
            if timeframe in ["today", "all"]:
                result = conn.execute(text("""
                    SELECT forecast_hour, valid_time, variable, value
                    FROM hydro_timeseries
                    WHERE feature_id = :feature_id
                      AND source = 'short_range'
                      AND variable IN ('streamflow', 'velocity')
                      AND forecast_hour BETWEEN 1 AND 18
                    ORDER BY forecast_hour, variable
                """), {'feature_id': feature_id})

                # Organize data by forecast hour
                forecast_data = {}
                for row in result:
                    fh, vt, var, val = row
                    if fh not in forecast_data:
                        forecast_data[fh] = {'valid_time': vt}
                    forecast_data[fh][var] = val

                if forecast_data:
                    # Detect rising limb from streamflow timeseries
                    flows = [(forecast_data[fh]['valid_time'], forecast_data[fh].get('streamflow', 0.0))
                             for fh in sorted(forecast_data.keys()) if 'streamflow' in forecast_data[fh]]

                    rising_limb_result = None
                    if len(flows) >= 3:
                        try:
                            rising_limb_result = detect_rising_limb(flows)
                        except:
                            pass  # Rising limb detection optional

                    # Classify confidence for short_range
                    sr_confidence = classify_confidence_with_reasoning(source='short_range')

                    # Build TodayForecast list
                    today_forecasts = []
                    for fh in sorted(forecast_data.keys()):
                        if 'streamflow' in forecast_data[fh] and 'velocity' in forecast_data[fh]:
                            # Check if this hour is part of rising limb
                            is_rising = False
                            intensity = None
                            if rising_limb_result and rising_limb_result.get('detected'):
                                is_rising = True
                                intensity = rising_limb_result.get('intensity', 'moderate')

                            today_forecasts.append(TodayForecast(
                                hour=fh,
                                valid_time=forecast_data[fh]['valid_time'],
                                flow_m3s=forecast_data[fh]['streamflow'],
                                velocity_ms=forecast_data[fh]['velocity'],
                                rising_limb_detected=is_rising,
                                rising_limb_intensity=intensity,
                                confidence=sr_confidence.confidence
                            ))

                    response.today = today_forecasts if today_forecasts else None

            # Fetch "outlook" data (medium_range_blend)
            if timeframe in ["outlook", "all"]:
                result = conn.execute(text("""
                    SELECT value
                    FROM hydro_timeseries
                    WHERE feature_id = :feature_id
                      AND source = 'medium_range_blend'
                      AND variable = 'streamflow'
                    ORDER BY forecast_hour
                """), {'feature_id': feature_id})

                flows = [row[0] for row in result]

                if flows and len(flows) >= 3:
                    import numpy as np

                    mean_flow = float(np.mean(flows))
                    min_flow = float(np.min(flows))
                    max_flow = float(np.max(flows))

                    # Determine trend (simple: compare first third vs last third)
                    first_third = flows[:len(flows)//3]
                    last_third = flows[-len(flows)//3:]

                    trend = "stable"
                    if np.mean(last_third) > np.mean(first_third) * 1.1:
                        trend = "rising"
                    elif np.mean(last_third) < np.mean(first_third) * 0.9:
                        trend = "falling"

                    # Ensemble spread (coefficient of variation)
                    cv = float(np.std(flows) / np.mean(flows)) if np.mean(flows) > 0 else 0.0

                    # Classify confidence
                    mr_confidence = classify_confidence_with_reasoning(source='medium_range_blend')

                    # Generate interpretation
                    interpretation = f"10-day outlook shows {trend} trend. "
                    if trend == "rising":
                        interpretation += f"Flow expected to increase from {min_flow:.2f} to {max_flow:.2f} m³/s."
                    elif trend == "falling":
                        interpretation += f"Flow expected to decrease from {max_flow:.2f} to {min_flow:.2f} m³/s."
                    else:
                        interpretation += f"Flow expected to remain stable around {mean_flow:.2f} m³/s."

                    response.outlook = OutlookResponse(
                        trend=trend,
                        confidence=mr_confidence.confidence,
                        mean_flow_m3s=mean_flow,
                        min_flow_m3s=min_flow,
                        max_flow_m3s=max_flow,
                        ensemble_spread=cv,
                        interpretation=interpretation
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
    - Flow suitability (flow percentile vs optimal range)
    - Velocity suitability (species-specific velocity ranges)
    - Thermal suitability (TSI from Open-Meteo temperature data) ✅
    - Stability (BDI-based baseflow dominance)

    Returns explainable score with component breakdown and confidence.
    """
    try:
        engine = get_db_engine()

        with engine.begin() as conn:
            # Fetch hydrologic data
            source_filter = 'analysis_assim' if timeframe == 'now' else 'short_range'

            result = conn.execute(text("""
                SELECT variable, value, valid_time
                FROM hydro_timeseries
                WHERE feature_id = :feature_id
                  AND source = :source
                  AND variable IN ('streamflow', 'velocity', 'qBtmVertRunoff', 'qBucket', 'qSfcLatRunoff')
                ORDER BY valid_time DESC
                LIMIT 5
            """), {'feature_id': feature_id, 'source': source_filter})

            rows = result.fetchall()
            data = {row[0]: row[1] for row in rows}
            timestamp = rows[0][2] if rows else datetime.now()  # Get timestamp from first row

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

            # Compute flow percentile
            percentile_result = compute_flow_percentile_for_reach(
                feature_id=feature_id,
                current_flow=data.get('streamflow', 0.0),
                timestamp=timestamp
            )

            # Compute thermal suitability (TSI)
            species_config = load_species_config(species)
            tsi_result = compute_thermal_suitability(
                engine=engine,
                nhdplusid=feature_id,
                species_config=species_config,
                timeframe=timeframe
            )
            tsi_score = tsi_result.get('score', 0.0) if tsi_result.get('score') is not None else 0.0

            # Prepare hydro_data for species scoring
            hydro_data = {
                'flow_percentile': percentile_result.get('percentile', 50.0),
                'velocity': data.get('velocity', 0.0),
                'bdi': bdi,
                'flow_variability': None,
                'tsi': tsi_score,  # ✅ EPIC-3: Include thermal suitability
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
                SELECT variable, value, valid_time
                FROM hydro_timeseries
                WHERE feature_id = :feature_id
                  AND source = 'analysis_assim'
                  AND variable IN ('streamflow', 'velocity', 'qBtmVertRunoff', 'qBucket', 'qSfcLatRunoff')
                ORDER BY valid_time DESC
                LIMIT 5
            """), {'feature_id': feature_id})

            rows = result.fetchall()
            data = {row[0]: row[1] for row in rows}
            timestamp = rows[0][2] if rows else datetime.now()  # Get timestamp from first row

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

            # Compute flow percentile
            percentile_result = compute_flow_percentile_for_reach(
                feature_id=feature_id,
                current_flow=data.get('streamflow', 0.0),
                timestamp=timestamp
            )

            # Prepare hydro_data for hatch prediction
            hydro_data = {
                'flow_percentile': percentile_result.get('percentile', 50.0),
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
