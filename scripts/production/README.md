# Production Scripts

Scripts for production data ingestion and database management.

## Database Reset and Repopulation

### `reset_and_repopulate_db.py`

Complete workflow for resetting and repopulating the database when changing geographic locations or starting fresh.

**Full Reset (with confirmation):**
```bash
python scripts/production/reset_and_repopulate_db.py \
    --nhd-geojson "D:\Data\nhdHydrologyExample.geojson"
```

**Automated Reset (skip confirmation):**
```bash
python scripts/production/reset_and_repopulate_db.py \
    --nhd-geojson "path/to/data.geojson" \
    --skip-confirmation
```

**Reset without Temperature Data:**
```bash
python scripts/production/reset_and_repopulate_db.py \
    --nhd-geojson "data.geojson" \
    --skip-temperature
```

**Temperature for Limited Reaches:**
```bash
python scripts/production/reset_and_repopulate_db.py \
    --nhd-geojson "data.geojson" \
    --temp-reaches 50 \
    --temp-forecast-days 7
```

**Options:**
- `--nhd-geojson`: Path to NHDPlus GeoJSON file (REQUIRED)
- `--temp-reaches`: Number of reaches to fetch temperature for (default: all)
- `--temp-forecast-days`: Days of forecast to fetch (default: 7, max: 16)
- `--temp-batch-size`: Batch size for API calls (default: 50)
- `--temp-delay`: Delay between API calls in seconds (default: 1.0)
- `--skip-confirmation`: Skip confirmation prompt
- `--skip-nwm`: Skip NWM hydrology ingestion
- `--skip-temperature`: Skip temperature ingestion

### Workflow Steps

The script performs these steps automatically:

1. **Clear Tables** - Truncates all database tables (with confirmation)
2. **Load NHD Data** - Imports spatial data from GeoJSON
3. **Extract Centroids** - Generates lat/lon for temperature API
4. **Ingest NWM Data** - Fetches hydrology time-series (filtered by loaded reaches)
5. **Ingest Temperature** - Fetches temperature forecasts from Open-Meteo

## Clear Tables Only

### Python Module

```python
from src.database.clear_tables import clear_all_tables, clear_specific_tables
import psycopg2

# Connect to database
conn = psycopg2.connect(...)

# Clear all tables (with confirmation)
clear_all_tables(conn)

# Clear all tables (no confirmation)
clear_all_tables(conn, skip_confirmation=True)

# Clear specific tables
clear_specific_tables(conn, ['hydro_timeseries', 'ingestion_log'])
```

### Command Line

```bash
# Clear all tables (with confirmation)
python -m src.database.clear_tables

# Clear all tables (no confirmation)
python -m src.database.clear_tables --skip-confirmation

# Clear specific tables
python -m src.database.clear_tables --tables hydro_timeseries ingestion_log

# Silent mode
python -m src.database.clear_tables --skip-confirmation --quiet
```

## Individual Ingestion Scripts

### Load NHD Data

```bash
python scripts/production/load_nhd_data.py "path/to/nhdHydrology.geojson"
```

Loads NHDPlus spatial data into:
- `nhd_flowlines` - Stream geometries and attributes
- `nhd_network_topology` - Network connectivity
- `nhd_flow_statistics` - Historical flow statistics

### Ingest NWM Hydrology Data

```bash
# Subset ingestion (filtered by loaded NHD reaches)
python scripts/dev/run_subset_ingestion.py

# Full ingestion (all 2.7M reaches)
python scripts/production/run_full_ingestion.py
```

Ingests National Water Model data into `hydro_timeseries` table.

### Ingest Temperature Data

```bash
# All reaches, 7-day forecast
python scripts/production/ingest_temperature.py

# Limited reaches
python scripts/production/ingest_temperature.py --reaches 100

# Extended forecast
python scripts/production/ingest_temperature.py --forecast-days 16

# Custom batch size and delay
python scripts/production/ingest_temperature.py \
    --batch-size 25 \
    --delay 2.0
```

Fetches temperature data from Open-Meteo API into `temperature_timeseries` table.

## Database Tables

### Core Hydrology
- `hydro_timeseries` - NWM time-series data (TimescaleDB hypertable)
- `reach_metadata` - Stream reach information
- `ingestion_log` - Data pipeline monitoring

### NHD Spatial
- `nhd_flowlines` - Stream geometries (PostGIS)
- `nhd_network_topology` - Network connectivity
- `nhd_flow_statistics` - Historical flow statistics
- `nhd_reach_centroids` - Lat/lon for temperature API

### Temperature
- `temperature_timeseries` - Open-Meteo forecasts

### User Data
- `user_observations` - Trip reports and hatch observations
- `computed_scores` - Cached species suitability scores

## Common Use Cases

### Change Geographic Region

```bash
python scripts/production/reset_and_repopulate_db.py \
    --nhd-geojson "D:\Data\new_region.geojson"
```

### Fresh Start (Development)

```bash
python scripts/production/reset_and_repopulate_db.py \
    --nhd-geojson "D:\Data\small_test.geojson" \
    --temp-reaches 10 \
    --skip-confirmation
```

### Clear and Reload NHD Only

```bash
# Clear NHD tables
python -m src.database.clear_tables \
    --tables nhd_flowlines nhd_network_topology nhd_flow_statistics nhd_reach_centroids \
    --skip-confirmation

# Reload NHD data
python scripts/production/load_nhd_data.py "new_data.geojson"

# Extract centroids
python scripts/setup/init_nhd_centroids.py
```

### Update Temperature Data Only

```bash
# Clear temperature table
python -m src.database.clear_tables --tables temperature_timeseries --skip-confirmation

# Re-ingest
python scripts/production/ingest_temperature.py --forecast-days 7
```
