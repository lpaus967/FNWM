# Map Export Guide - EPIC 8

This guide covers how to use the `map_current_conditions` materialized view and GeoJSON export functionality.

## Overview

**EPIC 8: Spatial Integration & Map-Ready Tables** enables efficient map rendering by combining:
- NHD flowline geometry (spatial data)
- Latest hydrology metrics (flow, velocity, BDI)
- Flow percentiles (computed from historical data)
- Confidence classification

This allows you to:
1. Export current conditions as GeoJSON for web mapping
2. Style streams by hydrology conditions
3. Create interactive map popups with rich data
4. Filter and query efficiently

## Quick Start

### 1. Create the Materialized View

```bash
# Initialize the view (first time only)
python scripts/setup/init_map_view.py
```

This creates the `map_current_conditions` view combining all spatial and hydrology data.

### 2. Export as GeoJSON

```bash
# Export all reaches
python scripts/production/export_map_geojson.py

# Export with filters
python scripts/production/export_map_geojson.py --min-bdi 0.7
python scripts/production/export_map_geojson.py --bdi-category groundwater_fed
python scripts/production/export_map_geojson.py --min-percentile 50 --max-percentile 75

# Custom output location
python scripts/production/export_map_geojson.py -o my_export.geojson
```

### 3. Refresh After Data Updates

After ingesting new NWM data, refresh the view:

```sql
-- In PostgreSQL
SELECT refresh_map_current_conditions();
```

Or use the refresh script:

```bash
python scripts/production/refresh_map_view.py
```

## Data Structure

### Materialized View Schema

The `map_current_conditions` view includes:

**Spatial Data:**
- `feature_id` - NHDPlusID
- `geom` - PostGIS geometry (LineString)
- `gnis_name` - Stream name
- `reachcode` - NHD reach code
- `drainage_area_sqkm` - Watershed area
- `slope`, `stream_order`, `gradient_class`, `size_class`

**Hydrology Metrics:**
- `streamflow` - Current flow (m³/s)
- `velocity` - Current velocity (m/s)
- `qBtmVertRunoff`, `qBucket`, `qSfcLatRunoff` - Flow components
- `nudge` - Data assimilation nudge value

**Derived Metrics:**
- `bdi` - Baseflow Dominance Index (0-1)
- `bdi_category` - Classification (groundwater_fed/mixed/storm_dominated)
- `flow_percentile` - Flow percentile (0-100)
- `flow_percentile_category` - Classification (extreme_low to extreme_high)
- `monthly_mean` - Historical monthly mean flow

**Metadata:**
- `valid_time` - Timestamp of data
- `source` - NWM product (analysis_assim, etc.)
- `confidence` - Data confidence (high/medium/low)

## GeoJSON Export Options

### Filter by BDI

```bash
# Groundwater-fed streams only
python scripts/production/export_map_geojson.py --bdi-category groundwater_fed

# High BDI streams (> 0.7)
python scripts/production/export_map_geojson.py --min-bdi 0.7
```

### Filter by Flow

```bash
# Low flow conditions
python scripts/production/export_map_geojson.py --max-percentile 25

# High flow conditions
python scripts/production/export_map_geojson.py --min-percentile 75

# Normal flow range
python scripts/production/export_map_geojson.py --min-percentile 40 --max-percentile 60
```

### Filter by Stream Name

```bash
# Find specific stream
python scripts/production/export_map_geojson.py --stream-name "Rock Creek"

# Partial match works
python scripts/production/export_map_geojson.py --stream-name "Creek"
```

### Limit Results

```bash
# Export first 100 features (for testing)
python scripts/production/export_map_geojson.py --limit 100
```

## Using GeoJSON in Web Maps

### Leaflet Example

```javascript
// Load GeoJSON
fetch('map_current_conditions.geojson')
  .then(response => response.json())
  .then(data => {
    // Style by BDI category
    const bdiStyles = {
      'groundwater_fed': { color: 'blue', weight: 3 },
      'mixed': { color: 'green', weight: 2 },
      'storm_dominated': { color: 'orange', weight: 1 }
    };

    L.geoJSON(data, {
      style: feature => bdiStyles[feature.properties.bdi_category] || { color: 'gray' },
      onEachFeature: (feature, layer) => {
        const props = feature.properties;
        layer.bindPopup(`
          <h3>${props.stream_name || 'Unnamed Stream'}</h3>
          <p><strong>Flow:</strong> ${props.streamflow_m3s.toFixed(2)} m³/s
             (${props.flow_percentile.toFixed(0)}th percentile - ${props.flow_percentile_category})</p>
          <p><strong>BDI:</strong> ${props.bdi.toFixed(2)} (${props.bdi_category})</p>
          <p><strong>Velocity:</strong> ${props.velocity_ms.toFixed(2)} m/s</p>
          <p><strong>Confidence:</strong> ${props.confidence}</p>
        `);
      }
    }).addTo(map);
  });
```

### Mapbox GL JS Example

```javascript
map.addSource('streams', {
  type: 'geojson',
  data: 'map_current_conditions.geojson'
});

// Style by flow percentile
map.addLayer({
  id: 'streams',
  type: 'line',
  source: 'streams',
  paint: {
    'line-color': [
      'case',
      ['<', ['get', 'flow_percentile'], 25], '#d7191c',  // Low (red)
      ['<', ['get', 'flow_percentile'], 75], '#2b83ba',  // Normal (blue)
      '#1a9850'  // High (green)
    ],
    'line-width': [
      'interpolate',
      ['linear'],
      ['get', 'drainage_area_sqkm'],
      0, 1,
      100, 3,
      1000, 5
    ]
  }
});
```

## Performance Optimization

### View Refresh Strategy

The materialized view improves query performance by pre-computing joins and metrics. Refresh strategies:

**Real-time applications:**
```sql
-- Refresh after each data ingestion
SELECT refresh_map_current_conditions();
```

**Scheduled refresh (recommended):**
```bash
# Add to cron (refresh every hour)
0 * * * * cd /path/to/FNWM && python scripts/production/refresh_map_view.py
```

**Manual refresh:**
```bash
# When needed
python scripts/production/refresh_map_view.py
```

### Query Performance

The view includes spatial indexes for fast bounding box queries:

```sql
-- Get streams in map extent (very fast with GIST index)
SELECT *
FROM map_current_conditions
WHERE geom && ST_MakeEnvelope(-112.5, 46.8, -112.0, 47.0, 4326);
```

Typical performance:
- Full view creation: ~5-10 seconds
- Refresh: ~5-10 seconds
- Bounding box query: <100ms
- GeoJSON export (all features): ~10-30 seconds
- GeoJSON export (filtered): <5 seconds

## Use Cases

### 1. Stream Conditions Dashboard

Export current conditions and render on a map showing:
- Blue = groundwater-fed (stable conditions)
- Green = mixed hydrology
- Orange = storm-dominated (flashy conditions)

```bash
python scripts/production/export_map_geojson.py -o dashboard.geojson
```

### 2. Fishing Condition Map

Highlight optimal fishing conditions (normal flows in groundwater-fed streams):

```bash
python scripts/production/export_map_geojson.py \
  --min-percentile 40 \
  --max-percentile 60 \
  --min-bdi 0.6 \
  -o fishing_conditions.geojson
```

### 3. Drought Monitoring

Find streams with low flow conditions:

```bash
python scripts/production/export_map_geojson.py \
  --max-percentile 25 \
  -o drought_streams.geojson
```

### 4. Flood Watch

Identify streams at high flow:

```bash
python scripts/production/export_map_geojson.py \
  --min-percentile 90 \
  -o flood_watch.geojson
```

## Database Queries

### Direct SQL Queries

Query the view directly for custom analysis:

```sql
-- Top 10 highest flow streams right now
SELECT
    gnis_name,
    streamflow,
    flow_percentile,
    flow_percentile_category
FROM map_current_conditions
ORDER BY streamflow DESC
LIMIT 10;

-- Groundwater-fed streams with normal flow
SELECT
    gnis_name,
    bdi,
    flow_percentile
FROM map_current_conditions
WHERE bdi_category = 'groundwater_fed'
  AND flow_percentile_category = 'normal';

-- Count by BDI category
SELECT
    bdi_category,
    COUNT(*) as count,
    AVG(streamflow) as avg_flow,
    AVG(flow_percentile) as avg_percentile
FROM map_current_conditions
GROUP BY bdi_category;
```

## Troubleshooting

### View is Empty

```sql
-- Check if hydrology data exists
SELECT COUNT(*) FROM hydro_timeseries WHERE source = 'analysis_assim';

-- Check if NHD data is loaded
SELECT COUNT(*) FROM nhd_flowlines;

-- Check if flow statistics are loaded
SELECT COUNT(*) FROM nhd_flow_statistics;
```

### Flow Percentiles Missing

Flow percentiles require:
1. NWM streamflow data (from `hydro_timeseries`)
2. NHD flow statistics (from `nhd_flow_statistics`)
3. Current month must be January-June (NHD data limitation)

```sql
-- Check what month data is available
SELECT DISTINCT EXTRACT(MONTH FROM valid_time) as month
FROM map_current_conditions;
```

### Performance Issues

If the view is slow:

```sql
-- Reindex
REINDEX INDEX idx_map_current_geom;
REINDEX INDEX idx_map_current_feature;

-- Analyze table
ANALYZE map_current_conditions;

-- Check view size
SELECT pg_size_pretty(pg_total_relation_size('map_current_conditions'));
```

## Advanced Workflows

### Automated Export Pipeline

```bash
#!/bin/bash
# scripts/workflows/export_daily_maps.sh

# Refresh view
python scripts/production/refresh_map_view.py

# Export multiple variants
python scripts/production/export_map_geojson.py \
  -o exports/all_streams_$(date +%Y%m%d).geojson

python scripts/production/export_map_geojson.py \
  --bdi-category groundwater_fed \
  -o exports/groundwater_$(date +%Y%m%d).geojson

python scripts/production/export_map_geojson.py \
  --min-percentile 75 \
  -o exports/high_flow_$(date +%Y%m%d).geojson
```

### Integration with API

Serve GeoJSON directly via FastAPI:

```python
# src/api/map_endpoints.py (future enhancement)

@app.get("/map/current", response_class=ORJSONResponse)
async def get_map_current_conditions(
    bbox: str = Query(None),
    min_bdi: float = Query(None),
    limit: int = Query(1000)
):
    """Return GeoJSON for map rendering."""
    # Query map_current_conditions view
    # Apply filters
    # Return as GeoJSON
    pass
```

## Next Steps

After setting up map exports, consider:

1. **Species Scoring View**: Create `map_species_scores` combining habitat scores with geometry
2. **Hatch Predictions View**: Create `map_hatch_predictions` for hatch likelihood maps
3. **Forecast Views**: Create time-series views for "today" and "outlook" timeframes
4. **Map API**: Build REST endpoints for dynamic map tile serving

See `docs/guides/implementation.md` for complete EPIC 8 implementation details.
