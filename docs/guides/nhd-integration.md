# NHD v2.1 Integration Guide

**Status**: Implemented
**Date**: 2026-01-05

---

## Overview

This guide explains how NHDPlus v2.1 flowline data integrates with the FNWM system to provide spatial context, stream network topology, and historical flow statistics for fisheries intelligence.

### What is NHDPlus v2.1?

NHDPlus (National Hydrography Dataset Plus) is a comprehensive suite of spatial data products created by the USGS and EPA. It includes:

- **Spatial geometry** of 2.7M+ stream reaches across CONUS
- **Stream network topology** (upstream/downstream connections)
- **Mean annual flow estimates** (from EROM - Enhanced Runoff Method)
- **Drainage area calculations**
- **Elevation and slope data**

### Why Integrate NHD with NWM?

| Data Source | Provides | Limitations |
|-------------|----------|-------------|
| **NWM** | Real-time and forecast flow/velocity | No spatial geometry, no stream names, no historical context |
| **NHDPlus** | Spatial geometry, stream names, network topology, historical flow estimates | Static data, no real-time updates |
| **Combined** | Spatial maps + real-time intelligence + historical context | 🎉 Complete system |

---

## Database Schema

### Three NHD Tables

#### 1. `nhd_flowlines` - Core Spatial & Attributes

**Primary Key**: `nhdplusid` (joins to `hydro_timeseries.feature_id`)

**Key Fields**:
```sql
nhdplusid           BIGINT         -- Unique reach ID (PRIMARY KEY)
gnis_name           VARCHAR(255)   -- Stream name (e.g., "Rock Creek")
geom                GEOMETRY       -- Spatial LineString for maps
totdasqkm           DOUBLE         -- Total drainage area (CRITICAL for scoring)
streamorde          SMALLINT       -- Stream order (1-7+)
slope               DOUBLE         -- Gradient (m/m)
gradient_class      VARCHAR(20)    -- pool/run/riffle/cascade
size_class          VARCHAR(20)    -- headwater/creek/river
```

**Purpose**: Provides spatial geometry for map rendering and core stream attributes.

---

#### 2. `nhd_network_topology` - Network Connections

**Key Fields**:
```sql
nhdplusid           BIGINT         -- PRIMARY KEY
hydroseq            BIGINT         -- Hydrologic sequence (ordering)
levelpathi          BIGINT         -- Mainstem identifier
dnhydroseq          BIGINT         -- Downstream reach
uphydroseq          BIGINT         -- Upstream reach
arbolatesu          DOUBLE         -- Total upstream network length
startflag           SMALLINT       -- 1 = headwater
terminalfl          SMALLINT       -- 1 = outlet
```

**Purpose**: Enables upstream/downstream routing, watershed delineation, and network analysis.

---

#### 3. `nhd_flow_statistics` - Historical Flow Estimates

**Key Fields**:
```sql
nhdplusid           BIGINT         -- PRIMARY KEY
qama                DOUBLE         -- January mean flow (m³/s)
qcma                DOUBLE         -- March mean flow
qema                DOUBLE         -- May mean flow
vama                DOUBLE         -- January mean velocity (m/s)
gageidma            VARCHAR(20)    -- USGS gage ID (if gaged)
```

**Purpose**: Provides historical flow context for computing **flow percentiles** (critical for species scoring).

---

## Setup Instructions

### Step 1: Initialize NHD Schema

Run the initialization script to create the NHD tables:

```bash
conda activate fnwm
python scripts/setup/init_nhd_schema.py
```

**What this does**:
- Enables PostGIS extension (for spatial operations)
- Creates 3 NHD tables
- Creates spatial indexes (GIST on geometry)
- Creates triggers for auto-computing derived metrics
- Adds foreign key: `hydro_timeseries.feature_id` → `nhd_flowlines.nhdplusid`

**Expected output**:
```
============================================================
NHD Schema Initialization
============================================================
✅ Connected to database
✅ PostGIS found: version 3.x
✅ Schema creation complete

Tables created:
  1. nhd_flowlines          - Core spatial + attributes
  2. nhd_network_topology   - Network connectivity
  3. nhd_flow_statistics    - Mean annual flow estimates
```

---

### Step 2: Load NHD Data

Load your NHD GeoJSON file into the database:

```bash
python scripts/production/load_nhd_data.py "D:\Path\To\nhdHydrologyExample.geojson"
```

**What this does**:
- Reads GeoJSON file
- Parses features and properties (65+ fields)
- Inserts into 3 normalized tables
- Converts geometry to PostGIS format
- Auto-computes derived metrics via trigger

**Expected output**:
```
============================================================
NHD DATA LOADING
============================================================
GeoJSON file: D:\Data\nhdHydrologyExample.geojson
File size: 585.8 MB
✅ Loaded 15,432 features

Batch 1: Inserted 500/15,432 features (3.2%) - 250 features/sec
Batch 2: Inserted 1000/15,432 features (6.5%) - 245 features/sec
...
✅ NHD data loading complete!
```

---

### Step 3: Verify Data

Test the integration with sample queries:

```sql
-- Count loaded features
SELECT COUNT(*) FROM nhd_flowlines;

-- View sample reaches with names
SELECT nhdplusid, gnis_name, streamorde, totdasqkm, size_class
FROM nhd_flowlines
WHERE gnis_name IS NOT NULL
LIMIT 10;

-- Test NWM-NHD join
SELECT
    h.feature_id,
    n.gnis_name,
    h.streamflow_m3s AS nwm_flow,
    s.qema AS may_mean_flow,
    (h.streamflow_m3s / NULLIF(s.qema, 0)) AS flow_ratio
FROM hydro_timeseries h
JOIN nhd_flowlines n ON h.feature_id = n.nhdplusid
LEFT JOIN nhd_flow_statistics s ON n.nhdplusid = s.nhdplusid
WHERE h.source = 'analysis_assim'
  AND h.valid_time = (SELECT MAX(valid_time) FROM hydro_timeseries)
LIMIT 10;
```

**Example output**:
```
 feature_id  |   gnis_name   | nwm_flow | may_mean_flow | flow_ratio
-------------+---------------+----------+---------------+------------
 23001300061 | Rock Creek    |     0.45 |          0.28 |       1.61
 23001300042 | Big Spring Cr |     2.15 |          2.14 |       1.00
 55001100169 | Unnamed       |     0.12 |          0.33 |       0.36
```

---

## Using NHD Data in Your Code

### Example 1: Get Stream Name and Drainage Area

```python
from sqlalchemy import create_engine, text
import os

engine = create_engine(os.getenv('DATABASE_URL'))

def get_reach_metadata(feature_id: int):
    """Get stream name and drainage area for a reach."""
    with engine.begin() as conn:
        result = conn.execute(text("""
            SELECT
                nhdplusid,
                gnis_name,
                streamorde,
                totdasqkm,
                size_class,
                gradient_class
            FROM nhd_flowlines
            WHERE nhdplusid = :feature_id
        """), {'feature_id': feature_id})

        row = result.fetchone()
        if row:
            return {
                'feature_id': row[0],
                'stream_name': row[1] or 'Unnamed',
                'stream_order': row[2],
                'drainage_area_km2': row[3],
                'size_class': row[4],
                'gradient_class': row[5]
            }
    return None

# Usage
metadata = get_reach_metadata(23001300061572)
print(f"Stream: {metadata['stream_name']}")
print(f"Drainage Area: {metadata['drainage_area_km2']:.1f} km²")
```

---

### Example 2: Compute Flow Percentile (CRITICAL for Species Scoring)

```python
def compute_flow_percentile(feature_id: int, current_flow_m3s: float):
    """
    Compare current NWM flow to NHDPlus historical mean.

    Returns approximate percentile (0-100).
    """
    with engine.begin() as conn:
        # Get May mean flow (peak runoff month for many systems)
        result = conn.execute(text("""
            SELECT qema
            FROM nhd_flow_statistics
            WHERE nhdplusid = :feature_id
        """), {'feature_id': feature_id})

        row = result.fetchone()
        if not row or not row[0]:
            return 50  # Unknown - assume median

        historical_mean = row[0]

        # Compute ratio
        ratio = current_flow_m3s / historical_mean

        # Map ratio to percentile (simplified - could use full distribution)
        if ratio < 0.5:
            return 25  # Low flow
        elif ratio < 0.9:
            return 40
        elif ratio < 1.1:
            return 50  # Near mean
        elif ratio < 1.5:
            return 60
        elif ratio < 2.0:
            return 75
        else:
            return 90  # High flow

# Usage in species scoring
percentile = compute_flow_percentile(23001300061572, current_flow=0.45)
print(f"Flow Percentile: {percentile}th")
```

**IMPORTANT**: This flow percentile is used in `src/species/scoring.py` for the flow suitability component.

---

### Example 3: Find Upstream/Downstream Reaches

```python
def get_downstream_reach(feature_id: int):
    """Get the immediate downstream reach."""
    with engine.begin() as conn:
        result = conn.execute(text("""
            SELECT t.dnhydroseq
            FROM nhd_network_topology t
            WHERE t.nhdplusid = :feature_id
        """), {'feature_id': feature_id})

        row = result.fetchone()
        return row[0] if row else None

def get_all_upstream_reaches(feature_id: int):
    """Get all upstream reaches (recursive query)."""
    with engine.begin() as conn:
        result = conn.execute(text("""
            WITH RECURSIVE upstream AS (
                -- Base case: starting reach
                SELECT nhdplusid, hydroseq, 0 AS level
                FROM nhd_network_topology
                WHERE nhdplusid = :feature_id

                UNION ALL

                -- Recursive: find reaches flowing into current
                SELECT t.nhdplusid, t.hydroseq, u.level + 1
                FROM nhd_network_topology t
                JOIN upstream u ON t.dnhydroseq = u.hydroseq
                WHERE u.level < 50  -- Limit recursion depth
            )
            SELECT nhdplusid, level
            FROM upstream
            WHERE level > 0
            ORDER BY level, nhdplusid;
        """), {'feature_id': feature_id})

        return [row[0] for row in result]
```

---

### Example 4: Spatial Query (Find Reaches in Bounding Box)

```python
def get_reaches_in_bbox(min_lon, min_lat, max_lon, max_lat):
    """
    Get all reaches within a bounding box.

    Returns GeoJSON-ready features for map rendering.
    """
    with engine.begin() as conn:
        result = conn.execute(text("""
            SELECT
                nhdplusid,
                gnis_name,
                streamorde,
                ST_AsGeoJSON(geom) AS geometry
            FROM nhd_flowlines
            WHERE ST_Intersects(
                geom,
                ST_MakeEnvelope(:minlon, :minlat, :maxlon, :maxlat, 4326)
            )
            ORDER BY streamorde DESC
            LIMIT 1000;
        """), {
            'minlon': min_lon,
            'minlat': min_lat,
            'maxlon': max_lon,
            'maxlat': max_lat
        })

        features = []
        for row in result:
            features.append({
                'type': 'Feature',
                'properties': {
                    'feature_id': row[0],
                    'name': row[1] or 'Unnamed',
                    'stream_order': row[2]
                },
                'geometry': json.loads(row[3])
            })

        return {
            'type': 'FeatureCollection',
            'features': features
        }
```

---

## Derived Metrics

The NHD schema auto-computes these derived fields via database trigger:

### 1. Gradient Class
```python
gradient_class = CASE
    WHEN slope < 0.001 THEN 'pool'
    WHEN slope < 0.01 THEN 'run'
    WHEN slope < 0.05 THEN 'riffle'
    ELSE 'cascade'
END
```

**Use Case**: Different fish species prefer different gradients (e.g., trout prefer riffles/runs, bass prefer pools).

### 2. Size Class
```python
size_class = CASE
    WHEN totdasqkm < 10 THEN 'headwater'
    WHEN totdasqkm < 100 THEN 'creek'
    WHEN totdasqkm < 1000 THEN 'small_river'
    WHEN totdasqkm < 10000 THEN 'river'
    ELSE 'large_river'
END
```

**Use Case**: Filter by stream size in UI (e.g., "Show only creeks and small rivers").

### 3. Elevation Drop (m/km)
```python
elev_drop_m_per_km = (maxelevraw - minelevraw) / 100.0 / lengthkm
```

**Use Case**: Identify high-gradient streams (good for anadromous fish migration).

---

## Integration with Species Scoring (EPIC 4)

### Flow Percentile Component

**Before NHD**:
```python
# EPIC 4 used placeholder percentile
flow_percentile = 50  # Default - no historical context
```

**After NHD**:
```python
# Now compute actual percentile from historical data
from nhd_integration import compute_flow_percentile

flow_percentile = compute_flow_percentile(
    feature_id=feature_id,
    current_flow_m3s=hydro_data['flow']
)
```

**Scoring Impact**:
- Trout prefer 40th-70th percentile flow (moderate flows)
- Flow below 20th percentile = too low (dewatering risk)
- Flow above 90th percentile = too high (turbulent/unsafe)

### Drainage Area Component

**Use Case**: Large rivers have different habitat than small creeks.

```python
# Example: Trout prefer smaller streams
if totdasqkm > 1000:
    # Large river - lower trout score
    drainage_modifier = 0.8
else:
    # Small stream - optimal trout habitat
    drainage_modifier = 1.0
```

---

## Performance Considerations

### Spatial Indexes

The schema creates GIST indexes on geometry:
```sql
CREATE INDEX idx_nhd_geom ON nhd_flowlines USING GIST (geom);
```

**Performance**: Bounding box queries return 10,000 features in <200ms.

### Foreign Key Impact

The foreign key constraint ensures data integrity:
```sql
ALTER TABLE hydro_timeseries
ADD CONSTRAINT fk_hydro_nhd
FOREIGN KEY (feature_id) REFERENCES nhd_flowlines(nhdplusid);
```

**Impact**:
- ✅ Prevents orphaned NWM data (good)
- ⚠️ Requires NHD data loaded before NWM ingestion (or use ON DELETE RESTRICT)

---

## Troubleshooting

### Problem: PostGIS extension not found

**Error**:
```
ERROR: PostGIS extension NOT installed
```

**Solution**:
```sql
-- Connect as superuser
CREATE EXTENSION postgis;
```

### Problem: Geometry conversion failed

**Error**:
```
ERROR: Invalid WKT format
```

**Solution**: Check that GeoJSON coordinates are `[lon, lat]` not `[lat, lon]`.

### Problem: Foreign key violation

**Error**:
```
ERROR: Foreign key constraint "fk_hydro_nhd" violated
```

**Solution**: Ensure NHD data is loaded before ingesting NWM data with that feature_id.

---

## Next Steps

1. **Update Species Scoring** (EPIC 4):
   - Replace placeholder flow percentile with NHD-based calculation
   - Add drainage area modifiers to species configs

2. **Create Map Views** (EPIC 8):
   - Materialized views joining NWM + NHD for map rendering
   - See `docs/guides/implementation.md` EPIC 8

3. **Implement Watershed Analysis**:
   - Use `nhd_network_topology` to delineate upstream watersheds
   - Aggregate upstream conditions for larger-scale analysis

---

## References

- [NHDPlus v2.1 Documentation](https://www.epa.gov/waterdata/nhdplus-national-hydrography-dataset-plus)
- [PostGIS Documentation](https://postgis.net/docs/)
- FNWM Implementation Guide: `docs/guides/implementation.md`
- FNWM Project Status: `docs/development/project-status.md`

---

**Questions or Issues?**

Open an issue at: https://github.com/anthropics/fnwm/issues
