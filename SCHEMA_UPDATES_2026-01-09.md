# Database Schema Updates

**Date:** 2026-01-09
**Status:** Complete

## Summary

Two major schema reorganization changes have been implemented:

1. **Renamed `spatial` schema to `nhd`** - Better semantic meaning for NHDPlus geospatial data
2. **Moved `temperature_timeseries` from `derived` to `observations`** - Temperature forecasts are observational data, not internally derived

---

## Change 1: Spatial Schema Renamed to NHD

### Rationale
The schema contains NHDPlus (National Hydrography Dataset Plus) flowline data and stream network topology. The name `nhd` is more semantically clear and concise than `spatial`.

### Changes Made

#### Database
- Schema renamed: `spatial` → `nhd`
- All tables in schema automatically updated:
  - `nhd.flowlines`
  - `nhd.network_topology`
  - `nhd.flow_statistics`
  - `nhd.reach_centroids`
  - `nhd.reach_metadata`

#### Scripts Updated
- **30 Python files** updated to reference `nhd.*` instead of `spatial.*`
- **3 SQL files** updated:
  - `scripts/db/create_schemas.sql`
  - `scripts/db/migrate_to_schemas.sql`
  - `scripts/setup/schemas/observations.sql`

#### Files Created/Modified
- Created: `scripts/db/rename_spatial_to_nhd.sql` - SQL migration script
- Created: `scripts/db/rename_spatial_to_nhd.py` - Python migration orchestrator
- Created: `scripts/setup/schemas/nhd.sql` - New schema definition
- Deleted: `scripts/setup/schemas/spatial.sql` - Old schema definition
- Updated: `scripts/db/update_code_schema_references.py` - Added pattern for schema renames

#### Example Changes
```python
# Before
SELECT * FROM spatial.flowlines WHERE nhdplusid = :id

# After
SELECT * FROM nhd.flowlines WHERE nhdplusid = :id
```

---

## Change 2: Temperature Timeseries Moved to Observations

### Rationale
The `temperature_timeseries` table contains air temperature forecasts from the Open-Meteo API - this is external observational data, not internally computed/derived data. It belongs in the `observations` schema alongside USGS gage data and user trip reports.

### Changes Made

#### Database
- Table moved: `derived.temperature_timeseries` → `observations.temperature_timeseries`
- Foreign key constraints updated to reference new location

#### Schema Definitions Updated
- **observations.sql**: Added temperature_timeseries table definition
- **derived.sql**: Removed temperature_timeseries table definition

#### Code References Updated
- Updated 4 occurrences in `src/metrics/thermal_suitability.py`
- Updated 1 occurrence in `src/api/main.py`
- Updated ingestion scripts that reference temperature table
- Updated migration scripts to reflect new location

#### Files Created
- Created: `scripts/db/move_temperature_to_observations.sql` - Migration script

#### Example Changes
```python
# Before
SELECT temperature_2m FROM derived.temperature_timeseries
WHERE nhdplusid = :id

# After
SELECT temperature_2m FROM observations.temperature_timeseries
WHERE nhdplusid = :id
```

---

## Updated Schema Structure

### Current Organization

```
nwm                    - National Water Model data
├── hydro_timeseries
└── ingestion_log

nhd                    - NHDPlus geospatial reference data
├── flowlines
├── network_topology
├── flow_statistics
├── reach_centroids
└── reach_metadata

observations           - Ground truth data
├── usgs_flowsites
├── usgs_instantaneous_values
├── usgs_latest_readings
├── user_observations
└── temperature_timeseries    ← MOVED HERE

derived                - Computed intelligence
├── computed_scores
└── map_current_conditions

validation             - Model performance metrics
├── nwm_usgs_validation
├── latest_validation_results
└── summary
```

---

## Files Modified

### Database Migration Scripts
- `scripts/db/rename_spatial_to_nhd.sql`
- `scripts/db/rename_spatial_to_nhd.py`
- `scripts/db/move_temperature_to_observations.sql`
- `scripts/db/migrate_to_schemas.sql`
- `scripts/db/create_schemas.sql`
- `scripts/db/update_code_schema_references.py`

### Schema Definitions
- `scripts/setup/schemas/nhd.sql` (created)
- `scripts/setup/schemas/observations.sql` (updated)
- `scripts/setup/schemas/derived.sql` (updated)
- `scripts/setup/schemas/spatial.sql` (deleted)

### Source Code (30 Python files)
Key files updated:
- `src/api/main.py`
- `src/metrics/thermal_suitability.py`
- `src/metrics/flow_percentile.py`
- `src/temperature/prediction.py`
- `src/validation/nwm_usgs_validator.py`
- `scripts/ingestion/nwm/run_subset_ingestion.py`
- `scripts/ingestion/spatial/load_nhd_data.py`
- `scripts/ingestion/weather/ingest_temperature.py`
- `scripts/setup/init_nhd_*.py`
- All test files referencing schemas

### Documentation
- `docs/guides/schema-migration-guide.md` (updated)
- `SCHEMA_UPDATES_2026-01-09.md` (this file)

---

## Verification

To verify these changes were applied correctly:

```bash
# Check schema exists
psql -d fnwm -c "\dn"

# List tables in nhd schema
psql -d fnwm -c "\dt nhd.*"

# Verify temperature_timeseries location
psql -d fnwm -c "\d observations.temperature_timeseries"

# Run updated ingestion
python scripts/ingestion/weather/ingest_temperature.py

# Test API
python -m uvicorn src.api.main:app --reload
```

---

## Migration Commands Used

```bash
# 1. Rename spatial schema to nhd
python scripts/db/rename_spatial_to_nhd.py

# 2. Move temperature table
psql -d fnwm -f scripts/db/move_temperature_to_observations.sql

# 3. Update code references
python scripts/db/update_code_schema_references.py --include-scripts --apply
```

---

## Impact

### Zero Breaking Changes
- All code references automatically updated
- All foreign keys preserved
- All indexes maintained
- No data loss or corruption

### Performance
- No performance impact (schemas are logical organization only)

### Maintenance
- Clearer semantic meaning: `nhd.*` vs `spatial.*`
- Temperature data properly categorized as observational
- Better alignment with data source (NHDPlus, Open-Meteo API)

---

## Next Steps

None required - migration is complete and verified.

Optional improvements:
- Update any external documentation referencing old schema names
- Update any Terraform or infrastructure-as-code that references schemas
- Update any API documentation showing example queries

---

## Questions?

Contact development team or refer to:
- `docs/guides/schema-migration-guide.md` - Complete migration guide
- `scripts/db/README.md` - Database script documentation
