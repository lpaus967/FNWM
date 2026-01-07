#!/usr/bin/env python3
"""
Configuration for HRRR Wind Data Pipeline

Centralized configuration for URLs, paths, timeouts, and constants.
"""

from pathlib import Path

# Script and base directories
SCRIPT_DIR = Path(__file__).parent
BASE_DIR = SCRIPT_DIR.parent.parent.parent

# Data directories
RAW_GRIB_DIR = BASE_DIR / "data" / "satellite" / "wind" / "rawGrib"
PROCESSED_DIR = BASE_DIR / "data" / "satellite" / "wind" / "processed"

# NOAA HRRR configuration
HRRR_BASE_URL = "https://nomads.ncep.noaa.gov/pub/data/nccf/com/hrrr/prod/"
HRRR_FILE_PATTERN = "hrrr.t{hour:02d}z.wrfsfcf00.grib2"

# GRIB band configuration
WIND_BANDS = [77, 78]  # u and v wind components at 10m height
BAND_DESCRIPTIONS = {
    77: "u-component of wind (m/s) at 10m height",
    78: "v-component of wind (m/s) at 10m height"
}

# Network timeouts (seconds)
DIRECTORY_LISTING_TIMEOUT = 30
DOWNLOAD_TIMEOUT = 300

# Download configuration
DOWNLOAD_CHUNK_SIZE = 8192
DEFAULT_FORECAST_HOURS = [3, 7, 12, 16]

# S3 configuration
S3_BUCKET_NAME = "fnwm-wind-data"
S3_REGION = "us-east-2"
S3_PREFIX_TEMPLATE = "hrrr/{year}/{month:02d}/{day:02d}"
S3_RETENTION_DAYS = 7

# S3 metadata
S3_METADATA = {
    'data_type': 'hrrr_wind',
    'source': 'NOAA_NOMADS',
    'bands': 'u_v_10m'
}

# File patterns
GRIB_FILE_PATTERN = "*.grib2"
PROCESSED_FILE_PATTERN = "*_processed.grib2"
PROCESSED_SUFFIX = "_processed.grib2"

# Timezone
TIMEZONE = "America/New_York"
