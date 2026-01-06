"""
Quick Feature ID Counter

Counts the total number of unique CONUS feature IDs from a single NWM file.
Uses this to estimate the size of a full ingestion.
"""

import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent.parent.parent / 'src'
sys.path.insert(0, str(src_path))

import xarray as xr
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def count_feature_ids(netcdf_path: Path) -> int:
    """
    Count unique feature IDs in a NetCDF file.

    Args:
        netcdf_path: Path to NetCDF file

    Returns:
        Number of unique feature IDs
    """
    logger.info(f"Reading feature IDs from: {netcdf_path}")

    # Open dataset and read only feature_id variable (very fast)
    ds = xr.open_dataset(netcdf_path)
    feature_ids = ds['feature_id'].values
    ds.close()

    # Count unique IDs
    unique_ids = len(set(feature_ids))
    total_ids = len(feature_ids)

    logger.info(f"Total feature IDs: {total_ids:,}")
    logger.info(f"Unique feature IDs: {unique_ids:,}")

    return unique_ids


def estimate_ingestion_size(num_features: int):
    """
    Estimate the size of a full ingestion.

    Args:
        num_features: Number of unique feature IDs
    """
    logger.info("\n" + "=" * 80)
    logger.info("FULL INGESTION SIZE ESTIMATE")
    logger.info("=" * 80)

    # Variables per reach
    variables_per_reach = 6  # streamflow, velocity, qSfcLatRunoff, qBucket, qBtmVertRunoff, nudge

    # Product 1: analysis_assim (f000 only)
    analysis_assim_records = num_features * variables_per_reach
    logger.info(f"\nProduct 1: analysis_assim")
    logger.info(f"  Forecast hours: 1 (f000)")
    logger.info(f"  Records: {analysis_assim_records:,}")

    # Product 2: short_range (f001-f018)
    short_range_hours = 18
    short_range_records = num_features * variables_per_reach * short_range_hours
    logger.info(f"\nProduct 2: short_range")
    logger.info(f"  Forecast hours: {short_range_hours} (f001-f018)")
    logger.info(f"  Records: {short_range_records:,}")

    # Product 3: medium_range_blend (f024, f048, f072, f096, f120, f144, f168, f192, f216, f240)
    medium_range_hours = 10
    medium_range_records = num_features * variables_per_reach * medium_range_hours
    logger.info(f"\nProduct 3: medium_range_blend")
    logger.info(f"  Forecast hours: {medium_range_hours} (f024 through f240, every 24h)")
    logger.info(f"  Records: {medium_range_records:,}")

    # Product 4: analysis_assim_no_da (f000 only)
    analysis_assim_no_da_records = num_features * variables_per_reach
    logger.info(f"\nProduct 4: analysis_assim_no_da")
    logger.info(f"  Forecast hours: 1 (f000)")
    logger.info(f"  Records: {analysis_assim_no_da_records:,}")

    # Total
    total_records = (
        analysis_assim_records +
        short_range_records +
        medium_range_records +
        analysis_assim_no_da_records
    )

    logger.info("\n" + "=" * 80)
    logger.info(f"TOTAL ESTIMATED RECORDS: {total_records:,}")
    logger.info("=" * 80)

    # Storage estimate (rough)
    # Assume ~8 bytes per float value + overhead
    bytes_per_record = 10  # Conservative estimate
    total_mb = (total_records * bytes_per_record) / (1024 * 1024)
    total_gb = total_mb / 1024

    logger.info(f"\nEstimated database storage: ~{total_gb:.2f} GB per hourly cycle")
    logger.info(f"(Per day at hourly ingestion: ~{total_gb * 24:.2f} GB)")

    # Time estimate (very rough, depends on hardware)
    logger.info(f"\n⚠️  This is for ONE hourly cycle (e.g., 2026-01-03 00Z)")
    logger.info(f"   For continuous operation, multiply by cycles per day (24)")


if __name__ == "__main__":
    # Use a cached file (should exist from previous runs)
    data_dir = Path(__file__).parent.parent.parent / 'data' / 'raw' / 'nwm'

    # Try to find any cached CONUS file
    cached_files = list(data_dir.glob("*_conus.nc"))

    if not cached_files:
        logger.error("No cached CONUS NetCDF files found in data/raw/nwm/")
        logger.error("Please run the subset ingestion first to download a file.")
        sys.exit(1)

    # Use the first cached file
    netcdf_path = cached_files[0]
    logger.info(f"Using cached file: {netcdf_path.name}")

    # Count feature IDs
    num_features = count_feature_ids(netcdf_path)

    # Estimate ingestion size
    estimate_ingestion_size(num_features)

    logger.info("\n✅ Count complete!")
