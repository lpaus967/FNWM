# NHD Database Setup - Quick Reference

This directory contains scripts for setting up NHDPlus v2.1 spatial integration.

## Prerequisites

- PostgreSQL database (configured in `.env`)
- PostGIS extension (auto-installed by script if missing)
- NHD GeoJSON file (see below)

## Setup Steps

### 1. Initialize NHD Schema

Run this FIRST to create the NHD tables:

```bash
conda activate fnwm
python scripts/setup/init_nhd_schema.py
```

**Creates:**
- `nhd_flowlines` - Spatial geometry + attributes
- `nhd_network_topology` - Network connections
- `nhd_flow_statistics` - Historical flow estimates

**Requirements:** Must be run AFTER `init_db.py`

---

### 2. Load NHD Data

Load your NHD GeoJSON file:

```bash
python scripts/production/load_nhd_data.py "D:\Path\To\nhdHydrologyExample.geojson"
```

**Parameters:**
- Path to GeoJSON file (required)
- Batch size: 500 features (default)

**Expected Time:**
- 10,000 features: ~40 seconds
- 100,000 features: ~7 minutes
- 1,000,000 features: ~1 hour

---

## Verification

Test the integration:

```sql
-- Count loaded features
SELECT COUNT(*) FROM nhd_flowlines;

-- View sample reaches
SELECT nhdplusid, gnis_name, streamorde, totdasqkm
FROM nhd_flowlines
WHERE gnis_name IS NOT NULL
LIMIT 10;

-- Test NWM-NHD join
SELECT h.feature_id, n.gnis_name, h.streamflow_m3s
FROM hydro_timeseries h
JOIN nhd_flowlines n ON h.feature_id = n.nhdplusid
LIMIT 10;
```

---

## Files in this Directory

| File | Purpose |
|------|---------|
| `create_nhd_tables.sql` | SQL schema for NHD tables (300+ lines) |
| `init_nhd_schema.py` | Python script to initialize schema |
| `NHD_SETUP_README.md` | This file |

---

## Obtaining NHD Data

### Option 1: USGS Download

Download NHDPlus v2.1 from:
https://www.epa.gov/waterdata/get-nhdplus-national-hydrography-dataset-plus-data

Format: Geodatabase or Shapefile → Convert to GeoJSON

### Option 2: Web Services

Use USGS Web Feature Service (WFS):
https://hydro.nationalmap.gov/arcgis/rest/services/NHDPlus_HR/MapServer

### Option 3: Subset for Testing

Your example file: `nhdHydrologyExample.geojson` (~15K features)

---

## Troubleshooting

### PostGIS not found

**Error:** `PostGIS extension NOT installed`

**Fix:**
```sql
-- Connect as superuser
psql -d fnwm -U postgres
CREATE EXTENSION postgis;
```

### File not found

**Error:** `GeoJSON file not found`

**Fix:** Check file path is absolute, not relative. Use double backslashes on Windows:
```bash
python load_nhd_data.py "D:\\Data\\nhd.geojson"
```

### Foreign key violation

**Error:** `Foreign key constraint "fk_hydro_nhd" violated`

**Fix:** Load NHD data BEFORE running NWM ingestion, or temporarily disable constraint:
```sql
ALTER TABLE hydro_timeseries DROP CONSTRAINT IF EXISTS fk_hydro_nhd;
```

---

## Next Steps

After setup:
1. Review: `docs/guides/nhd-integration.md`
2. Update species scoring to use flow percentiles
3. Implement map rendering (EPIC 8)

---

**Questions?** See full documentation: `docs/guides/nhd-integration.md`
