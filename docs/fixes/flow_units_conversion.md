# Flow Units Conversion Fix: CFS → m³/s

**Date:** 2026-01-06
**Issue:** Flow percentile calculations showing incorrect values (~4% instead of ~50%)
**Root Cause:** Unit mismatch between NHDPlus flow statistics (CFS) and NWM current flows (m³/s)
**Solution:** Convert all flow statistics from CFS to m³/s

---

## Problem Description

### The Issue
Flow percentile values are showing extreme low values (around 4-5%) when conditions appear normal. For example:
```json
{
  "flow_percentile": 4.39605416954073,
  "flow_percentile_category": "extreme_low"
}
```

### Root Cause
There's a unit mismatch in the flow percentile calculation:

1. **Current Flow (from National Water Model)**: Stored in **m³/s** ✓
   - Source: `hydro_timeseries.streamflow`
   - Example: 41.64 m³/s

2. **Historical Monthly Mean (from NHDPlus)**: Stored in **CFS** ❌
   - Source: `nhd_flow_statistics.qama` through `qfma`
   - Example: 1471 CFS (which equals 41.66 m³/s)

3. **The Calculation**: Divides m³/s by CFS (wrong!)
   ```sql
   flow_percentile = 50.0 + (50.0 * tanh((current_flow / monthly_mean - 1.0) * 2.0))
   ```

   With mismatched units:
   - Ratio: 41.64 / 1471 = **0.028** (way too low!)
   - Percentile: **4.4%** ❌ (extreme low, incorrect)

   With correct units:
   - Ratio: 41.64 / 41.66 = **0.9995** (nearly equal)
   - Percentile: **~50%** ✓ (normal conditions, correct)

### Impact
- Flow percentiles show "extreme_low" for normal conditions
- API responses show incorrect habitat suitability
- Map exports display wrong flow classifications
- Species scoring uses incorrect flow data

---

## Solution

### Conversion Factor
```
1 m³/s = 35.3147 cubic feet per second (CFS)
```

To convert FROM CFS TO m³/s:
```
m³/s = CFS ÷ 35.3147
```

### What Gets Converted
All flow columns in `nhd_flow_statistics` table:
- Monthly mean flows: `qama` through `qlma` (Jan-Dec)
- Incremental flows: `qincrama` through `qincrfma`
- Gage measurements: `gageqma`

---

## How to Apply the Fix

### Option 1: Run Python Script (Recommended)
This provides safety checks, logging, and verification:

```bash
# From project root
python scripts/setup/run_fix_flow_units.py
```

The script will:
1. Show sample data before conversion
2. Ask for confirmation
3. Apply the conversion
4. Show sample data after conversion
5. Refresh the materialized view
6. Verify the results

### Option 2: Run SQL Script Directly
If you prefer direct SQL execution:

```bash
psql -U postgres -d fnwm -f scripts/setup/fix_flow_units_cfs_to_m3s.sql
```

---

## Verification

### 1. Check Sample Flow Values
Before conversion:
```sql
SELECT nhdplusid, qama, qema, qfma
FROM nhd_flow_statistics
WHERE qama IS NOT NULL
LIMIT 3;
```

Expected: Large values (hundreds to thousands - these are CFS)

After conversion:
```sql
SELECT nhdplusid, qama, qema, qfma
FROM nhd_flow_statistics
WHERE qama IS NOT NULL
LIMIT 3;
```

Expected: Smaller values (divided by ~35 - these are now m³/s)

### 2. Check Flow Percentiles
```sql
SELECT
    AVG(flow_percentile) as avg_percentile,
    MIN(flow_percentile) as min_percentile,
    MAX(flow_percentile) as max_percentile
FROM map_current_conditions
WHERE flow_percentile IS NOT NULL;
```

Expected results:
- Average percentile: ~40-60% (should be close to 50%)
- Range: 0-100% (with variety, not all extreme low)

### 3. Test via API
After restarting your API server:

```bash
curl http://localhost:8000/conditions/current/23776838
```

Check that `flow_percentile` values are reasonable (not all extreme_low).

---

## Technical Details

### Affected Tables
- `nhd_flow_statistics` - Raw data (converted)
- `map_current_conditions` - Materialized view (refreshed after conversion)

### Affected Code Paths
1. **Materialized View** (`scripts/setup/create_map_current_conditions_view.sql`):
   ```sql
   CASE
       WHEN latest.streamflow IS NOT NULL AND fs.monthly_mean IS NOT NULL
       THEN 50.0 + (50.0 * tanh((latest.streamflow / fs.monthly_mean - 1.0) * 2.0))
   ```
   Now both values are in m³/s ✓

2. **API Flow Percentile** (`src/metrics/flow_percentile.py`):
   ```python
   def get_monthly_mean_flow(feature_id: int, month: int):
       # Queries nhd_flow_statistics directly
       result = conn.execute(text(f"SELECT {column_name} FROM nhd_flow_statistics..."))
   ```
   Now returns m³/s values ✓

### Why This Is Better Than Code Changes
Converting the data once is superior to fixing calculations because:
- ✅ Single source of truth (data stored in correct units)
- ✅ Fixes all calculations automatically (view + API)
- ✅ No performance overhead from runtime conversions
- ✅ Prevents future bugs from unit confusion
- ✅ Aligns with schema documentation (which says m³/s)

---

## Preventing Future Issues

**Automatic Conversion During Ingestion**

The NHD data loader (`scripts/production/load_nhd_data.py`) has been updated to automatically convert flow values from CFS to m³/s during ingestion.

This means:
- ✅ Future NHD data loads will have correct units
- ✅ No manual conversion needed for new data
- ✅ Consistent units across all flow statistics

The conversion happens in the `convert_flow_cfs_to_m3s()` function and is applied to:
- All monthly mean flows (QA_01 through QA_12)
- All incremental flows (qincrama through qincrfma)
- Gage flow measurements (gageqma)

**Important:** If you've already loaded NHD data, you still need to run the one-time conversion script to fix existing data.

## Post-Conversion Checklist

After running the conversion:

- [ ] Verify sample flow values are ~35x smaller
- [ ] Check flow percentiles show reasonable distribution
- [ ] Restart API server
- [ ] Test API endpoints return correct percentiles
- [ ] Verify map exports show proper classifications
- [ ] Run species scoring tests to confirm suitability calculations
- [ ] Future NHD data ingestions will auto-convert (no action needed)

---

## Rollback (If Needed)

If you need to revert the conversion:

```sql
-- Multiply by 35.3147 to convert back to CFS
UPDATE nhd_flow_statistics
SET
    qama = qama * 35.3147,
    qbma = qbma * 35.3147,
    -- ... repeat for all columns
WHERE TRUE;

REFRESH MATERIALIZED VIEW map_current_conditions;
```

**Note:** This should only be needed if there was an error during conversion. The conversion to m³/s is the correct state.

---

## Related Files

- `scripts/setup/fix_flow_units_cfs_to_m3s.sql` - SQL conversion script
- `scripts/setup/run_fix_flow_units.py` - Python execution script
- `scripts/setup/create_map_current_conditions_view.sql` - View definition
- `src/metrics/flow_percentile.py` - Flow percentile calculations
- `scripts/setup/create_nhd_tables.sql` - Table schema (line 178: "m³/s")

---

## Questions?

If flow percentiles still seem incorrect after conversion:
1. Verify NWM streamflow data is actually in m³/s (not CFS)
2. Check that the conversion was applied (values should be ~35x smaller)
3. Ensure materialized view was refreshed
4. Review calculation logic in `flow_percentile.py`
