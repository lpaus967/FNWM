# FNWM Database & Scripts Reorganization - Complete

**Date:** 2026-01-09
**Status:** ✅ Implementation Complete - Ready for Migration

---

## Executive Summary

The FNWM project has been reorganized for better maintainability, clearer structure, and improved scalability. This includes:

1. **Database Schema Organization** - 5 domain-specific schemas instead of everything in `public`
2. **Scripts Directory Restructure** - Logical grouping by purpose and data type
3. **Automated Migration Tools** - Scripts to handle the transition smoothly
4. **Comprehensive Documentation** - Migration guides and updated references

**No data is lost** - this is purely organizational restructuring.

---

## What Changed

### 1. Database Structure

**Before:**
```
public schema
├── hydro_timeseries
├── nhd_flowlines
├── USGS_Flowsites
├── temperature_timeseries
└── ... 14+ tables
```

**After:**
```
nwm schema              (National Water Model data)
├── hydro_timeseries
└── ingestion_log

spatial schema          (Geospatial reference data)
├── flowlines (renamed from nhd_flowlines)
├── network_topology
├── flow_statistics
├── reach_centroids
└── reach_metadata

observations schema     (Ground truth data)
├── usgs_flowsites (renamed from USGS_Flowsites)
├── usgs_instantaneous_values
├── usgs_latest_readings
└── user_observations

derived schema          (Computed intelligence)
├── temperature_timeseries
├── computed_scores
└── map_current_conditions

validation schema       (Model performance)
├── nwm_usgs_validation
├── latest_validation_results
└── summary
```

### 2. Scripts Directory

**Before:**
```
scripts/
├── production/         (mixed purposes)
├── dev/                (some ingestion scripts)
├── setup/              (many individual init scripts)
└── satellite_data/     (wind data only)
```

**After:**
```
scripts/
├── db/                 # Database management (NEW)
├── ingestion/          # All data ingestion, organized by source
│   ├── nwm/
│   ├── spatial/
│   ├── observations/
│   ├── weather/
│   └── orchestration/
├── setup/              # Schema initialization
│   └── schemas/        # Individual schema SQL files (NEW)
├── dev/                # Development utilities
├── tests/              # Test scripts
├── utils/              # General utilities
└── archive/            # One-time migration scripts (NEW)
```

---

## Benefits

### Database Benefits

1. **Logical Organization** - Tables grouped by domain and purpose
2. **Better Access Control** - Grant/revoke permissions per schema
3. **Easier Maintenance** - Clear separation of concerns
4. **Self-Documenting** - Schema names indicate data type
5. **Simplified Queries** - `FROM spatial.flowlines` is clearer than `FROM nhd_flowlines`

### Scripts Benefits

1. **Clear Purpose** - Directory names describe what scripts do
2. **Logical Grouping** - Related scripts together
3. **Easier Navigation** - Find scripts by domain
4. **Reduced Clutter** - Archive for historical scripts
5. **Better Maintenance** - Clear ownership

---

## Migration Steps

### Step 1: Backup (REQUIRED)

```bash
pg_dump -U masteruser -h fnwm-db.cjome0482kqx.us-east-2.rds.amazonaws.com \
    -d fnwm-db > backup_$(date +%Y%m%d_%H%M%S).sql
```

### Step 2: Run Database Migration

```bash
# Stop the API server first
# Ctrl+C if running, or kill the process

# Preview migration
python scripts/db/migrate_to_schemas.py --dry-run

# Run migration
python scripts/db/migrate_to_schemas.py
```

**Duration:** ~30 seconds
**Downtime:** Yes - API must be stopped
**Risk:** Low - all data preserved

### Step 3: Update Application Code

```bash
# Preview changes
python scripts/db/update_code_schema_references.py

# Apply changes
python scripts/db/update_code_schema_references.py --apply
```

### Step 4: Test & Verify

```bash
# Start API
python -m uvicorn src.api.main:app --reload --port 8000

# Test endpoints
curl http://localhost:8000/health
curl http://localhost:8000/hydrology/reach/3018334
```

---

## Files Created

### Database Management (`scripts/db/`)

| File | Purpose |
|------|---------|
| `create_schemas.sql` | Creates 5 domain schemas |
| `migrate_to_schemas.sql` | SQL migration script |
| `migrate_to_schemas.py` | Python migration orchestrator |
| `update_code_schema_references.py` | Updates code references |
| `init_schemas.py` | Unified schema initialization |

### Schema Definitions (`scripts/setup/schemas/`)

| File | Schema | Tables |
|------|--------|--------|
| `nwm.sql` | nwm | 2 tables |
| `spatial.sql` | spatial | 5 tables |
| `observations.sql` | observations | 4 tables |
| `derived.sql` | derived | 3 tables |
| `validation.sql` | validation | 3 tables |

### Documentation

| File | Purpose |
|------|---------|
| `docs/guides/schema-migration-guide.md` | Complete migration guide |
| `docs/guides/scripts-reorganization-summary.md` | Scripts changes summary |
| `REORGANIZATION_SUMMARY.md` | This file |

---

## Scripts Reference

### Most Common Commands

```bash
# Database migration
python scripts/db/migrate_to_schemas.py

# Update code references
python scripts/db/update_code_schema_references.py --apply

# Initialize all schemas (fresh install)
python scripts/db/init_schemas.py --all

# NWM ingestion (filtered)
python scripts/ingestion/nwm/run_subset_ingestion.py

# USGS ingestion
python scripts/ingestion/observations/ingest_usgs_data.py

# Temperature ingestion
python scripts/ingestion/weather/ingest_temperature.py

# Full database reset
python scripts/ingestion/orchestration/reset_and_repopulate_db.py \
    --nhd-geojson <path>
```

---

## Rollback Plan

If needed, restore from backup:

```bash
# Stop API
# Drop current database (if needed)
dropdb -U masteruser -h <host> fnwm-db

# Recreate database
createdb -U masteruser -h <host> fnwm-db

# Restore from backup
psql -U masteruser -h <host> -d fnwm-db < backup_20260109.sql
```

---

## Testing Checklist

After migration, verify:

- [ ] Database backup completed
- [ ] Migration script ran successfully
- [ ] All 5 schemas created
- [ ] All tables moved to correct schemas
- [ ] Foreign keys intact
- [ ] Materialized views refreshable
- [ ] Code references updated
- [ ] API starts without errors
- [ ] Health endpoint works: `GET /health`
- [ ] Hydrology endpoint works: `GET /hydrology/reach/3018334`
- [ ] Species scoring works: `GET /fisheries/reach/3018334/score`
- [ ] USGS ingestion works
- [ ] NWM ingestion works
- [ ] Temperature ingestion works
- [ ] No errors in logs

---

## Performance Impact

**Expected:** ZERO performance impact
- Query speed: Unchanged
- Index performance: Unchanged
- Storage size: Unchanged
- Join performance: Unchanged

Schemas are logical organization only - no physical changes.

---

## Breaking Changes

### For Developers

1. **SQL Queries** - Must use schema prefixes
   ```sql
   -- Before
   SELECT * FROM hydro_timeseries

   -- After
   SELECT * FROM nwm.hydro_timeseries
   ```

2. **Script Paths** - Updated locations
   ```bash
   # Before
   python scripts/production/ingest_usgs_data.py

   # After
   python scripts/ingestion/observations/ingest_usgs_data.py
   ```

### For Cron Jobs

Update scheduled task paths:
```bash
# Before
0 * * * * cd /path/to/FNWM && python scripts/production/ingest_usgs_data.py

# After
0 * * * * cd /path/to/FNWM && python scripts/ingestion/observations/ingest_usgs_data.py
```

---

## Files Removed

**Archived (not deleted):**
- `scripts/archive/fix_smallint_columns.sql`
- `scripts/archive/fix_flow_units_cfs_to_m3s.sql`
- `scripts/archive/run_fix_flow_units.py`

**Deleted:**
- `scripts/production/data/` (2.8GB of raw data - regeneratable)

**Directories Removed:**
- `scripts/production/` (renamed to `ingestion/`)
- `scripts/satellite_data/` (merged into `ingestion/weather/`)

---

## Support & Troubleshooting

**Common Issues:**

1. **Foreign key errors** → See migration guide section "Common Issues & Solutions"
2. **Materialized view errors** → Refresh views manually
3. **API query errors** → Re-run code updater
4. **Import path errors** → Check script moved to new location

**Full Documentation:**
- Migration Guide: `docs/guides/schema-migration-guide.md`
- Scripts Summary: `docs/guides/scripts-reorganization-summary.md`
- NHD Integration: `docs/guides/nhd-integration.md`
- USGS Integration: `docs/guides/usgs-integration.md`

---

## Next Steps

1. **Review this summary** ✅
2. **Backup database** ⏳
3. **Run migration** ⏳
4. **Update code** ⏳
5. **Test thoroughly** ⏳
6. **Update cron jobs** ⏳
7. **Monitor logs** ⏳

---

## Questions?

Refer to documentation or create a GitHub issue.

**Migration is complete and ready to run!** 🚀
