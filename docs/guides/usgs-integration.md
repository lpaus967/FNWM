# USGS Water Services Integration Guide

**Last Updated:** 2026-01-08

This guide covers the integration of USGS real-time gage data into the FNWM system for validation and ground truth observations.

---

## Overview

The USGS integration provides:
- Real-time streamflow observations from USGS monitoring stations
- Spatial mapping of gages to NHD stream reaches
- Automated validation of NWM predictions against observed data
- Statistical performance metrics for model accuracy assessment

**Key Components:**
- USGS Water Services API client
- Database tables for gage locations and observations
- NWM-USGS validation engine
- Automated ingestion and validation pipeline

---

## Architecture

### Data Flow

```
USGS Water Services API
         ↓
    API Client
         ↓
  USGS_Flowsites (table)      ← Gage locations
         ↓
usgs_instantaneous_values     ← 15-min observations
         ↓
    Spatial Mapping
         ↓
  NHD Flowlines (100m buffer)
         ↓
    Validation Engine
         ↓
nwm_usgs_validation           ← Performance metrics
```

### Database Schema

**Tables:**
1. **USGS_Flowsites** - Gage site metadata and locations
   - Site ID, name, coordinates
   - Agency information (USGS, NOAA ID)
   - PostGIS point geometry

2. **usgs_instantaneous_values** - Time-series observations
   - 15-minute interval measurements
   - Discharge (ft³/s), gage height (ft), water temp (°C)
   - Quality flags (provisional/approved)

3. **nwm_usgs_validation** - Validation metrics
   - Correlation, RMSE, MAE, bias
   - Nash-Sutcliffe Efficiency
   - Performance ratings

**Materialized Views:**
- `usgs_latest_readings` - Quick access to current conditions
- `latest_validation_results` - Most recent validation metrics

---

## Setup

### 1. Initialize USGS Gage Sites

Load USGS gage locations from GeoJSON:

```bash
python scripts/setup/init_usgs_flowsites.py [path_to_geojson]
```

**Default path:** `D:\Personal Projects\FNWM\Testing\Guages\usgsGuageTest.geojson`

This creates:
- USGS_Flowsites table
- Spatial indexes
- Foreign key constraints

**Sample output:**
```
Found 7 features to load
✅ Loaded 7 features successfully

Sample records:
  - EF OF SF SALMON RIVER AT STIBNITE, ID (13311000) in Idaho
  - JOHNSON CREEK AT YELLOW PINE ID (13313000) in Idaho
```

### 2. Create Data Tables

Initialize tables for storing observations and validation results:

```bash
python scripts/setup/init_usgs_data_table.py
python scripts/setup/init_validation_table.py
```

This creates:
- `usgs_instantaneous_values` - Observations storage
- `usgs_latest_readings` - Materialized view
- `nwm_usgs_validation` - Validation results
- `latest_validation_results` - Materialized view
- `validation_summary` - Performance summary view

---

## USGS Water Services API

### API Overview

**Base URL:** `https://waterservices.usgs.gov/nwis/iv/`

**Key Features:**
- Real-time instantaneous values (15-minute intervals)
- Multiple parameters (discharge, gage height, temperature)
- JSON response format
- Up to 100 sites per request

### Parameter Codes

| Code | Parameter | Unit |
|------|-----------|------|
| 00060 | Discharge (streamflow) | ft³/s |
| 00065 | Gage height (water level) | feet |
| 00010 | Water temperature | °C |
| 00095 | Specific conductance | µS/cm |
| 00300 | Dissolved oxygen | mg/L |

### Example Request

```
GET https://waterservices.usgs.gov/nwis/iv/?sites=13311000,13313000&parameterCd=00060,00065&format=json
```

Returns current discharge and gage height for two sites.

### Client Usage

```python
from src.usgs.client import USGSClient, ParameterCodes

# Initialize client
client = USGSClient()

# Fetch current conditions
results = client.fetch_current_conditions(
    site_ids=['13311000', '13313000'],
    parameter_codes=[ParameterCodes.DISCHARGE, ParameterCodes.GAGE_HEIGHT]
)

# Process results
for result in results:
    if result.success:
        for reading in result.data:
            print(f"{reading.parameter_name}: {reading.value} {reading.unit}")
            print(f"Time: {reading.datetime}")
            print(f"Provisional: {reading.is_provisional}")
```

---

## Data Ingestion

### Manual Ingestion

Run the USGS ingestion script to fetch and store current conditions:

```bash
python scripts/production/ingest_usgs_data.py
```

**Process:**
1. Queries database for enabled USGS sites
2. Fetches current conditions from USGS API
3. Stores observations in `usgs_instantaneous_values`
4. Refreshes materialized views
5. Displays summary statistics

**Sample output:**
```
Sites queried: 7
Successful: 7
Failed: 0
Total readings fetched: 19

Top 5 Sites by Discharge:
13310700       488.00 ft3/s  Provisional     2026-01-09 00:45 UTC
13313000       199.00 ft3/s  Provisional     2026-01-09 00:00 UTC
```

### Automated Ingestion

USGS ingestion is integrated into the main NWM workflow:

```bash
python scripts/dev/run_subset_ingestion.py
```

This workflow:
1. Ingests NWM channel routing data
2. Ingests USGS gage observations
3. Runs NWM-USGS validation
4. Stores validation metrics

**Recommended Schedule:**
- Hourly ingestion (USGS updates hourly)
- Validation after each NWM ingestion cycle

---

## Validation Framework

### Spatial Mapping

USGS gages are spatially mapped to NHD flowlines:

```sql
SELECT DISTINCT
    usgs."siteId" as usgs_site_id,
    nhd.nhdplusid,
    ST_Distance(usgs.geom::geography, nhd.geom::geography) as distance_m
FROM "USGS_Flowsites" usgs
CROSS JOIN LATERAL (
    SELECT nhdplusid, geom
    FROM nhd_flowlines
    WHERE ST_DWithin(usgs.geom::geography, geom::geography, 100)
    ORDER BY ST_Distance(usgs.geom::geography, geom::geography)
    LIMIT 1
) nhd;
```

**Criteria:**
- Gages must be within 100 meters of an NHD flowline
- Closest flowline is selected

### Validation Metrics

The validation engine compares NWM predictions with USGS observations:

**Metrics Calculated:**

1. **Pearson Correlation (R)**
   - Range: -1 to 1
   - Interpretation: 1.0 = perfect positive correlation

2. **RMSE (Root Mean Square Error)**
   - Units: ft³/s
   - Interpretation: Lower is better, represents average prediction error

3. **MAE (Mean Absolute Error)**
   - Units: ft³/s
   - Interpretation: Average magnitude of errors

4. **Bias**
   - Units: ft³/s
   - Interpretation: Positive = overestimate, negative = underestimate

5. **Percent Bias**
   - Units: %
   - Interpretation: Relative bias as percentage

6. **Nash-Sutcliffe Efficiency (NSE)**
   - Range: -∞ to 1
   - Interpretation:
     - 1.0 = perfect match
     - 0.0 = model as good as using mean
     - < 0 = worse than mean

**Performance Ratings (based on NSE):**
- Excellent: NSE > 0.75
- Very Good: NSE 0.65-0.75
- Good: NSE 0.50-0.65
- Satisfactory: NSE 0.40-0.50
- Unsatisfactory: NSE < 0.40

### Running Validation

**Standalone validation:**

```bash
python scripts/tests/test_validation.py
```

**Programmatic usage:**

```python
from src.validation.nwm_usgs_validator import NWMUSGSValidator
from datetime import datetime, timedelta, timezone

# Initialize validator
validator = NWMUSGSValidator(database_url)

# Set validation period
end_time = datetime.now(timezone.utc)
start_time = end_time - timedelta(days=7)

# Run validation
results = validator.validate_all_sites(
    start_time=start_time,
    end_time=end_time,
    nwm_product='analysis_assim'
)

# Process results
for metrics in results:
    print(f"Site {metrics.site_id}:")
    print(f"  Correlation: {metrics.correlation:.3f}")
    print(f"  RMSE: {metrics.rmse:.2f} cfs")
    print(f"  Nash-Sutcliffe: {metrics.nash_sutcliffe:.3f}")
```

---

## Querying Validation Results

### Latest Results

```sql
SELECT
    site_id,
    site_name,
    correlation,
    rmse,
    nash_sutcliffe,
    performance_rating
FROM latest_validation_results
ORDER BY nash_sutcliffe DESC;
```

### Overall Performance Summary

```sql
SELECT
    nwm_product,
    sites_validated,
    avg_correlation,
    avg_rmse,
    avg_nash_sutcliffe,
    last_validation
FROM validation_summary;
```

### Historical Validation Trends

```sql
SELECT
    site_id,
    validation_start,
    validation_end,
    nash_sutcliffe,
    correlation,
    rmse
FROM nwm_usgs_validation
WHERE site_id = '13311000'
ORDER BY validated_at DESC
LIMIT 10;
```

---

## Current Gage Network

**Active Sites:** 7

| Site ID | Name | State | NOAA ID |
|---------|------|-------|---------|
| 13310700 | SF Salmon River nr Krassel | Idaho | KRSI1 |
| 13310800 | EFSF Salmon R abv Meadow Crk | Idaho | - |
| 13310850 | Meadow Creek nr Stibnite | Idaho | - |
| 13311000 | EF of SF Salmon River at Stibnite | Idaho | SFSI1 |
| 13311250 | EFSF Salmon R abv Sugar Crk | Idaho | - |
| 13311450 | Sugar Creek nr Stibnite | Idaho | SUGI1 |
| 13313000 | Johnson Creek at Yellow Pine | Idaho | JOHI1 |

**Data Coverage:**
- All sites: Discharge (00060), Gage Height (00065)
- 5 of 7 sites: Water Temperature (00010)

---

## API Integration

### Available Endpoints (Planned)

Future API endpoints will expose validation metrics:

```
GET /validation/summary
  - Overall model performance metrics

GET /validation/site/{site_id}
  - Historical validation for specific gage

GET /validation/recent
  - Latest validation results across all sites
```

---

## Troubleshooting

### No Validation Results

**Possible causes:**
1. No NHD data loaded
   ```bash
   python scripts/production/load_nhd_data.py <geojson_path>
   ```

2. No USGS sites mapped to NHD
   - Check spatial proximity (must be within 100m)
   - Verify USGS_Flowsites and nhd_flowlines tables have data

3. Insufficient paired observations
   - Need at least 5 matching timestamps
   - Check that NWM and USGS data overlap in time

### USGS API Errors

**Rate limiting:**
- USGS API may throttle excessive requests
- Use batch requests (up to 100 sites)
- Add retry logic (built into client)

**Site data unavailable:**
- Some sites may be offline or inactive
- Check `isEnabled` flag in USGS_Flowsites
- Verify site ID is correct

---

## Best Practices

1. **Regular Ingestion**
   - Run USGS ingestion hourly to keep data fresh
   - USGS updates data every hour

2. **Validation Cadence**
   - Run validation after each NWM ingestion
   - Store historical validation metrics for trend analysis

3. **Data Quality**
   - Check `is_provisional` flag
   - Provisional data may be revised
   - Use approved data for critical decisions

4. **Performance Monitoring**
   - Monitor NSE trends over time
   - Alert on significant degradation
   - Investigate sites with NSE < 0.4

5. **Spatial Coverage**
   - Expand gage network over time
   - Target gages near high-value fishing locations
   - Ensure geographic diversity

---

## Future Enhancements

**Planned:**
- Expanded gage network (beyond Idaho)
- Real-time validation dashboards
- Alert system for poor model performance
- Automated model recalibration based on validation
- Integration with user trip reports
- Hatch observation validation

**Under Consideration:**
- Alternative validation data sources (SNOTEL, local agencies)
- Forecasted discharge validation (not just analysis)
- Validation of derived metrics (not just raw discharge)

---

## References

**USGS Resources:**
- Water Services API Documentation: https://waterservices.usgs.gov/docs/
- Instantaneous Values Service: https://waterservices.usgs.gov/docs/instantaneous-values/
- Site Information Service: https://waterservices.usgs.gov/docs/site-service/

**Academic References:**
- Moriasi et al. (2007) - Model evaluation guidelines
- Nash & Sutcliffe (1970) - NSE coefficient
- Krause et al. (2005) - Comparison of model performance metrics

**Related Documentation:**
- [NHD Integration Guide](nhd-integration.md) - Spatial data setup
- [Project Status](../development/project-status.md) - Current implementation status
- [NWM Product Schedules](nwm-product-schedules.md) - NWM ingestion timing
