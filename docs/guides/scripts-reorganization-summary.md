# Scripts Directory Reorganization Summary

**Date:** 2026-01-09
**Status:** Complete

---

## Overview

The `scripts/` directory has been reorganized for better maintainability and logical grouping.

---

## New Directory Structure

```
scripts/
├── db/                          # Database management (NEW)
│   ├── create_schemas.sql       # Schema definitions
│   ├── migrate_to_schemas.sql   # Migration SQL script
│   ├── migrate_to_schemas.py    # Migration Python script
│   ├── update_code_schema_references.py  # Code updater
│   └── init_schemas.py          # Unified schema initialization
│
├── ingestion/                   # Data ingestion (RENAMED from production)
│   ├── nwm/
│   │   ├── run_full_ingestion.py        # All 2.7M reaches
│   │   └── run_subset_ingestion.py      # Filtered by NHD (moved from dev/)
│   ├── spatial/
│   │   └── load_nhd_data.py             # NHD GeoJSON loader
│   ├── observations/
│   │   └── ingest_usgs_data.py          # USGS gage data
│   ├── weather/
│   │   ├── ingest_temperature.py        # Open-Meteo temperature
│   │   └── wind/                        # HRRR wind pipeline (moved from satellite_data/)
│   │       ├── run_pipeline.py
│   │       ├── dataFetcher.py
│   │       ├── processGrib.py
│   │       └── uploadToS3.py
│   └── orchestration/
│       ├── reset_and_repopulate_db.py   # Full database reset
│       └── export_map_geojson.py        # Map export
│
├── setup/                       # Initial schema setup
│   ├── schemas/                 # Schema SQL files (NEW)
│   │   ├── nwm.sql
│   │   ├── spatial.sql
│   │   ├── observations.sql
│   │   ├── derived.sql
│   │   └── validation.sql
│   ├── init_db.py                       # Legacy init (kept for compatibility)
│   ├── init_nhd_centroids.py
│   ├── init_nhd_schema.py
│   ├── init_temperature_tables.py
│   ├── init_usgs_flowsites.py
│   ├── init_usgs_data_table.py
│   ├── init_validation_table.py
│   └── create_*.sql files               # Legacy SQL files (kept for reference)
│
├── dev/                         # Development utilities
│   ├── check_usgs_sites.py
│   ├── query_usgs_data.py
│   └── check_temp_table.py
│
├── tests/                       # Test scripts
│   ├── test_*.py
│   └── verify_*.py
│
├── utils/                       # General utilities
│   ├── check_progress.py
│   └── cleanup_orphaned_jobs.py
│
└── archive/                     # One-time migration scripts (NEW)
    ├── fix_smallint_columns.sql
    ├── fix_flow_units_cfs_to_m3s.sql
    └── run_fix_flow_units.py
```

---

## Changes Made

### New Directories

1. **`scripts/db/`** - Central location for database management scripts
   - Schema creation and migration
   - Code update utilities
   - Unified initialization

2. **`scripts/ingestion/`** - Renamed from `production/`
   - Better describes purpose (data ingestion, not production deployment)
   - Organized by data source (nwm, spatial, observations, weather)
   - Separated orchestration scripts

3. **`scripts/archive/`** - One-time migration scripts
   - Keeps them for reference but out of the way
   - Clearly indicates they're not part of normal workflows

### Moved Files

| Old Location | New Location | Reason |
|-------------|--------------|--------|
| `dev/run_subset_ingestion.py` | `ingestion/nwm/` | Grouped with NWM ingestion |
| `production/run_full_ingestion.py` | `ingestion/nwm/` | Grouped with NWM ingestion |
| `production/load_nhd_data.py` | `ingestion/spatial/` | Grouped by data type |
| `production/ingest_usgs_data.py` | `ingestion/observations/` | Grouped by data type |
| `production/ingest_temperature.py` | `ingestion/weather/` | Grouped by data type |
| `satellite_data/wind/` | `ingestion/weather/wind/` | Consolidated weather data |
| `production/reset_and_repopulate_db.py` | `ingestion/orchestration/` | Full workflow script |
| `production/export_map_geojson.py` | `ingestion/orchestration/` | Export workflow |
| `setup/fix_*.sql` | `archive/` | One-time migrations |

### Removed/Consolidated

- **`scripts/production/`** - Renamed to `ingestion/`
- **`scripts/satellite_data/`** - Merged into `ingestion/weather/`
- **`scripts/production/data/`** - Removed (2.8GB of raw data)

---

## Updated Workflows

### Database Setup (Fresh Installation)

**Old:**
```bash
python scripts/setup/init_db.py
python scripts/setup/init_nhd_schema.py
python scripts/setup/init_temperature_tables.py
python scripts/setup/init_usgs_flowsites.py
# ... multiple scripts
```

**New:**
```bash
# One command to initialize all schemas
python scripts/db/init_schemas.py --all

# Or individual schemas
python scripts/db/init_schemas.py --schema spatial
```

### Data Ingestion

**Old:**
```bash
python scripts/production/run_full_ingestion.py
python scripts/production/ingest_temperature.py
python scripts/production/ingest_usgs_data.py
```

**New:**
```bash
python scripts/ingestion/nwm/run_subset_ingestion.py
python scripts/ingestion/weather/ingest_temperature.py
python scripts/ingestion/observations/ingest_usgs_data.py
```

### Database Migration

**New:**
```bash
# Migrate existing database to new schema structure
python scripts/db/migrate_to_schemas.py

# Update application code
python scripts/db/update_code_schema_references.py --apply
```

---

## Scripts Summary

### Database Management (`scripts/db/`)

| Script | Purpose | Usage |
|--------|---------|-------|
| `create_schemas.sql` | Creates 5 domain schemas | Run via migrate script |
| `migrate_to_schemas.sql` | Moves tables to schemas | Run via migrate script |
| `migrate_to_schemas.py` | Python migration orchestrator | `python scripts/db/migrate_to_schemas.py` |
| `update_code_schema_references.py` | Updates SQL queries in code | `python scripts/db/update_code_schema_references.py --apply` |
| `init_schemas.py` | Unified schema initialization | `python scripts/db/init_schemas.py --all` |

### Ingestion (`scripts/ingestion/`)

| Script | Purpose | Frequency |
|--------|---------|-----------|
| `nwm/run_subset_ingestion.py` | NWM data (filtered) | Hourly |
| `nwm/run_full_ingestion.py` | NWM data (all reaches) | Manual |
| `spatial/load_nhd_data.py` | NHD spatial data | One-time |
| `observations/ingest_usgs_data.py` | USGS gage observations | Hourly |
| `weather/ingest_temperature.py` | Temperature forecasts | Daily |
| `weather/wind/run_pipeline.py` | Wind data pipeline | Hourly |
| `orchestration/reset_and_repopulate_db.py` | Full database reset | Manual |
| `orchestration/export_map_geojson.py` | Map export | As needed |

---

## Benefits of Reorganization

1. **Clear Purpose** - Directory names describe what scripts do
2. **Logical Grouping** - Related scripts together
3. **Easier Navigation** - Find scripts by domain, not arbitrary location
4. **Reduced Clutter** - Archive directory for historical scripts
5. **Better Maintenance** - Clear ownership and dependencies
6. **Scalability** - Easy to add new ingestion sources

---

## Migration Impact

**For Developers:**
- Update any local scripts or aliases that reference old paths
- Use new paths in documentation and guides

**For Cron Jobs:**
Update scheduled task paths:
```bash
# Old
0 * * * * python /path/scripts/production/ingest_usgs_data.py

# New
0 * * * * python /path/scripts/ingestion/observations/ingest_usgs_data.py
```

**For CI/CD:**
Update pipeline configuration to use new paths.

---

## Files Removed

Total files removed: **3 one-time migration scripts + 2.8GB data directory**

Archived (still accessible):
- `archive/fix_smallint_columns.sql`
- `archive/fix_flow_units_cfs_to_m3s.sql`
- `archive/run_fix_flow_units.py`

---

## Next Steps

1. ✅ Scripts reorganized
2. ✅ Database schemas created
3. ✅ Migration scripts ready
4. ⏳ Run database migration
5. ⏳ Update production cron jobs
6. ⏳ Update deployment documentation

---

## References

- **Migration Guide:** `docs/guides/schema-migration-guide.md`
- **Schema Definitions:** `scripts/setup/schemas/*.sql`
- **Database Scripts:** `scripts/db/`
