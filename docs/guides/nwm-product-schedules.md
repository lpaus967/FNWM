# NWM Product Schedules

Quick reference for when each NWM product is available.

## Product Availability

| Product | Cycle Frequency | Valid Hours | Notes |
|---------|----------------|-------------|-------|
| **analysis_assim** | Hourly | 00-23Z | Every hour, with data assimilation |
| **short_range** | Hourly | 00-23Z | 18-hour forecast (f001-f018), every hour |
| **medium_range_blend** | 6-hourly | 00, 06, 12, 18Z | 10-day ensemble forecast |
| **analysis_assim_no_da** | Daily | 00Z only | Midnight UTC only, no data assimilation |

## Ingestion Script Behavior

### Subset Ingestion (`scripts/dev/run_subset_ingestion.py`)

```python
# Example: Using 20:00 UTC
target_date = datetime(2026, 1, 4, 20, 0, 0, tzinfo=timezone.utc)

# What gets ingested:
# ✅ analysis_assim (f000)        - Always available
# ✅ short_range (f001, f018)     - Always available
# ❌ medium_range_blend (f024)    - SKIPPED (needs 00/06/12/18Z)
# ❌ analysis_assim_no_da (f000)  - SKIPPED (needs 00Z)
```

```python
# Example: Using midnight UTC
target_date = datetime(2026, 1, 4, 0, 0, 0, tzinfo=timezone.utc)

# What gets ingested:
# ✅ analysis_assim (f000)        - Available
# ✅ short_range (f001, f018)     - Available
# ✅ medium_range_blend (f024)    - Available (00Z)
# ✅ analysis_assim_no_da (f000)  - Available (00Z)
```

## Best Practices

### For Testing (Subset Ingestion)

**Use any hour** for quick tests:
- `analysis_assim` and `short_range` work at any hour
- Good for rapid iteration

**Use 00Z/06Z/12Z/18Z** for comprehensive tests:
- Adds `medium_range_blend` data
- More complete dataset

**Use 00Z only** for full product coverage:
- All 4 products available
- Most complete test

### For Production (Full Ingestion)

**Run at 00Z** to get all products:
```python
target_date = datetime(2026, 1, 4, 0, 0, 0, tzinfo=timezone.utc)
```

**Or run analysis_assim + short_range hourly**:
- Skip `analysis_assim_no_da` (we don't strictly need it)
- Run `medium_range_blend` only at 00/06/12/18Z

## Why analysis_assim_no_da Matters

**Purpose**: Non-data-assimilated "free run" for ecological analysis

**Use Case**:
- Species ecology decisions should use non-assimilated data
- Gauge-corrected data (`analysis_assim`) for display only

**Note**: We currently don't use it in EPIC 2-6 because:
1. All BDI variables are available in `analysis_assim`
2. Thermal component (EPIC 3) not yet implemented
3. Can add later when we need pure hydrologic signal

## Recommended Ingestion Schedule

For production deployment:

```bash
# Cron schedule
# Every hour: analysis_assim + short_range
0 * * * * /path/to/run_hourly_ingestion.py

# Every 6 hours: medium_range_blend
0 0,6,12,18 * * * /path/to/run_medium_range_ingestion.py

# Daily at midnight: analysis_assim_no_da (optional)
0 0 * * * /path/to/run_no_da_ingestion.py
```

This ensures:
- Current conditions always fresh (hourly)
- 18-hour forecast always fresh (hourly)
- 10-day outlook updated 4x/day
- Non-assimilated baseline once/day

---

## Error Messages Explained

### "Invalid cycle hour X for product 'analysis_assim_no_da'. Valid hours: [0]"

**Cause**: Trying to fetch `analysis_assim_no_da` at a non-midnight hour

**Fix**: Change target_date to hour 0, or script will auto-skip

### "Invalid cycle hour X for product 'medium_range_blend'. Valid hours: [0, 6, 12, 18]"

**Cause**: Trying to fetch `medium_range_blend` outside 6-hour windows

**Fix**: Change target_date to 00/06/12/18Z, or script will auto-skip

---

## Testing Your Setup

```bash
# Test with hour 20 (most products work)
python scripts/dev/run_subset_ingestion.py  # Default: hour 0

# Or modify the script to test different hours:
# Line 171: target_date = datetime(2026, 1, 4, 20, 0, 0, tzinfo=timezone.utc)
```

Expected output:
```
✅ analysis_assim: 593,806 records
✅ short_range f001: 593,806 records
✅ short_range f018: 593,806 records
⚠️  medium_range_blend SKIPPED (only runs at 00/06/12/18Z, got 20Z)
⚠️  analysis_assim_no_da SKIPPED (only runs at 00Z, got 20Z)
```

This is **correct behavior** - the script gracefully skips unavailable products!
