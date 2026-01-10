# HRRR Wind Data Pipeline

Automated pipeline for downloading, processing, and uploading HRRR wind forecast data to AWS S3.

## Overview

This pipeline:
1. Downloads HRRR (High-Resolution Rapid Refresh) wind data from NOAA NOMADS
2. Processes GRIB2 files to extract u/v wind components at 10m height
3. Uploads processed data to AWS S3 for storage and analysis

## Quick Start

### Prerequisites

1. **Python Dependencies**

   **Option A: Using Conda (Recommended)**

   Update your existing `fnwm` conda environment:
   ```bash
   # From repo root
   conda env update -f environment.yml --prune
   conda activate fnwm
   ```

   Or install standalone wind environment:
   ```bash
   # From this directory
   cd scripts/satellite_data/wind
   conda env create -f environment.yml
   conda activate fnwm-wind
   ```

   **Option B: Using pip**
   ```bash
   pip install requests boto3

   # Then install GDAL separately
   # macOS: brew install gdal
   # Linux: apt-get install gdal-bin
   # Windows: conda install -c conda-forge gdal
   ```

2. **AWS Credentials**
   Configure AWS credentials with S3 access:
   ```bash
   aws configure
   ```

   Or set environment variables:
   ```bash
   export AWS_ACCESS_KEY_ID='your_key'
   export AWS_SECRET_ACCESS_KEY='your_secret'
   export AWS_DEFAULT_REGION='us-east-2'
   ```

4. **Terraform** (for S3 bucket creation)
   The S3 bucket must be created first using Terraform:
   ```bash
   cd ../../../  # Navigate to repo root
   terraform apply
   ```

### Run Complete Pipeline

```bash
cd scripts/satellite_data/wind
python run_pipeline.py
```

This will:
- Download the HRRR file closest to current time
- Process it to extract wind components
- Upload to S3 bucket: `s3://fnwm-wind-data/hrrr/YYYY/MM/DD/`
- Clean up local files
- Delete S3 objects older than 7 days

## Scripts

### `run_pipeline.py` - Complete Workflow

Runs the full pipeline from download to upload.

**Usage:**
```bash
python run_pipeline.py
```

### `dataFetcher.py` - Download HRRR Data

Downloads GRIB files from NOAA NOMADS server.

**Functions:**
- `fetch_current_time_hrrr()` - Download file closest to current time (default)
- `fetch_hrrr_data(hours=[...])` - Download specific forecast hours

**Output:** `data/satellite/wind/rawGrib/`

**Standalone Usage:**
```bash
python dataFetcher.py
```

### `processGrib.py` - Extract Wind Bands

Uses GDAL to extract wind component bands from GRIB files.

**Extracted Bands:**
- Band 77: u-component of wind (m/s) at 10m height
- Band 78: v-component of wind (m/s) at 10m height

**Input:** `data/satellite/wind/rawGrib/`
**Output:** `data/satellite/wind/processed/`

**Standalone Usage:**
```bash
python processGrib.py
```

### `uploadToS3.py` - Upload to AWS S3

Uploads processed GRIB files to S3 with metadata.

**Features:**
- Organizes files by date: `hrrr/YYYY/MM/DD/`
- Attaches metadata (upload time, data type, source)
- Automatic cleanup of old data (7 days)
- Verification of uploads

**Standalone Usage:**
```bash
python uploadToS3.py
```

## Configuration

### Directory Structure

```
FNWM/
├── scripts/
│   └── satellite_data/
│       └── wind/
│           ├── dataFetcher.py
│           ├── processGrib.py
│           ├── uploadToS3.py
│           ├── run_pipeline.py
│           └── README.md
└── data/
    └── satellite/
        └── wind/
            ├── rawGrib/       # Downloaded GRIB files
            └── processed/     # Processed GRIB files (bands 77, 78)
```

### S3 Bucket Structure

```
s3://fnwm-wind-data/
└── hrrr/
    └── YYYY/
        └── MM/
            └── DD/
                ├── hrrr.t00z.wrfsfcf00_processed.grib2
                ├── hrrr.t01z.wrfsfcf00_processed.grib2
                └── ...
```

### Customization

#### Change Download Hours

Edit `dataFetcher.py`:
```python
# Download specific hours instead of current time
hours_to_download = [0, 6, 12, 18]  # 00z, 06z, 12z, 18z
results = fetch_hrrr_data(hours=hours_to_download)
```

#### Change Extracted Bands

Edit `processGrib.py`:
```python
# Extract different bands
bands_to_extract = [77, 78]  # Modify as needed
```

#### Change S3 Retention Period

Edit `uploadToS3.py`:
```python
# Change from 7 to 30 days
uploader.delete_old_objects(prefix='hrrr/', days_old=30)
```

#### Change S3 Bucket Name

Edit `uploadToS3.py`:
```python
bucket_name = "your-custom-bucket-name"
```

And update Terraform configuration in `main.tf`.

## Automation

### Cron Job (Linux/macOS)

Create a script `~/wind_pipeline.sh`:
```bash
#!/bin/bash
export AWS_ACCESS_KEY_ID='your_key'
export AWS_SECRET_ACCESS_KEY='your_secret'

cd "/path/to/FNWM/scripts/satellite_data/wind"
python run_pipeline.py >> /tmp/wind_pipeline.log 2>&1
```

Make it executable:
```bash
chmod +x ~/wind_pipeline.sh
```

Add to crontab:
```bash
crontab -e

# Run every 6 hours
0 */6 * * * ~/wind_pipeline.sh
```

### GitHub Actions

Create `.github/workflows/wind-pipeline.yml`:
```yaml
name: Wind Data Pipeline

on:
  schedule:
    - cron: '0 */6 * * *'  # Every 6 hours
  workflow_dispatch:  # Manual trigger

jobs:
  run-pipeline:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install requests boto3
          sudo apt-get update
          sudo apt-get install -y gdal-bin

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v2
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: us-east-2

      - name: Run pipeline
        run: |
          cd scripts/satellite_data/wind
          python run_pipeline.py
```

## Data Sources

### HRRR (High-Resolution Rapid Refresh)

- **Provider:** NOAA NCEP
- **URL:** https://nomads.ncep.noaa.gov/pub/data/nccf/com/hrrr/prod/
- **Update Frequency:** Hourly
- **Spatial Resolution:** 3 km
- **Domain:** Continental United States (CONUS)
- **File Format:** GRIB2

### Wind Components

- **Band 77:** u-component (eastward) wind at 10m height (m/s)
- **Band 78:** v-component (northward) wind at 10m height (m/s)

To calculate wind speed and direction:
```python
import numpy as np

# Wind speed (m/s)
wind_speed = np.sqrt(u**2 + v**2)

# Wind direction (degrees, meteorological convention)
wind_direction = np.arctan2(-u, -v) * 180 / np.pi
wind_direction = (wind_direction + 360) % 360
```

## Troubleshooting

### GDAL Not Found

**Error:** `gdal_translate not found`

**Solution:**
```bash
# macOS
brew install gdal

# Linux
sudo apt-get install gdal-bin

# Windows (via conda)
conda install -c conda-forge gdal
```

### S3 Bucket Does Not Exist

**Error:** `Bucket does not exist: fnwm-wind-data`

**Solution:**
```bash
cd ../../../  # Navigate to repo root
terraform apply
```

### AWS Credentials Not Configured

**Error:** `Unable to locate credentials`

**Solution:**
```bash
aws configure
# Or set environment variables
export AWS_ACCESS_KEY_ID='your_key'
export AWS_SECRET_ACCESS_KEY='your_secret'
```

### No Data Available for Current Hour

**Error:** `No files found in directory listing`

**Solution:**
NOAA servers may have delays. The script automatically searches for the nearest available hour. If this persists, check NOAA server status: https://nomads.ncep.noaa.gov/

### Download Times Out

**Error:** `Error downloading: timeout`

**Solution:**
Increase timeout in `dataFetcher.py`:
```python
response = requests.get(url, stream=True, timeout=600)  # Increase from 300
```

## Cost Considerations

### S3 Storage

- **Storage:** ~$0.023/GB/month (Standard tier)
- **Typical file size:** ~140 MB per processed file
- **7-day retention:** ~980 MB daily → ~$0.023/month
- **30-day retention:** ~4.2 GB daily → ~$0.10/month

### Data Transfer

- **Upload:** Free (data transfer to S3)
- **Download:** $0.09/GB (first 10 TB/month)

### Optimization

To reduce costs:
1. Use S3 Intelligent-Tiering for automatic cost optimization
2. Enable S3 lifecycle policies for automatic deletion
3. Compress GRIB files before upload (use gzip)

## Improvements from Original Scripts

1. **S3 Instead of Mapbox**
   - Lower cost for data storage
   - Better for archival and analysis
   - No tileset processing delays

2. **Better Error Handling**
   - Graceful fallback for missing data
   - Clear error messages with solutions
   - Automatic retry logic

3. **Flexible Configuration**
   - Cross-platform path handling
   - Environment-based configuration
   - Modular design for easy customization

4. **Enhanced Logging**
   - Structured logging with timestamps
   - Progress indicators for downloads
   - Detailed upload summaries

5. **Automated Cleanup**
   - Local file cleanup after upload
   - S3 retention policy (7 days default)
   - Prevents storage buildup

6. **Metadata Tagging**
   - Upload timestamps
   - Data source information
   - Band information for easy filtering

## License

This project is part of the FNWM (Fisheries and Natural Water Management) repository.

## Support

For issues or questions, please contact the FNWM development team or create an issue in the GitHub repository.
