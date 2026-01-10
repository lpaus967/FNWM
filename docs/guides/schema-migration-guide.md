# FNWM Schema Migration Guide

**Date:** 2026-01-09
**Status:** Complete

---

## Overview

This guide describes the database reorganization that moves tables from the `public` schema to organized domain-specific schemas.

### New Schema Structure

```
nwm               - National Water Model data
├── hydro_timeseries
└── ingestion_log

nhd               - NHDPlus geospatial reference data
├── flowlines (formerly nhd_flowlines)
├── network_topology (formerly nhd_network_topology)
├── flow_statistics (formerly nhd_flow_statistics)
├── reach_centroids (formerly nhd_reach_centroids)
└── reach_metadata

observations      - Ground truth data
├── usgs_flowsites (formerly USGS_Flowsites)
├── usgs_instantaneous_values
├── usgs_latest_readings
├── user_observations
└── temperature_timeseries (air temperature forecasts)

derived           - Computed intelligence
├── computed_scores
└── map_current_conditions

validation        - Model performance
├── nwm_usgs_validation
├── latest_validation_results
└── summary (formerly validation_summary)
```

---

## Benefits

1. **Logical Organization** - Tables grouped by domain and purpose
2. **Better Security** - Grant/revoke permissions per schema
3. **Easier Maintenance** - Clear separation of concerns
4. **Self-Documenting** - Schema names indicate data type
5. **Simplified Queries** - `FROM nhd.flowlines` vs `FROM nhd_flowlines`

---

## Migration Process

### Step 1: Backup Your Database (CRITICAL!)

```bash
# Full database backup
pg_dump -U masteruser -h <host> -d fnwm-db > backup_$(date +%Y%m%d).sql

# Or backup specific tables
pg_dump -U masteruser -h <host> -d fnwm-db \
    -t hydro_timeseries \
    -t nhd_flowlines \
    -t USGS_Flowsites \
    > backup_critical_tables.sql
```

### Step 2: Run Migration Script

```bash
# Preview changes (dry run)
python scripts/db/migrate_to_schemas.py --dry-run

# Run migration (interactive confirmation)
python scripts/db/migrate_to_schemas.py

# Run migration (skip confirmation)
python scripts/db/migrate_to_schemas.py --skip-confirmation
```

**What it does:**
1. Creates 5 new schemas
2. Moves tables from `public` to domain schemas
3. Renames some tables (e.g., `nhd_flowlines` → `nhd.flowlines`)
4. Updates foreign key constraints
5. Recreates materialized views with new references

**Duration:** ~30 seconds for typical database
**Downtime:** Yes - stop API during migration
**Data Loss:** None - structural changes only

### Step 3: Update Application Code

```bash
# Preview code changes
python scripts/db/update_code_schema_references.py

# Apply code changes
python scripts/db/update_code_schema_references.py --apply
```

**What it updates:**
- All SQL queries in `src/` directory
- FROM clauses: `FROM hydro_timeseries` → `FROM nwm.hydro_timeseries`
- JOIN clauses: `JOIN nhd_flowlines` → `JOIN nhd.flowlines`
- INSERT/UPDATE/DELETE statements
- Foreign key references

### Step 4: Verify Migration

```bash
# Check schema structure
python scripts/db/migrate_to_schemas.py --verify

# Test API endpoints
python -m uvicorn src.api.main:app --reload --port 8000

# Open browser to http://localhost:8000/docs
# Test each endpoint:
#   - GET /health
#   - GET /hydrology/reach/{feature_id}
#   - GET /fisheries/reach/{feature_id}/score
```

### Step 5: Update Ingestion Scripts (Optional)

The ingestion scripts have been reorganized to match the new schema structure:

**Old Structure:**
```
scripts/production/
scripts/dev/
```

**New Structure:**
```
scripts/ingestion/
├── nwm/               # NWM data ingestion
├── nhd/           # NHD data loading
├── observations/      # USGS gage ingestion
├── weather/           # Temperature & wind data
└── orchestration/     # Full workflows
```

Update any cron jobs or scheduled tasks to use new paths.

---

## Rollback Procedure

If something goes wrong, you can rollback:

```bash
# Restore from backup
psql -U masteruser -h <host> -d fnwm-db < backup_20260109.sql

# Or manually move tables back
ALTER TABLE nwm.hydro_timeseries SET SCHEMA public;
ALTER TABLE nhd.flowlines SET SCHEMA public;
ALTER TABLE nhd.flowlines RENAME TO nhd_flowlines;
# ... etc for each table
```

---

## Common Issues & Solutions

### Issue 1: Foreign Key Constraint Errors

**Error:**
```
ERROR: update or delete on table "usgs_flowsites" violates foreign key constraint
```

**Solution:**
Foreign keys were updated during migration. If you see this error, run:

```sql
-- Check foreign key constraints
SELECT conname, conrelid::regclass, confrelid::regclass
FROM pg_constraint
WHERE contype = 'f';

-- Drop and recreate if needed
ALTER TABLE validation.nwm_usgs_validation
DROP CONSTRAINT fk_validation_usgs_site;

ALTER TABLE validation.nwm_usgs_validation
ADD CONSTRAINT fk_validation_usgs_site
FOREIGN KEY (site_id)
REFERENCES observations.usgs_flowsites("siteId")
ON DELETE CASCADE;
```

### Issue 2: Materialized View Refresh Errors

**Error:**
```
ERROR: materialized view "usgs_latest_readings" does not exist
```

**Solution:**
```sql
-- Refresh all materialized views
REFRESH MATERIALIZED VIEW CONCURRENTLY observations.usgs_latest_readings;
REFRESH MATERIALIZED VIEW CONCURRENTLY validation.latest_validation_results;
REFRESH MATERIALIZED VIEW CONCURRENTLY derived.map_current_conditions;
```

### Issue 3: API Queries Still Reference Old Schema

**Error:**
```
ERROR: relation "hydro_timeseries" does not exist
```

**Solution:**
Re-run the code updater:
```bash
python scripts/db/update_code_schema_references.py --apply
```

Or manually update the file:
```python
# Before
query = "SELECT * FROM hydro_timeseries WHERE feature_id = :id"

# After
query = "SELECT * FROM nwm.hydro_timeseries WHERE feature_id = :id"
```

### Issue 4: Search Path Issues

If you want to query tables without schema prefixes:

```sql
-- For current session
SET search_path TO public, nwm, nhd, observations, derived, validation;

-- For database default
ALTER DATABASE "fnwm-db" SET search_path TO public, nwm, nhd, observations, derived, validation;
```

Note: Explicit schema prefixes are recommended for clarity.

---

## Fresh Installation (No Migration Needed)

If setting up a new database from scratch:

```bash
# 1. Create schemas
python scripts/db/init_schemas.py --all

# 2. Load nhd data
python scripts/ingestion/nhd/load_nhd_data.py <path-to-geojson>

# 3. Initialize USGS sites
python scripts/setup/init_usgs_flowsites.py <path-to-usgs-geojson>

# 4. Run initial ingestion
python scripts/ingestion/nwm/run_subset_ingestion.py
```

---

## Testing Checklist

After migration, verify:

- [ ] All schemas created: `\dn` in psql
- [ ] All tables moved: `\dt nwm.*`, `\dt nhd.*`, etc.
- [ ] Foreign keys intact: `\d+ validation.nwm_usgs_validation`
- [ ] Materialized views refreshable
- [ ] API health check passes: `GET /health`
- [ ] Hydrology endpoint works: `GET /hydrology/reach/3018334`
- [ ] Species scoring works: `GET /fisheries/reach/3018334/score`
- [ ] USGS ingestion works: `python scripts/ingestion/observations/ingest_usgs_data.py`
- [ ] NWM ingestion works: `python scripts/ingestion/nwm/run_subset_ingestion.py`
- [ ] Temperature ingestion works: `python scripts/ingestion/weather/ingest_temperature.py`

---

## Performance Impact

**Expected Changes:**
- Query performance: Unchanged (schemas are logical grouping only)
- Index performance: Unchanged (indexes preserved)
- Join performance: Unchanged (foreign keys preserved)
- Storage size: Unchanged (no data duplication)

**Actual Impact:** Zero performance difference - this is purely organizational.

---

## References

- **Migration Script:** `scripts/db/migrate_to_schemas.py`
- **Schema Definitions:** `scripts/setup/schemas/*.sql`
- **Code Updater:** `scripts/db/update_code_schema_references.py`
- **Init Script:** `scripts/db/init_schemas.py`

---

## Questions?

Contact the development team or file an issue at:
https://github.com/anthropics/claude-code/issues
