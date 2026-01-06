# FNWM API Documentation

## Overview

The FNWM (Fly-Fishing Network Water Model) API provides RESTful endpoints for accessing hydrologic conditions, fisheries intelligence, and habitat scoring for stream reaches.

**Key Features**:
- Clean, user-facing field names (no raw NWM variable exposure)
- Confidence metadata included in all predictions
- Explainable AI responses with reasoning
- Auto-generated OpenAPI documentation
- CORS support for web clients

---

## Quick Start

### Prerequisites

- Python environment with `fnwm` conda environment
- PostgreSQL database with FNWM data
- Required dependencies installed (FastAPI, uvicorn, SQLAlchemy)

### Starting the API

1. **Activate the conda environment**:
   ```bash
   conda activate fnwm
   ```

2. **Navigate to the FNWM project directory**:
   ```bash
   cd C:\Users\lpaus\GitHub Connections\FNWM
   ```

3. **Start the development server**:
   ```bash
   python -m uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000
   ```

4. **Verify the API is running**:
   - Server will start at: `http://localhost:8000`
   - Health check: `http://localhost:8000/health`

### Interactive Documentation

Once the API is running, access the interactive documentation:

- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`
- **OpenAPI JSON**: `http://localhost:8000/openapi.json`

---

## Configuration

### Environment Variables

The API requires the following environment variable:

```bash
DATABASE_URL=postgresql://user:password@host:port/fnwm
```

### Dependencies

Ensure the following packages are installed:

```
fastapi>=0.104.0
uvicorn[standard]>=0.24.0
python-multipart>=0.0.6
sqlalchemy>=2.0.0
```

---

## API Endpoints

### System Endpoints

#### Health Check
```
GET /health
```

Returns the system health status and database connectivity.

**Example Response**:
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "database": "connected",
  "last_data_update": "2026-01-04T19:00:00Z",
  "message": "All systems operational"
}
```

#### Metadata
```
GET /metadata
```

Returns available species, hatches, confidence levels, and timeframes.

**Example Response**:
```json
{
  "available_species": [
    {
      "species_id": "trout",
      "name": "Coldwater Trout",
      "description": "Habitat scoring for Coldwater Trout"
    }
  ],
  "available_hatches": [
    {
      "hatch_id": "green_drake",
      "name": "Green Drake",
      "scientific_name": "Ephemera guttulata",
      "seasonal_window": "Day 135-180"
    }
  ],
  "confidence_levels": ["high", "medium", "low"],
  "timeframes": ["now", "today", "outlook"]
}
```

---

### Hydrology Endpoints

#### Get Reach Hydrologic Conditions
```
GET /hydrology/reach/{feature_id}
```

Returns hydrologic conditions for a specific stream reach.

**Query Parameters**:
- `timeframe` (optional): `now`, `today`, `outlook`, or `all` (default: `now`)

**Example Request**:
```bash
curl "http://localhost:8000/hydrology/reach/12444119?timeframe=now"
```

**Response Fields**:
- `flow_m3s`: Stream flow in cubic meters per second
- `velocity_ms`: Water velocity in meters per second
- `bdi`: Baseflow Dominance Index (groundwater influence)
- `confidence`: Confidence level and reasoning
- `timestamp`: UTC timestamp (ISO 8601)

---

### Fisheries Intelligence Endpoints

#### Species Habitat Score
```
GET /fisheries/reach/{feature_id}/score
```

Returns habitat suitability score for a specific species.

**Query Parameters**:
- `species` (optional): Species identifier (default: `trout`)
- `timeframe` (optional): `now`, `today`, or `outlook` (default: `now`)

**Example Request**:
```bash
curl "http://localhost:8000/fisheries/reach/12444119/score?species=trout&timeframe=now"
```

**Example Response**:
```json
{
  "feature_id": 12345,
  "species": "Coldwater Trout",
  "overall_score": 0.87,
  "rating": "excellent",
  "components": {
    "flow": 1.0,
    "velocity": 0.95,
    "thermal": 0.0,
    "stability": 0.75
  },
  "explanation": "Excellent habitat for Coldwater Trout. Strengths: flow at 55th percentile (optimal range), suitable velocity (0.60 m/s), stable groundwater-fed conditions (BDI=0.75). (Temperature data not yet integrated - see EPIC 3)",
  "confidence": "high",
  "confidence_reasoning": "High confidence: Using current conditions with data assimilation.",
  "timestamp": "2026-01-04T20:30:00Z",
  "timeframe": "now"
}
```

**Rating Scale**:
- `excellent`: Score >= 0.8
- `good`: Score >= 0.6
- `fair`: Score >= 0.4
- `poor`: Score < 0.4

---

#### Hatch Likelihood Predictions
```
GET /fisheries/reach/{feature_id}/hatches
```

Returns insect hatch likelihood predictions for a specific date and reach.

**Query Parameters**:
- `date` (optional): Date for prediction (ISO format: YYYY-MM-DD, default: today)

**Example Request**:
```bash
curl "http://localhost:8000/fisheries/reach/101/hatches?date=2025-05-25"
```

**Example Response**:
```json
{
  "feature_id": 12345,
  "date": "2025-05-25T00:00:00",
  "hatches": [
    {
      "hatch_name": "Green Drake",
      "scientific_name": "Ephemera guttulata",
      "likelihood": 1.0,
      "rating": "very_likely",
      "in_season": true,
      "hydrologic_match": {
        "flow_percentile": true,
        "rising_limb": true,
        "velocity": true,
        "bdi": true
      },
      "explanation": "All hydrologic conditions favor Green Drake emergence. Favorable: flow at 65th percentile (in preferred range), flow stability suitable, velocity 0.60 m/s (in preferred range), groundwater influence adequate (BDI=0.75)."
    }
  ],
  "generated_at": "2026-01-04T20:30:00Z"
}
```

**Likelihood Ratings**:
- `very_likely`: Likelihood >= 0.75
- `likely`: Likelihood >= 0.5
- `possible`: Likelihood >= 0.25
- `unlikely`: Likelihood < 0.25

---

## Example Usage

### Using cURL

```bash
# Check API health
curl http://localhost:8000/health

# Get available metadata
curl http://localhost:8000/metadata

# Get current hydrologic conditions
curl "http://localhost:8000/hydrology/reach/12345?timeframe=now"

# Get habitat score for trout
curl "http://localhost:8000/fisheries/reach/12345/score?species=trout&timeframe=now"

# Get hatch predictions for specific date
curl "http://localhost:8000/fisheries/reach/12345/hatches?date=2025-05-25"
```

### Using Python

```python
import requests

# Base URL
BASE_URL = "http://localhost:8000"

# Health check
response = requests.get(f"{BASE_URL}/health")
print(response.json())

# Get species score
params = {
    "species": "trout",
    "timeframe": "now"
}
response = requests.get(f"{BASE_URL}/fisheries/reach/12345/score", params=params)
score_data = response.json()
print(f"Habitat Score: {score_data['overall_score']}")
print(f"Rating: {score_data['rating']}")
print(f"Explanation: {score_data['explanation']}")

# Get hatch predictions
params = {"date": "2025-05-25"}
response = requests.get(f"{BASE_URL}/fisheries/reach/12345/hatches", params=params)
hatches = response.json()
for hatch in hatches['hatches']:
    print(f"{hatch['hatch_name']}: {hatch['rating']}")
```

### Using JavaScript (Fetch API)

```javascript
// Base URL
const BASE_URL = 'http://localhost:8000';

// Get species score
async function getHabitatScore(featureId, species = 'trout') {
  const response = await fetch(
    `${BASE_URL}/fisheries/reach/${featureId}/score?species=${species}&timeframe=now`
  );
  const data = await response.json();
  console.log(`Score: ${data.overall_score}`);
  console.log(`Rating: ${data.rating}`);
  console.log(`Explanation: ${data.explanation}`);
  return data;
}

// Get hatch predictions
async function getHatchPredictions(featureId, date) {
  const response = await fetch(
    `${BASE_URL}/fisheries/reach/${featureId}/hatches?date=${date}`
  );
  const data = await response.json();
  return data.hatches;
}

// Usage
getHabitatScore(12345);
getHatchPredictions(12345, '2025-05-25');
```

---

## API Design Principles

### 1. No NWM Complexity Exposed
- No f### folder references
- No raw variable names (qSfcLatRunoff, etc.)
- Clean time abstractions (now/today/outlook)
- User-facing field names (flow_m3s, not streamflow)

### 2. Confidence Everywhere
- Every prediction includes confidence level
- Reasoning provided (why this confidence)
- Transparent uncertainty communication

### 3. Explainability First
- Species scores include explanations
- Hatch predictions explain matches/mismatches
- Component breakdowns for debugging

### 4. RESTful & Standards-Compliant
- Resource-oriented URLs
- HTTP status codes (200, 404, 500)
- ISO 8601 timestamps (UTC)
- JSON responses
- CORS support

---

## Performance

Expected response times:
- **Health check**: <10ms
- **Metadata**: <50ms (scans config files)
- **Species score**: <100ms (database query + computation)
- **Hatch forecast**: <150ms (multiple predictions)

No heavy computation - most work is database I/O.

---

## Production Deployment

### Recommended Enhancements

1. **CORS**: Configure `allow_origins` for specific domains
2. **Rate Limiting**: Add rate limiting middleware
3. **Authentication**: Add API key or OAuth if needed
4. **Caching**: Cache species scores and hatch predictions
5. **Monitoring**: Add Prometheus metrics endpoint
6. **Logging**: Structured logging for errors and requests

### Production Server Command

For production, run with Gunicorn + uvicorn workers:

```bash
gunicorn src.api.main:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  --timeout 120 \
  --access-logfile - \
  --error-logfile -
```

---

## Known Limitations

1. **Simplified Flow Percentile**: Currently uses default 50th percentile; should compute from historical data
2. **Rising Limb Detection Not Integrated**: Placeholder for hatch predictions; requires timeseries analysis
3. **No Caching**: Every request hits database; consider caching scores for ~5 minutes
4. **No Authentication**: Currently open API; add auth when deploying to production
5. **Limited Error Handling**: Basic 404/500 responses; could add more specific error codes

---

## Troubleshooting

### API Won't Start

**Issue**: `ModuleNotFoundError: No module named 'fastapi'`
- **Solution**: Ensure conda environment is activated: `conda activate fnwm`
- **Solution**: Install dependencies: `pip install fastapi uvicorn[standard] sqlalchemy`

**Issue**: `Database connection error`
- **Solution**: Verify `DATABASE_URL` environment variable is set
- **Solution**: Check PostgreSQL is running and accessible

### 404 Errors

**Issue**: Endpoint not found
- **Solution**: Check the endpoint URL matches the documented pattern
- **Solution**: Verify feature_id exists in database

### 500 Errors

**Issue**: Internal server error
- **Solution**: Check server logs for detailed error messages
- **Solution**: Verify database has required data for the feature_id

---

## Support

For issues or questions:
- Check the interactive API docs at `/docs`
- Review the epic-6-completion-summary.md in `docs/development/`
- Check server logs for detailed error messages

---

## Version

**Current Version**: 1.0.0
**Last Updated**: 2026-01-04
