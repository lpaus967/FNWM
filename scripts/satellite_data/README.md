# Satellite Data Scripts

This directory contains scripts for fetching, processing, and storing satellite data for the FNWM project.

## Available Data Sources

### Wind Data (`wind/`)

HRRR (High-Resolution Rapid Refresh) wind forecast data from NOAA.

- **Data Source:** NOAA NOMADS HRRR
- **Update Frequency:** Hourly
- **Spatial Resolution:** 3 km
- **Storage:** AWS S3 (`s3://fnwm-wind-data/`)
- **Retention:** 7 days

**Quick Start:**
```bash
cd wind
python run_pipeline.py
```

See [wind/README.md](wind/README.md) for detailed documentation.

## Future Data Sources

This directory structure is designed to accommodate additional satellite data sources:

- **Precipitation** - Radar and satellite precipitation data
- **Temperature** - Surface and upper-air temperature data
- **Cloud Cover** - Satellite cloud imagery
- **Sea Surface Temperature** - For coastal/marine applications
- **Vegetation Indices** - NDVI and other vegetation metrics

## Directory Structure

```
satellite_data/
├── README.md           # This file
└── wind/               # HRRR wind data pipeline
    ├── README.md       # Wind data documentation
    ├── requirements.txt
    ├── dataFetcher.py  # Download HRRR data
    ├── processGrib.py  # Process GRIB files
    ├── uploadToS3.py   # Upload to S3
    └── run_pipeline.py # Complete pipeline
```

## General Setup

### Prerequisites

1. **Python 3.9+**
2. **AWS Credentials** - Configured via `aws configure` or environment variables
3. **Terraform** - For creating S3 buckets and other infrastructure

### Infrastructure Setup

Before running any pipeline, create the necessary S3 buckets:

```bash
cd ../../..  # Navigate to repo root
terraform init
terraform apply
```

This creates:
- `fnwm-wind-data` - Wind data storage bucket

### Python Dependencies

Each data source has its own `requirements.txt`:

```bash
cd wind
pip install -r requirements.txt
```

## AWS S3 Organization

All satellite data is stored in S3 with the following structure:

```
s3://fnwm-{data-type}/
└── {source}/
    └── YYYY/
        └── MM/
            └── DD/
                └── data files
```

Example:
```
s3://fnwm-wind-data/
└── hrrr/
    └── 2025/
        └── 01/
            └── 06/
                ├── hrrr.t00z.wrfsfcf00_processed.grib2
                ├── hrrr.t06z.wrfsfcf00_processed.grib2
                └── ...
```

## Data Retention

Each bucket has lifecycle policies configured via Terraform:

- **Wind Data:** 7 days
- **Future data sources:** To be determined based on use case

## Contributing

When adding new satellite data sources:

1. Create a new directory under `satellite_data/`
2. Follow the structure of the `wind/` directory
3. Include:
   - `README.md` - Documentation
   - `requirements.txt` - Python dependencies
   - Individual scripts for fetch, process, upload
   - `run_pipeline.py` - Complete pipeline
4. Update Terraform configuration in `main.tf` for S3 buckets
5. Update this README with the new data source

## License

This project is part of the FNWM (Fisheries and Natural Water Management) repository.
