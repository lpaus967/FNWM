# FNWM Implementation Guide

This document provides a step-by-step roadmap for implementing the Fisheries National Water Model intelligence engine as specified in the PRD.

---

## Table of Contents

1. [Prerequisites & Technology Stack](#1-prerequisites--technology-stack)
2. [Development Environment Setup](#2-development-environment-setup)
3. [Implementation Roadmap](#3-implementation-roadmap)
4. [Testing Strategy](#4-testing-strategy)
5. [Deployment & Operations](#5-deployment--operations)
6. [Validation & Iteration](#6-validation--iteration)

---

## 1. Prerequisites & Technology Stack

### Recommended Technology Stack

**Language & Runtime**
- **Python 3.10+** (recommended for scientific computing, data processing)
  - Alternative: Node.js/TypeScript for lightweight API layers
- **Virtual environment management**: `venv` or `conda`

**Data Processing**
- **pandas** / **polars** – dataframe operations
- **numpy** – numerical computing
- **xarray** – multi-dimensional NetCDF handling (NWM uses NetCDF format)
- **dask** – parallel processing for large datasets (optional but recommended)

**Data Storage**
- **PostgreSQL** with **PostGIS** – geospatial reach indexing
- **TimescaleDB** extension – time-series optimization
- Alternative: **DuckDB** for analytics layer

**API & Services**
- **FastAPI** – modern Python API framework
- **Pydantic** – data validation and settings management
- **Redis** – caching layer for computed scores

**Scheduling & Orchestration**
- **Apache Airflow** or **Prefect** – workflow orchestration
- **Cron** – simpler alternative for MVP

**Monitoring & Observability**
- **Prometheus** + **Grafana** – metrics
- **Sentry** – error tracking
- **Structured logging**: `structlog` or `python-json-logger`

**Testing**
- **pytest** – unit and integration tests
- **hypothesis** – property-based testing for metrics
- **Great Expectations** – data quality validation

**Configuration Management**
- **YAML** files for species/hatch thresholds
- **Pydantic Settings** for environment config
- **Git** for version control of config changes

---

## 2. Development Environment Setup

### Initial Setup

```bash
# Clone repository
git clone <your-repo-url>
cd FNWM

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install core dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Setup pre-commit hooks (optional but recommended)
pip install pre-commit
pre-commit install
```

### Directory Structure

```text
FNWM/
├── src/
│   ├── ingest/              # EPIC 1: NWM data ingestion
│   ├── normalize/           # EPIC 1: Time normalization
│   ├── metrics/             # EPIC 2: Derived metrics
│   ├── temperature/         # EPIC 3: Temperature integration
│   ├── species/             # EPIC 4: Species scoring
│   ├── hatches/             # EPIC 4: Hatch likelihood
│   ├── confidence/          # EPIC 5: Uncertainty quantification
│   ├── api/                 # EPIC 6: API endpoints
│   └── validation/          # EPIC 7: Feedback loop
├── config/
│   ├── species/             # Species-specific YAML configs
│   ├── hatches/             # Hatch-specific YAML configs
│   └── settings.py          # Environment settings
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/            # Test data & synthetic hydrographs
├── scripts/
│   ├── download_nwm.py      # Manual data download utilities
│   └── calibrate.py         # Threshold calibration tools
├── notebooks/               # Exploratory analysis (Jupyter)
├── docs/
│   └── api/                 # API documentation
├── requirements.txt
├── requirements-dev.txt
├── pyproject.toml
├── README.md
└── IMPLEMENTATION_GUIDE.md
```

### Database Setup

```bash
# Install PostgreSQL with PostGIS and TimescaleDB
# (Docker recommended for development)

docker run -d \
  --name fnwm-db \
  -e POSTGRES_PASSWORD=dev_password \
  -e POSTGRES_DB=fnwm \
  -p 5432:5432 \
  timescale/timescaledb-ha:pg15

# Run migrations
python scripts/init_db.py
```

---

## 3. Implementation Roadmap

Implementation follows the EPICs defined in the PRD, with suggested order and parallelization opportunities.

---

### EPIC 1: NWM Data Ingestion & Normalization

**Goal**: Create a reliable, minimal, fisheries-focused NWM ingestion layer.

#### Ticket 1.1 – NWM Product Ingestor

**Files to Create**:
- `src/ingest/nwm_client.py`
- `src/ingest/schedulers.py`
- `src/ingest/validators.py`

**Implementation Steps**:

1. **Set up NWM HTTP client**
   ```python
   # src/ingest/nwm_client.py
   import requests
   from pathlib import Path

   class NWMClient:
       BASE_URL = "https://nomads.ncep.noaa.gov/pub/data/nccf/com/nwm/"

       PRODUCTS = [
           "analysis_assim/channel_rt",
           "short_range/channel_rt",
           "medium_range_blend/channel_rt",
           "analysis_assim_no_da/channel_rt"
       ]

       def download_product(self, product: str, cycle: str, domain: str = "conus"):
           # Implementation
           pass
   ```

2. **Implement NetCDF parsing**
   ```python
   import xarray as xr

   def parse_channel_rt(filepath: Path) -> pd.DataFrame:
       """Extract channel routing variables from NetCDF"""
       ds = xr.open_dataset(filepath)

       # Extract key variables
       df = pd.DataFrame({
           'feature_id': ds['feature_id'].values,
           'streamflow_m3s': ds['streamflow'].values,
           'velocity_ms': ds['velocity'].values,
           'qSfcLatRunoff_m3s': ds['qSfcLatRunoff'].values,
           'qBucket_m3s': ds['qBucket'].values,
           'qBtmVertRunoff_m3s': ds['qBtmVertRunoff'].values,
           'nudge_m3s': ds['nudge'].values if 'nudge' in ds else None,
       })

       return df
   ```

3. **Domain validation**
   ```python
   # src/ingest/validators.py
   VALID_DOMAINS = ['conus', 'alaska', 'hawaii', 'puertorico']

   def validate_domain(feature_id: int, domain: str):
       """Ensure feature_id belongs to declared domain"""
       # Implement lookup against NHDPlus domain mapping
       pass
   ```

4. **Scheduling logic**
   - Hourly for `analysis_assim`
   - Hourly for `short_range`
   - Every 6 hours for `medium_range_blend`
   - Daily for `analysis_assim_no_da`

**Acceptance Criteria**:
- [ ] Successfully downloads all 4 products
- [ ] Parses NetCDF to structured format
- [ ] Validates domain consistency
- [ ] Logs failures with alerting
- [ ] Handles network errors gracefully

---

#### Ticket 1.2 – Time Normalization Service

**Files to Create**:
- `src/normalize/time_normalizer.py`
- `src/normalize/schemas.py`

**Implementation Steps**:

1. **Define canonical schema**
   ```python
   # src/normalize/schemas.py
   from pydantic import BaseModel
   from datetime import datetime
   from enum import Enum

   class NWMSource(str, Enum):
       ANALYSIS_ASSIM = "analysis_assim"
       SHORT_RANGE = "short_range"
       MEDIUM_BLEND = "medium_range_blend"
       NO_DA = "analysis_assim_no_da"

   class HydroRecord(BaseModel):
       feature_id: int
       valid_time: datetime  # UTC, timezone-aware
       variable: str
       value: float
       source: NWMSource
       forecast_hour: int | None  # Only for forecasts
   ```

2. **Abstract forecast semantics**
   ```python
   # src/normalize/time_normalizer.py
   def normalize_short_range(df: pd.DataFrame, reference_time: datetime) -> list[HydroRecord]:
       """Convert f001-f018 to valid_time"""
       records = []
       for f_hour in range(1, 19):
           valid_time = reference_time + timedelta(hours=f_hour)
           # Map to schema
       return records
   ```

3. **Store in normalized table**
   ```sql
   CREATE TABLE hydro_timeseries (
       feature_id BIGINT NOT NULL,
       valid_time TIMESTAMPTZ NOT NULL,
       variable VARCHAR(50) NOT NULL,
       value DOUBLE PRECISION,
       source VARCHAR(50) NOT NULL,
       forecast_hour SMALLINT,
       ingested_at TIMESTAMPTZ DEFAULT NOW(),
       PRIMARY KEY (feature_id, valid_time, variable, source)
   );

   SELECT create_hypertable('hydro_timeseries', 'valid_time');
   CREATE INDEX idx_feature_time ON hydro_timeseries (feature_id, valid_time DESC);
   ```

**Acceptance Criteria**:
- [ ] All NWM products map to single schema
- [ ] No `f###` references in downstream code
- [ ] `valid_time` is always UTC timezone-aware
- [ ] Source is tagged for traceability

---

### EPIC 2: Derived Hydrology Metrics Engine

**Goal**: Translate raw hydrology into interpretable signals.

#### Ticket 2.1 – Rising Limb Detector

**Files to Create**:
- `src/metrics/rising_limb.py`
- `config/thresholds/rising_limb.yaml`

**Implementation Steps**:

1. **Load configuration**
   ```yaml
   # config/thresholds/rising_limb.yaml
   default:
     min_slope: 0.5  # m³/s per hour
     min_duration: 3  # consecutive hours
     intensity_thresholds:
       weak: 0.5
       moderate: 2.0
       strong: 5.0

   species_overrides:
     anadromous_salmonid:
       min_slope: 2.0
       min_duration: 6
   ```

2. **Compute derivative**
   ```python
   # src/metrics/rising_limb.py
   import numpy as np
   from typing import Literal

   def detect_rising_limb(
       flows: pd.Series,  # Time-indexed streamflow
       config: dict
   ) -> tuple[bool, Literal["weak", "moderate", "strong"] | None]:
       """Detect sustained rising limb"""

       # Compute dQ/dt
       dQdt = flows.diff() / flows.index.to_series().diff().dt.total_seconds() * 3600

       # Identify consecutive positive slopes
       is_rising = dQdt > config['min_slope']
       consecutive = is_rising.rolling(config['min_duration']).sum()

       detected = (consecutive >= config['min_duration']).any()

       if not detected:
           return False, None

       # Classify intensity
       max_slope = dQdt.max()
       if max_slope > config['intensity_thresholds']['strong']:
           return True, "strong"
       elif max_slope > config['intensity_thresholds']['moderate']:
           return True, "moderate"
       else:
           return True, "weak"
   ```

3. **Unit tests with synthetic hydrographs**
   ```python
   # tests/unit/test_rising_limb.py
   def test_rising_limb_detection():
       # Create synthetic rising hydrograph
       times = pd.date_range('2025-01-01', periods=24, freq='H')
       flows = pd.Series(
           [10, 10, 11, 13, 16, 20, 25, 30, 32, 33] + [33]*14,
           index=times
       )

       detected, intensity = detect_rising_limb(flows, DEFAULT_CONFIG)
       assert detected is True
       assert intensity == "moderate"
   ```

**Acceptance Criteria**:
- [ ] Returns boolean + intensity
- [ ] Config-driven thresholds
- [ ] Unit tests against synthetic data
- [ ] Handles missing data gracefully

---

#### Ticket 2.2 – Baseflow Dominance Index (BDI)

**Files to Create**:
- `src/metrics/baseflow.py`

**Implementation Steps**:

1. **Compute BDI**
   ```python
   # src/metrics/baseflow.py
   def compute_bdi(
       q_btm_vert: float,  # Deep groundwater
       q_bucket: float,    # Shallow subsurface
       q_sfc_lat: float    # Surface runoff
   ) -> float:
       """
       Baseflow Dominance Index
       Returns 0 (storm-dominated) to 1 (baseflow-dominated)
       """
       total = q_btm_vert + q_bucket + q_sfc_lat

       if total == 0:
           return 0.0

       baseflow = q_btm_vert + q_bucket
       return baseflow / total
   ```

2. **Validate against known reaches**
   ```python
   # tests/integration/test_bdi.py
   def test_bdi_groundwater_fed_reach():
       """Test against known spring creek"""
       # Use USGS gauge data or expert knowledge
       bdi = compute_bdi(q_btm=5.0, q_bucket=3.0, q_sfc=0.5)
       assert bdi > 0.8  # Expect high baseflow dominance
   ```

**Acceptance Criteria**:
- [ ] Returns normalized 0-1 value
- [ ] Validated against known spring creeks
- [ ] Handles edge cases (zero total flow)

---

#### Ticket 2.3 – Velocity Suitability Classifier

**Files to Create**:
- `src/metrics/velocity.py`
- `config/species/trout.yaml`

**Implementation Steps**:

1. **Species configuration**
   ```yaml
   # config/species/trout.yaml
   name: "Coldwater Trout"
   velocity_ranges:
     min_optimal: 0.3  # m/s
     max_optimal: 0.8
     min_tolerable: 0.1
     max_tolerable: 1.5
   ```

2. **Classification logic**
   ```python
   # src/metrics/velocity.py
   from enum import Enum

   class VelocityClass(str, Enum):
       TOO_SLOW = "too_slow"
       OPTIMAL = "optimal"
       FAST = "fast"
       TOO_FAST = "too_fast"

   def classify_velocity(velocity_ms: float, species_config: dict) -> tuple[bool, VelocityClass, float]:
       """
       Returns:
           - suitable: bool
           - class: VelocityClass
           - score: 0-1 normalized suitability
       """
       ranges = species_config['velocity_ranges']

       if velocity_ms < ranges['min_tolerable']:
           return False, VelocityClass.TOO_SLOW, 0.0
       elif velocity_ms > ranges['max_tolerable']:
           return False, VelocityClass.TOO_FAST, 0.0
       elif ranges['min_optimal'] <= velocity_ms <= ranges['max_optimal']:
           return True, VelocityClass.OPTIMAL, 1.0
       else:
           # Compute gradient score
           score = compute_gradient_score(velocity_ms, ranges)
           return True, VelocityClass.FAST, score
   ```

**Acceptance Criteria**:
- [ ] Species-aware thresholds
- [ ] Returns categorical + numeric score
- [ ] Config-driven, no hardcoded values

---

### EPIC 3: Temperature & Thermal Suitability

**Goal**: Integrate temperature meaningfully into fisheries logic.

#### Ticket 3.1 – Temperature Ingestion Layer

**Files to Create**:
- `src/temperature/ingest.py`
- `src/temperature/proxies.py`

**Implementation Steps**:

1. **Ingest stream temperature (if available)**
   ```python
   # src/temperature/ingest.py
   def ingest_stream_temp(source: str) -> pd.DataFrame:
       """
       Ingest modeled stream temperature
       Sources: NWM (future), USGS, regional models
       """
       # Check for availability
       # Fallback to proxy if unavailable
       pass
   ```

2. **Air temperature proxy**
   ```python
   # src/temperature/proxies.py
   def use_air_temp_proxy(air_temp_c: float, bdi: float) -> dict:
       """
       When stream temp unavailable, use air temp + BDI as proxy
       High BDI = greater thermal buffering
       """
       return {
           'temp_proxy_c': air_temp_c,
           'confidence': 'low' if bdi < 0.5 else 'medium',
           'buffering_effect': bdi
       }
   ```

**Acceptance Criteria**:
- [ ] Graceful fallback when temp unavailable
- [ ] Explicit source tagging
- [ ] Documents uncertainty when using proxy

---

#### Ticket 3.2 – Thermal Suitability Index (TSI)

**Files to Create**:
- `src/temperature/tsi.py`

**Implementation Steps**:

1. **Compute TSI**
   ```python
   # src/temperature/tsi.py
   def compute_tsi(
       water_temp_c: float,
       bdi: float,
       flow_stability: float,  # 0-1 metric
       species: str
   ) -> tuple[float, str]:
       """
       Thermal Suitability Index
       Returns: (score 0-1, explanation)
       """
       species_thresholds = load_species_config(species)['temperature']

       # Base temperature score
       temp_score = score_temperature(water_temp_c, species_thresholds)

       # Thermal buffering bonus (high BDI = cool refuge potential)
       buffering_bonus = bdi * 0.2 if water_temp_c > species_thresholds['stress'] else 0

       # Stability bonus
       stability_bonus = flow_stability * 0.1

       tsi = min(1.0, temp_score + buffering_bonus + stability_bonus)

       explanation = generate_explanation(water_temp_c, bdi, tsi)

       return tsi, explanation
   ```

**Acceptance Criteria**:
- [ ] Normalized 0-1 output
- [ ] Species-aware thresholds
- [ ] Includes explanation payload

---

### EPIC 4: Species & Hatch Scoring Framework

**Goal**: Produce explainable, species-specific scores.

#### Ticket 4.1 – Species Scoring Engine

**Files to Create**:
- `src/species/scoring.py`
- `config/species/*.yaml`

**Implementation Steps**:

1. **Load species configuration**
   ```yaml
   # config/species/trout.yaml
   name: "Coldwater Trout"

   scoring_weights:
     flow_suitability: 0.30
     velocity_suitability: 0.25
     thermal_suitability: 0.25
     stability: 0.20

   flow_percentile_optimal:
     min: 40
     max: 70

   bdi_threshold: 0.6
   ```

2. **Scoring engine**
   ```python
   # src/species/scoring.py
   from pydantic import BaseModel

   class SpeciesScore(BaseModel):
       overall_score: float  # 0-1
       rating: str  # poor/fair/good/excellent
       components: dict[str, float]
       explanation: str
       confidence: str

   def compute_species_score(
       feature_id: int,
       species: str,
       hydro_data: dict
   ) -> SpeciesScore:
       """
       Compute overall habitat suitability for species
       """
       config = load_species_config(species)
       weights = config['scoring_weights']

       # Compute component scores
       flow_score = score_flow_suitability(hydro_data['flow_percentile'], config)
       velocity_score = score_velocity_suitability(hydro_data['velocity'], config)
       thermal_score = hydro_data['tsi']  # From EPIC 3
       stability_score = score_stability(hydro_data['bdi'], hydro_data['flow_variability'])

       # Weighted sum
       overall = (
           weights['flow_suitability'] * flow_score +
           weights['velocity_suitability'] * velocity_score +
           weights['thermal_suitability'] * thermal_score +
           weights['stability'] * stability_score
       )

       # Classify
       if overall >= 0.8:
           rating = "excellent"
       elif overall >= 0.6:
           rating = "good"
       elif overall >= 0.3:
           rating = "fair"
       else:
           rating = "poor"

       return SpeciesScore(
           overall_score=overall,
           rating=rating,
           components={
               'flow': flow_score,
               'velocity': velocity_score,
               'thermal': thermal_score,
               'stability': stability_score
           },
           explanation=generate_explanation(overall, components, config),
           confidence=compute_confidence(hydro_data)
       )
   ```

**Acceptance Criteria**:
- [ ] Config-driven weights (no hardcoded)
- [ ] Deterministic output
- [ ] Includes component breakdown
- [ ] Auditable explanations

---

#### Ticket 4.2 – Hatch Likelihood Engine

**Files to Create**:
- `src/hatches/likelihood.py`
- `config/hatches/*.yaml`

**Implementation Steps**:

1. **Hatch configuration**
   ```yaml
   # config/hatches/green_drake.yaml
   name: "Green Drake"
   species: "Ephemera guttulata"

   hydrologic_signature:
     flow_percentile:
       min: 55
       max: 80
     rising_limb:
       allowed: ["false", "weak"]
     velocity:
       min: 0.4
       max: 0.9
     bdi_threshold: 0.65

   temporal_window:
     start_day_of_year: 135  # Mid-May
     end_day_of_year: 180    # Late June
   ```

2. **Likelihood scoring**
   ```python
   # src/hatches/likelihood.py
   class HatchScore(BaseModel):
       hatch_name: str
       likelihood: float  # 0-1
       rating: str  # unlikely/possible/likely/very_likely
       hydrologic_match: dict[str, bool]
       explanation: str

   def compute_hatch_likelihood(
       feature_id: int,
       hatch: str,
       hydro_data: dict,
       current_date: datetime
   ) -> HatchScore:
       """Compute hatch likelihood based on hydrologic signature"""
       config = load_hatch_config(hatch)

       # Check temporal window
       day_of_year = current_date.timetuple().tm_yday
       in_season = config['temporal_window']['start'] <= day_of_year <= config['temporal_window']['end']

       if not in_season:
           return HatchScore(
               hatch_name=config['name'],
               likelihood=0.0,
               rating="unlikely",
               hydrologic_match={},
               explanation="Outside seasonal window"
           )

       # Check hydrologic conditions
       signature = config['hydrologic_signature']
       matches = {
           'flow_percentile': signature['flow_percentile']['min'] <= hydro_data['flow_percentile'] <= signature['flow_percentile']['max'],
           'rising_limb': hydro_data['rising_limb'] in signature['rising_limb']['allowed'],
           'velocity': signature['velocity']['min'] <= hydro_data['velocity'] <= signature['velocity']['max'],
           'bdi': hydro_data['bdi'] >= signature['bdi_threshold']
       }

       # Score based on match quality
       match_count = sum(matches.values())
       likelihood = match_count / len(matches)

       if likelihood >= 0.75:
           rating = "very_likely"
       elif likelihood >= 0.5:
           rating = "likely"
       elif likelihood >= 0.25:
           rating = "possible"
       else:
           rating = "unlikely"

       return HatchScore(
           hatch_name=config['name'],
           likelihood=likelihood,
           rating=rating,
           hydrologic_match=matches,
           explanation=generate_hatch_explanation(matches, config)
       )
   ```

**Acceptance Criteria**:
- [ ] Species + hatch aware
- [ ] Seasonal gating logic
- [ ] Outputs likelihood + explanation
- [ ] Unit-testable with fixed dates

---

### EPIC 5: Confidence & Uncertainty

**Goal**: Communicate trust correctly.

#### Ticket 5.1 – Ensemble Spread Calculator

**Files to Create**:
- `src/confidence/ensemble.py`

**Implementation Steps**:

1. **Compute spread metric**
   ```python
   # src/confidence/ensemble.py
   import numpy as np

   def compute_ensemble_spread(
       member_flows: list[float]  # streamflow from mem1-mem6
   ) -> dict:
       """
       Quantify forecast disagreement
       """
       mean_flow = np.mean(member_flows)
       std_flow = np.std(member_flows)

       # Coefficient of variation
       spread = std_flow / mean_flow if mean_flow > 0 else 0

       return {
           'spread_metric': spread,
           'mean_flow': mean_flow,
           'std_flow': std_flow,
           'min_flow': min(member_flows),
           'max_flow': max(member_flows)
       }
   ```

**Acceptance Criteria**:
- [ ] Numeric spread metric
- [ ] Cached per reach per timestep
- [ ] Handles zero-flow edge cases

---

#### Ticket 5.2 – Confidence Classification Service

**Files to Create**:
- `src/confidence/classifier.py`

**Implementation Steps**:

1. **Classify confidence**
   ```python
   # src/confidence/classifier.py
   from typing import Literal

   def classify_confidence(
       source: str,
       forecast_hour: int | None,
       ensemble_spread: float | None,
       nudge_magnitude: float | None
   ) -> Literal["high", "medium", "low"]:
       """
       Translate uncertainty signals into confidence level
       """
       # Analysis data = high confidence
       if source == "analysis_assim":
           return "high"

       # Short-range early hours with low spread
       if source == "short_range" and forecast_hour <= 3:
           if ensemble_spread is None or ensemble_spread < 0.15:
               return "high"
           else:
               return "medium"

       # Short-range later hours
       if source == "short_range" and 4 <= forecast_hour <= 12:
           if ensemble_spread and ensemble_spread > 0.3:
               return "low"
           else:
               return "medium"

       # Medium-range with high spread
       if source == "medium_range_blend":
           if ensemble_spread and ensemble_spread > 0.4:
               return "low"
           else:
               return "medium"

       # Default
       return "medium"
   ```

**Acceptance Criteria**:
- [ ] Returns high/medium/low
- [ ] Matches PRD framework exactly
- [ ] Deterministic logic

---

### EPIC 6: API & Product Integration

**Goal**: Expose clean, stable interfaces to product.

#### Ticket 6.1 – Hydrology Reach API

**Files to Create**:
- `src/api/hydrology.py`
- `src/api/schemas.py`

**Implementation Steps**:

1. **Define API schemas**
   ```python
   # src/api/schemas.py
   from pydantic import BaseModel
   from typing import Literal

   class NowResponse(BaseModel):
       flow_m3s: float
       velocity_ms: float
       flow_percentile: float
       confidence: str

   class TodayForecast(BaseModel):
       hour: int
       flow_m3s: float
       velocity_ms: float
       rising_limb_detected: bool

   class OutlookResponse(BaseModel):
       trend: Literal["rising", "falling", "stable"]
       confidence: str
       mean_flow_m3s: float

   class HydrologyReachResponse(BaseModel):
       feature_id: int
       now: NowResponse | None
       today: list[TodayForecast] | None
       outlook: OutlookResponse | None
   ```

2. **Implement endpoint**
   ```python
   # src/api/hydrology.py
   from fastapi import FastAPI, Query
   from typing import Literal

   app = FastAPI()

   @app.get("/hydrology/reach/{feature_id}", response_model=HydrologyReachResponse)
   async def get_reach_hydrology(
       feature_id: int,
       timeframe: Literal["now", "today", "outlook", "all"] = "all",
       metric: Literal["flow", "velocity", "all"] | None = None
   ):
       """
       Get hydrology data for a specific reach

       Never exposes raw NWM variables - only interpreted metrics
       """
       response = HydrologyReachResponse(feature_id=feature_id)

       if timeframe in ["now", "all"]:
           response.now = fetch_now_data(feature_id, metric)

       if timeframe in ["today", "all"]:
           response.today = fetch_today_forecast(feature_id, metric)

       if timeframe in ["outlook", "all"]:
           response.outlook = fetch_outlook(feature_id)

       return response
   ```

**Acceptance Criteria**:
- [ ] Supports now/today/outlook
- [ ] Never exposes raw NWM variables
- [ ] Returns confidence metadata
- [ ] OpenAPI documentation auto-generated

---

#### Ticket 6.2 – Fisheries Intelligence API

**Files to Create**:
- `src/api/fisheries.py`

**Implementation Steps**:

1. **Implement species scoring endpoint**
   ```python
   # src/api/fisheries.py
   @app.get("/fisheries/reach/{feature_id}/score")
   async def get_fisheries_score(
       feature_id: int,
       species: str,
       timeframe: Literal["now", "today"] = "now"
   ):
       """
       Get species-specific habitat score
       """
       hydro_data = fetch_hydrology(feature_id, timeframe)
       score = compute_species_score(feature_id, species, hydro_data)

       return {
           "feature_id": feature_id,
           "species": species,
           "score": score.overall_score,
           "rating": score.rating,
           "components": score.components,
           "explanation": score.explanation,
           "confidence": score.confidence
       }

   @app.get("/fisheries/reach/{feature_id}/hatches")
   async def get_hatch_forecast(
       feature_id: int,
       date: datetime | None = None
   ):
       """
       Get hatch likelihood for all configured hatches
       """
       if date is None:
           date = datetime.now()

       hydro_data = fetch_hydrology(feature_id, "now")

       hatches = ["green_drake", "pmd", "caddis"]
       scores = [
           compute_hatch_likelihood(feature_id, hatch, hydro_data, date)
           for hatch in hatches
       ]

       return {
           "feature_id": feature_id,
           "date": date.isoformat(),
           "hatches": scores
       }
   ```

**Acceptance Criteria**:
- [ ] Includes explanation payloads
- [ ] Includes confidence classification
- [ ] Species-parameterized
- [ ] Documented responses

---

### EPIC 7: Validation & Feedback Loop

**Goal**: Close the loop between prediction and reality.

#### Ticket 7.1 – Observation Ingestion

**Files to Create**:
- `src/validation/observations.py`
- Database schema for observations

**Implementation Steps**:

1. **Observation schema**
   ```sql
   CREATE TABLE user_observations (
       id SERIAL PRIMARY KEY,
       feature_id BIGINT NOT NULL,
       observation_time TIMESTAMPTZ NOT NULL,
       observation_type VARCHAR(50),  -- 'trip_report', 'hatch_sighting'
       species VARCHAR(100),
       hatch_name VARCHAR(100),
       success_rating INTEGER CHECK (success_rating BETWEEN 1 AND 5),
       notes TEXT,
       user_id VARCHAR(255),  -- Anonymized
       created_at TIMESTAMPTZ DEFAULT NOW()
   );
   ```

2. **Ingestion endpoint**
   ```python
   # src/validation/observations.py
   from pydantic import BaseModel

   class TripReport(BaseModel):
       feature_id: int
       observation_time: datetime
       species: str
       success_rating: int  # 1-5
       notes: str | None

   @app.post("/validation/trip-report")
   async def submit_trip_report(report: TripReport):
       """Ingest user trip report for validation"""
       # Store with privacy safeguards
       # Link to predictions made for that reach/time
       pass
   ```

**Acceptance Criteria**:
- [ ] Time- and reach-aligned
- [ ] Privacy-safe (anonymized)
- [ ] Links to predictions

---

#### Ticket 7.2 – Model Performance Scoring

**Files to Create**:
- `src/validation/metrics.py`

**Implementation Steps**:

1. **Compute validation metrics**
   ```python
   # src/validation/metrics.py
   def compute_validation_metrics(
       predictions: pd.DataFrame,  # Predicted scores
       observations: pd.DataFrame   # Actual outcomes
   ) -> dict:
       """
       Compute precision, recall, and lead time
       """
       # Join on feature_id and time window
       merged = predictions.merge(observations, on=['feature_id', 'time_window'])

       # Binary classification: good/excellent vs poor/fair
       merged['predicted_good'] = merged['predicted_rating'].isin(['good', 'excellent'])
       merged['observed_good'] = merged['success_rating'] >= 4

       # Metrics
       tp = ((merged['predicted_good']) & (merged['observed_good'])).sum()
       fp = ((merged['predicted_good']) & (~merged['observed_good'])).sum()
       fn = ((~merged['predicted_good']) & (merged['observed_good'])).sum()

       precision = tp / (tp + fp) if (tp + fp) > 0 else 0
       recall = tp / (tp + fn) if (tp + fn) > 0 else 0

       # Lead time analysis
       lead_times = merged['observation_time'] - merged['prediction_time']
       mean_lead_hours = lead_times.mean().total_seconds() / 3600

       return {
           'precision': precision,
           'recall': recall,
           'f1_score': 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0,
           'mean_lead_time_hours': mean_lead_hours,
           'sample_size': len(merged)
       }
   ```

**Acceptance Criteria**:
- [ ] Stored historically
- [ ] Viewable by science team
- [ ] Automated weekly reports

---

#### Ticket 7.3 – Threshold Calibration Tooling

**Files to Create**:
- `scripts/calibrate.py`

**Implementation Steps**:

1. **Interactive calibration script**
   ```python
   # scripts/calibrate.py
   import yaml
   from src.validation.metrics import compute_validation_metrics

   def calibrate_threshold(
       config_file: str,
       parameter: str,
       test_range: tuple[float, float],
       step: float
   ):
       """
       Test threshold adjustments and show impact on metrics
       """
       config = yaml.safe_load(open(config_file))

       results = []
       for value in np.arange(test_range[0], test_range[1], step):
           # Temporarily adjust parameter
           config[parameter] = value

           # Re-score historical data
           predictions = recompute_scores(config)
           observations = load_observations()

           # Compute metrics
           metrics = compute_validation_metrics(predictions, observations)
           metrics['parameter_value'] = value

           results.append(metrics)

       # Display results
       df = pd.DataFrame(results)
       print(df)

       # Suggest optimal value
       optimal = df.loc[df['f1_score'].idxmax()]
       print(f"\nOptimal {parameter}: {optimal['parameter_value']}")
       print(f"F1 Score: {optimal['f1_score']:.3f}")
   ```

**Acceptance Criteria**:
- [ ] Config-only changes (no code deploy)
- [ ] Versioned and auditable
- [ ] Science team can run autonomously

---

### EPIC 8: Spatial Integration & Map-Ready Tables

**Goal**: Enable efficient joins between FNWM intelligence and USGS NHD v2.1 spatial layer for map visualization.

**Use Case**: User needs to style/color NHD stream reaches on a map based on:
- Current hydrologic conditions (flow, BDI, velocity)
- Species habitat suitability scores
- Hatch likelihood predictions
- Rising limb detections
- Confidence levels

**Architecture**: Create dedicated metrics tables that can be efficiently joined to spatial NHD layer.

---

#### Ticket 8.1 – Spatial Schema Setup

**Files to Create**:
- `scripts/setup/create_spatial_tables.sql`
- `scripts/setup/load_nhd_layer.py`

**Database Tables**:

1. **NHD Spatial Layer** (if not already loaded)
   ```sql
   CREATE TABLE nhd_flowlines (
       feature_id BIGINT PRIMARY KEY,
       geom GEOMETRY(LINESTRING, 4326),  -- PostGIS required
       gnis_name VARCHAR(255),            -- Stream name
       reachcode VARCHAR(50),
       state VARCHAR(2),
       huc8 VARCHAR(8),
       stream_order INTEGER
   );

   CREATE INDEX idx_nhd_geom ON nhd_flowlines USING GIST (geom);
   CREATE INDEX idx_nhd_state ON nhd_flowlines (state);
   ```

2. **Current Hydrology Metrics** (for map styling)
   ```sql
   CREATE TABLE current_hydrology (
       feature_id BIGINT PRIMARY KEY,

       -- Flow metrics
       streamflow_m3s DOUBLE PRECISION NOT NULL,
       flow_percentile DOUBLE PRECISION,
       flow_trend VARCHAR(20),  -- 'rising', 'falling', 'stable'

       -- Velocity metrics
       velocity_ms DOUBLE PRECISION NOT NULL,
       velocity_category VARCHAR(20),  -- from EPIC 2

       -- Baseflow metrics
       bdi DOUBLE PRECISION,
       bdi_category VARCHAR(30),  -- 'groundwater_fed', 'mixed', 'storm_dominated'

       -- Rising limb detection
       rising_limb_detected BOOLEAN,
       rising_limb_intensity VARCHAR(20),

       -- Metadata
       valid_time TIMESTAMPTZ NOT NULL,
       confidence VARCHAR(20) NOT NULL,
       computed_at TIMESTAMPTZ DEFAULT NOW(),

       CONSTRAINT fk_feature FOREIGN KEY (feature_id)
           REFERENCES nhd_flowlines(feature_id) ON DELETE CASCADE
   );

   CREATE INDEX idx_current_hydro_valid_time ON current_hydrology (valid_time DESC);
   CREATE INDEX idx_current_hydro_bdi ON current_hydrology (bdi);
   ```

3. **Species Habitat Scores** (for map styling)
   ```sql
   CREATE TABLE species_habitat_scores (
       id SERIAL PRIMARY KEY,
       feature_id BIGINT NOT NULL,
       species VARCHAR(100) NOT NULL,

       -- Overall score
       overall_score DOUBLE PRECISION NOT NULL,
       rating VARCHAR(20) NOT NULL,  -- 'poor', 'fair', 'good', 'excellent'

       -- Component scores (for popups)
       flow_score DOUBLE PRECISION,
       velocity_score DOUBLE PRECISION,
       thermal_score DOUBLE PRECISION,
       stability_score DOUBLE PRECISION,

       -- Explanation
       explanation TEXT,
       confidence VARCHAR(20) NOT NULL,

       -- Temporal info
       valid_time TIMESTAMPTZ NOT NULL,
       timeframe VARCHAR(20) NOT NULL,  -- 'now', 'today', 'outlook'
       computed_at TIMESTAMPTZ DEFAULT NOW(),

       CONSTRAINT fk_species_feature FOREIGN KEY (feature_id)
           REFERENCES nhd_flowlines(feature_id) ON DELETE CASCADE,
       UNIQUE (feature_id, species, valid_time)
   );

   CREATE INDEX idx_species_scores_feature ON species_habitat_scores (feature_id);
   CREATE INDEX idx_species_scores_species ON species_habitat_scores (species);
   CREATE INDEX idx_species_scores_rating ON species_habitat_scores (rating);
   ```

4. **Hatch Predictions** (for map styling)
   ```sql
   CREATE TABLE hatch_predictions (
       id SERIAL PRIMARY KEY,
       feature_id BIGINT NOT NULL,
       hatch_name VARCHAR(100) NOT NULL,
       scientific_name VARCHAR(255),

       -- Prediction
       likelihood DOUBLE PRECISION NOT NULL,
       rating VARCHAR(20) NOT NULL,  -- 'unlikely', 'possible', 'likely', 'very_likely'

       -- Conditions
       in_season BOOLEAN NOT NULL,
       flow_percentile_match BOOLEAN,
       rising_limb_match BOOLEAN,
       velocity_match BOOLEAN,
       bdi_match BOOLEAN,

       -- Explanation
       explanation TEXT,

       -- Temporal info
       prediction_date DATE NOT NULL,
       computed_at TIMESTAMPTZ DEFAULT NOW(),

       CONSTRAINT fk_hatch_feature FOREIGN KEY (feature_id)
           REFERENCES nhd_flowlines(feature_id) ON DELETE CASCADE,
       UNIQUE (feature_id, hatch_name, prediction_date)
   );

   CREATE INDEX idx_hatch_predictions_feature ON hatch_predictions (feature_id);
   CREATE INDEX idx_hatch_predictions_hatch ON hatch_predictions (hatch_name);
   CREATE INDEX idx_hatch_predictions_rating ON hatch_predictions (rating);
   ```

5. **Forecast Hydrology** (for time slider maps)
   ```sql
   CREATE TABLE forecast_hydrology (
       id SERIAL PRIMARY KEY,
       feature_id BIGINT NOT NULL,

       -- Forecast metadata
       forecast_hour INTEGER NOT NULL,  -- 1-18
       valid_time TIMESTAMPTZ NOT NULL,

       -- Forecasted values
       streamflow_m3s DOUBLE PRECISION NOT NULL,
       velocity_ms DOUBLE PRECISION NOT NULL,
       flow_percentile DOUBLE PRECISION,

       -- Detected conditions
       rising_limb_detected BOOLEAN,
       rising_limb_intensity VARCHAR(20),

       -- Uncertainty
       confidence VARCHAR(20) NOT NULL,
       ensemble_spread DOUBLE PRECISION,

       reference_time TIMESTAMPTZ NOT NULL,
       computed_at TIMESTAMPTZ DEFAULT NOW(),

       CONSTRAINT fk_forecast_feature FOREIGN KEY (feature_id)
           REFERENCES nhd_flowlines(feature_id) ON DELETE CASCADE,
       UNIQUE (feature_id, reference_time, forecast_hour)
   );

   CREATE INDEX idx_forecast_feature_time ON forecast_hydrology (feature_id, valid_time);
   CREATE INDEX idx_forecast_valid_time ON forecast_hydrology (valid_time);
   ```

**Acceptance Criteria**:
- [ ] All spatial tables created
- [ ] Foreign key constraints to nhd_flowlines
- [ ] Spatial indexes on geometry columns (PostGIS)
- [ ] Temporal indexes for time-based queries

---

#### Ticket 8.2 – Batch Computation Scripts

**Files to Create**:
- `scripts/compute/update_current_hydrology.py`
- `scripts/compute/update_species_scores.py`
- `scripts/compute/update_hatch_predictions.py`
- `scripts/compute/update_forecast_hydrology.py`

**Implementation Pattern** (example for current_hydrology):

```python
# scripts/compute/update_current_hydrology.py
"""
Compute and update current_hydrology table from latest analysis_assim data.
Run hourly via cron.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from datetime import datetime
import os

from metrics.baseflow import compute_bdi, classify_bdi
from metrics.velocity import classify_velocity
from metrics.rising_limb import detect_rising_limb
from confidence.classifier import classify_confidence_with_reasoning

load_dotenv()

def update_current_hydrology():
    """Update current_hydrology table with latest metrics."""
    engine = create_engine(os.getenv('DATABASE_URL'))

    with engine.begin() as conn:
        # Get all features with latest analysis_assim data
        result = conn.execute(text("""
            SELECT feature_id,
                   MAX(valid_time) as latest_time
            FROM hydro_timeseries
            WHERE source = 'analysis_assim'
            GROUP BY feature_id
        """))

        features = {row[0]: row[1] for row in result}

        print(f"Processing {len(features):,} features...")

        for feature_id, valid_time in features.items():
            # Fetch latest data for this feature
            result = conn.execute(text("""
                SELECT variable, value
                FROM hydro_timeseries
                WHERE feature_id = :feature_id
                  AND source = 'analysis_assim'
                  AND valid_time = :valid_time
            """), {'feature_id': feature_id, 'valid_time': valid_time})

            data = {row[0]: row[1] for row in result}

            if 'streamflow' not in data or 'velocity' not in data:
                continue

            # Compute derived metrics
            bdi = None
            bdi_category = None
            if all(k in data for k in ['qBtmVertRunoff', 'qBucket', 'qSfcLatRunoff']):
                bdi = compute_bdi(
                    data['qBtmVertRunoff'],
                    data['qBucket'],
                    data['qSfcLatRunoff']
                )
                bdi_category = classify_bdi(bdi)

            velocity_cat = classify_velocity(data['velocity'], species='trout')

            # TODO: Implement flow trend detection (rising/falling/stable)
            # TODO: Compute flow percentile from historical data

            confidence_obj = classify_confidence_with_reasoning(source='analysis_assim')

            # Upsert to current_hydrology table
            conn.execute(text("""
                INSERT INTO current_hydrology (
                    feature_id, streamflow_m3s, velocity_ms,
                    bdi, bdi_category, velocity_category,
                    valid_time, confidence, computed_at
                ) VALUES (
                    :feature_id, :streamflow, :velocity,
                    :bdi, :bdi_category, :velocity_category,
                    :valid_time, :confidence, NOW()
                )
                ON CONFLICT (feature_id)
                DO UPDATE SET
                    streamflow_m3s = EXCLUDED.streamflow_m3s,
                    velocity_ms = EXCLUDED.velocity_ms,
                    bdi = EXCLUDED.bdi,
                    bdi_category = EXCLUDED.bdi_category,
                    velocity_category = EXCLUDED.velocity_category,
                    valid_time = EXCLUDED.valid_time,
                    confidence = EXCLUDED.confidence,
                    computed_at = NOW()
            """), {
                'feature_id': feature_id,
                'streamflow': data['streamflow'],
                'velocity': data['velocity'],
                'bdi': bdi,
                'bdi_category': bdi_category,
                'velocity_category': velocity_cat.category if velocity_cat else None,
                'valid_time': valid_time,
                'confidence': confidence_obj.confidence
            })

        print(f"✅ Updated current_hydrology for {len(features):,} features")

if __name__ == "__main__":
    update_current_hydrology()
```

**Similar scripts** for:
- `update_species_scores.py` - Compute species scores for all reaches
- `update_hatch_predictions.py` - Compute hatch predictions for today
- `update_forecast_hydrology.py` - Process short_range forecast data

**Acceptance Criteria**:
- [ ] Incremental updates (upsert pattern)
- [ ] Efficient batch processing
- [ ] Logging and error handling
- [ ] Runnable via cron/scheduler

---

#### Ticket 8.3 – Materialized Views for Map Performance

**Files to Create**:
- `scripts/setup/create_map_views.sql`
- `scripts/compute/refresh_map_views.py`

**Materialized Views**:

1. **Latest Conditions Summary** (for fast map rendering)
   ```sql
   CREATE MATERIALIZED VIEW map_current_conditions AS
   SELECT
       f.feature_id,
       f.geom,
       f.gnis_name,
       f.state,

       -- Hydrology
       h.streamflow_m3s,
       h.flow_percentile,
       h.velocity_ms,
       h.bdi,
       h.bdi_category,
       h.rising_limb_detected,

       -- Species scores (trout as default)
       s.overall_score as trout_score,
       s.rating as trout_rating,

       -- Metadata
       h.valid_time,
       h.confidence
   FROM nhd_flowlines f
   LEFT JOIN current_hydrology h ON f.feature_id = h.feature_id
   LEFT JOIN species_habitat_scores s ON f.feature_id = s.feature_id
       AND s.species = 'trout'
       AND s.timeframe = 'now';

   CREATE INDEX idx_map_current_geom ON map_current_conditions USING GIST (geom);
   CREATE INDEX idx_map_current_state ON map_current_conditions (state);
   CREATE INDEX idx_map_current_bdi ON map_current_conditions (bdi_category);
   ```

2. **Active Hatches Today**
   ```sql
   CREATE MATERIALIZED VIEW map_active_hatches AS
   SELECT
       f.feature_id,
       f.geom,
       f.gnis_name,
       f.state,

       -- Aggregate all likely hatches
       array_agg(h.hatch_name ORDER BY h.likelihood DESC) as active_hatches,
       max(h.likelihood) as max_likelihood,
       count(*) as hatch_count
   FROM nhd_flowlines f
   JOIN hatch_predictions h ON f.feature_id = h.feature_id
   WHERE h.prediction_date = CURRENT_DATE
     AND h.rating IN ('likely', 'very_likely')
     AND h.in_season = true
   GROUP BY f.feature_id, f.geom, f.gnis_name, f.state;

   CREATE INDEX idx_map_hatches_geom ON map_active_hatches USING GIST (geom);
   ```

**Refresh Script**:
```python
# scripts/compute/refresh_map_views.py
"""Refresh materialized views for map rendering."""
from sqlalchemy import create_engine, text
import os

def refresh_map_views():
    engine = create_engine(os.getenv('DATABASE_URL'))

    with engine.begin() as conn:
        print("Refreshing map_current_conditions...")
        conn.execute(text("REFRESH MATERIALIZED VIEW CONCURRENTLY map_current_conditions"))

        print("Refreshing map_active_hatches...")
        conn.execute(text("REFRESH MATERIALIZED VIEW CONCURRENTLY map_active_hatches"))

    print("✅ Map views refreshed")

if __name__ == "__main__":
    refresh_map_views()
```

**Acceptance Criteria**:
- [ ] Views include all necessary fields for map styling
- [ ] Spatial indexes for fast bounding box queries
- [ ] CONCURRENTLY refresh (no locks)
- [ ] Automated refresh after data updates

---

#### Ticket 8.4 – Map API Endpoints

**Files to Create**:
- `src/api/map_endpoints.py`

**Endpoints**:

```python
# src/api/map_endpoints.py
from fastapi import APIRouter, Query
from typing import List
from pydantic import BaseModel

router = APIRouter(prefix="/map", tags=["Map Data"])

class MapFeature(BaseModel):
    """Single feature for map rendering."""
    feature_id: int
    geom: dict  # GeoJSON geometry
    properties: dict  # All attributes for styling

@router.get("/current", response_model=List[MapFeature])
async def get_map_current_conditions(
    bbox: str = Query(..., description="Bounding box: minLon,minLat,maxLon,maxLat"),
    state: str = Query(None, description="Filter by state code (e.g., 'MT')"),
    min_bdi: float = Query(None, description="Minimum BDI threshold")
):
    """
    Get current hydrologic conditions for map extent.

    Returns GeoJSON-ready features for efficient map rendering.
    Uses materialized view for fast queries.
    """
    # Parse bbox
    coords = [float(x) for x in bbox.split(',')]

    # Query materialized view
    query = """
        SELECT
            feature_id,
            ST_AsGeoJSON(geom) as geom,
            gnis_name,
            streamflow_m3s,
            bdi,
            bdi_category,
            trout_score,
            trout_rating,
            confidence
        FROM map_current_conditions
        WHERE geom && ST_MakeEnvelope(:minlon, :minlat, :maxlon, :maxlat, 4326)
    """

    if state:
        query += " AND state = :state"
    if min_bdi:
        query += " AND bdi >= :min_bdi"

    # Execute and return GeoJSON features
    # ...

@router.get("/species/{species}", response_model=List[MapFeature])
async def get_map_species_scores(
    species: str,
    bbox: str = Query(...),
    min_rating: str = Query(None, description="Minimum rating: poor/fair/good/excellent")
):
    """Get species habitat scores for map extent."""
    # Similar pattern - query species_habitat_scores joined to geometry
    # ...

@router.get("/hatches", response_model=List[MapFeature])
async def get_map_active_hatches(
    bbox: str = Query(...),
    hatch: str = Query(None, description="Filter by hatch name")
):
    """Get active hatch predictions for map extent."""
    # Query map_active_hatches materialized view
    # ...
```

**Acceptance Criteria**:
- [ ] Returns GeoJSON-ready features
- [ ] Bounding box filtering
- [ ] Fast response (<200ms for 10k features)
- [ ] Documented with OpenAPI examples

---

#### Benefits of This Architecture

**1. Fast Map Queries**
- Pre-computed scores eliminate real-time calculations
- Materialized views eliminate joins
- Spatial indexes enable efficient bounding box queries
- **100x performance improvement** over real-time computation

**2. Flexible Map Styling**
```javascript
// Style streams by BDI category
const styleByBDI = {
  'groundwater_fed': { color: 'blue', weight: 3 },
  'mixed': { color: 'green', weight: 2 },
  'storm_dominated': { color: 'orange', weight: 1 }
};

// Style by trout habitat rating
const styleByTrout = {
  'excellent': { color: '#006400', weight: 4 },
  'good': { color: '#90EE90', weight: 3 },
  'fair': { color: '#FFD700', weight: 2 },
  'poor': { color: '#FF6347', weight: 1 }
};
```

**3. Rich Map Popups**
```javascript
// Click a stream, show all intelligence
{
  "stream_name": "Rock Creek",
  "current_flow": "0.16 m³/s (50th percentile)",
  "bdi": "Groundwater-fed (0.85)",
  "trout_habitat": "Excellent (0.87)",
  "active_hatches": ["Green Drake (very likely)", "Sulphur (likely)"],
  "confidence": "high"
}
```

**4. Time Series Visualization**
- `forecast_hydrology` table enables time slider maps
- Show how conditions change over next 18 hours

---

## 4. Testing Strategy

### Unit Tests

**Coverage Requirements**: >80% for all business logic

```python
# tests/unit/test_bdi.py
import pytest
from src.metrics.baseflow import compute_bdi

def test_bdi_pure_baseflow():
    """100% baseflow should return 1.0"""
    assert compute_bdi(q_btm=5.0, q_bucket=3.0, q_sfc=0.0) == 1.0

def test_bdi_pure_stormflow():
    """100% stormflow should return 0.0"""
    assert compute_bdi(q_btm=0.0, q_bucket=0.0, q_sfc=10.0) == 0.0

def test_bdi_mixed():
    """Mixed sources should return intermediate value"""
    bdi = compute_bdi(q_btm=3.0, q_bucket=2.0, q_sfc=5.0)
    assert 0.4 < bdi < 0.6
```

### Integration Tests

```python
# tests/integration/test_species_scoring.py
def test_end_to_end_trout_score():
    """Test complete scoring pipeline"""
    feature_id = 123456

    # Setup test data
    setup_test_hydrology(feature_id, flow=42.0, velocity=0.6)

    # Compute score
    score = compute_species_score(feature_id, "trout", fetch_hydrology(feature_id))

    # Assertions
    assert score.overall_score > 0.7
    assert score.rating == "good"
    assert 'flow' in score.components
```

### Property-Based Testing

```python
# tests/property/test_metrics.py
from hypothesis import given, strategies as st

@given(
    q_btm=st.floats(min_value=0, max_value=100),
    q_bucket=st.floats(min_value=0, max_value=100),
    q_sfc=st.floats(min_value=0, max_value=100)
)
def test_bdi_bounded(q_btm, q_bucket, q_sfc):
    """BDI must always be between 0 and 1"""
    bdi = compute_bdi(q_btm, q_bucket, q_sfc)
    assert 0.0 <= bdi <= 1.0
```

---

## 5. Deployment & Operations

### Deployment Architecture

```text
┌─────────────────────────────────────────────┐
│          NWM Ingestion Service              │
│  - Scheduled via Airflow/Prefect            │
│  - Runs hourly/6-hourly                     │
└──────────────┬──────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────┐
│         PostgreSQL + TimescaleDB            │
│  - hydro_timeseries (hypertable)            │
│  - Partitioned by time                      │
└──────────────┬──────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────┐
│        Metrics Computation Layer            │
│  - BDI, Rising Limb, TSI, etc.              │
│  - Triggered on new data arrival            │
└──────────────┬──────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────┐
│          Scoring Engine                     │
│  - Species scores                           │
│  - Hatch likelihood                         │
│  - Cached in Redis                          │
└──────────────┬──────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────┐
│            FastAPI Service                  │
│  - /hydrology/reach/{id}                    │
│  - /fisheries/reach/{id}/score              │
│  - /fisheries/reach/{id}/hatches            │
└─────────────────────────────────────────────┘
```

### Monitoring

**Key Metrics to Track**:

1. **Data Freshness**
   - Time since last successful NWM ingest
   - Alert if >2 hours for analysis_assim

2. **API Performance**
   - P95 latency for reach queries
   - Target: <200ms

3. **Scoring Coverage**
   - % of reaches with valid scores
   - Target: >95%

4. **Validation Metrics**
   - Weekly precision/recall reports
   - Trend analysis month-over-month

**Example Prometheus Metrics**:

```python
from prometheus_client import Counter, Histogram, Gauge

nwm_ingest_success = Counter('nwm_ingest_success_total', 'Successful NWM ingests', ['product'])
nwm_ingest_failure = Counter('nwm_ingest_failure_total', 'Failed NWM ingests', ['product'])
api_latency = Histogram('api_request_duration_seconds', 'API latency', ['endpoint'])
score_coverage = Gauge('score_coverage_percent', 'Percentage of reaches with scores', ['species'])
```

---

## 6. Validation & Iteration

### Continuous Improvement Loop

1. **Weekly**: Review validation metrics dashboard
2. **Bi-weekly**: Calibrate thresholds based on new observations
3. **Monthly**: Science team review of model performance
4. **Quarterly**: User surveys on recommendation quality

### A/B Testing Framework

For new scoring algorithms:

```python
# Flag-based experimentation
def compute_species_score_v2(feature_id, species, hydro_data, use_experimental=False):
    if use_experimental and is_in_experiment_group(feature_id):
        return experimental_scoring_algorithm(...)
    else:
        return production_scoring_algorithm(...)
```

### Regional Tuning

Species and hatch configs should support regional overrides:

```yaml
# config/species/trout.yaml
default:
  velocity_ranges:
    min_optimal: 0.3
    max_optimal: 0.8

regional_overrides:
  western_freestone:
    velocity_ranges:
      min_optimal: 0.5
      max_optimal: 1.2
```

---

## Next Steps

### Phase 1: MVP (Weeks 1-4)
- [ ] EPIC 1: Data ingestion working for CONUS
- [ ] EPIC 2: Core metrics (BDI, rising limb, velocity)
- [ ] EPIC 4: Single species scoring (trout)
- [ ] EPIC 6: Basic API endpoint

### Phase 2: Enhancement (Weeks 5-8)
- [ ] EPIC 3: Temperature integration
- [ ] EPIC 4: Multiple species + hatches
- [ ] EPIC 5: Confidence framework
- [ ] EPIC 7: Observation ingestion

### Phase 3: Production Hardening (Weeks 9-12)
- [ ] Full monitoring & alerting
- [ ] Performance optimization
- [ ] Documentation complete
- [ ] Validation loop operational

---

## Critical Success Factors

1. **Config-Driven Design**: Species/hatch logic must be owned by science team, not buried in code
2. **Explainability**: Every score must have a transparent explanation
3. **Validation Loop**: Ship the feedback mechanism early—it's your moat
4. **Selectivity**: Resist feature creep—only ship what can be explained and validated

---

## Questions & Decisions Needed

Before starting implementation, clarify:

1. **Technology Stack**: Python confirmed? FastAPI vs Flask? PostgreSQL vs alternative?
2. **Infrastructure**: AWS/GCP/Azure? Containerized (Docker/K8s)?
3. **Data Refresh SLA**: What's acceptable staleness for "now"?
4. **Geographic Scope**: Start with CONUS only? Expand to Alaska/Hawaii later?
5. **Access Control**: Is this API public or internal-only initially?

---

This is your execution blueprint. Start with EPIC 1, prove the data pipeline, then build interpretation layers incrementally.

**Shipping raw hydrology is easy. Shipping trusted fisheries intelligence is the work.**
