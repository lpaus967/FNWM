"""
Download and process NWM RouteLink file for NWM-NHD crosswalk

The RouteLink file maps NWM feature_id to NHDPlus COMID, enabling joins between
NWM forecast data and NHD spatial data.

HydroShare Resource: https://www.hydroshare.org/resource/7ce5f87bc1904d0c8f297389be5fa169/
"""
import logging
import os
import sys
from pathlib import Path

import pandas as pd
import requests
import xarray as xr

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# AWS S3 RouteLink file URL (NWM v2.1)
# This is the parameter file from the retrospective dataset
ROUTELINK_URL = "https://noaa-nwm-retrospective-2-1-pds.s3.amazonaws.com/model_output/RouteLink_NHDPLUS.nc"

# Alternative: Try NOAA NCO server
ROUTELINK_ALT_URL = "https://www.nco.ncep.noaa.gov/pmb/codes/nwprod/nwm.v2.1/parm/domain/RouteLink_NHDPLUS.nc"

# Output directory
OUTPUT_DIR = Path("data/routelink")


def download_routelink(output_path: Path, force_download: bool = False):
    """
    Download RouteLink NetCDF file from AWS S3 or NOAA.

    Args:
        output_path: Path to save the NetCDF file
        force_download: Re-download even if file exists
    """
    if output_path.exists() and not force_download:
        logger.info(f"RouteLink file already exists: {output_path}")
        logger.info("Use force_download=True to re-download")
        return output_path

    logger.info("=" * 80)
    logger.info("DOWNLOADING ROUTELINK FILE")
    logger.info("=" * 80)

    # Try multiple sources
    urls_to_try = [
        ("AWS S3 (NWM v2.1)", ROUTELINK_URL),
        ("NOAA NCO Server", ROUTELINK_ALT_URL)
    ]

    for source_name, url in urls_to_try:
        logger.info(f"\nTrying {source_name}...")
        logger.info(f"URL: {url}")

        try:
            # Create output directory
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Download file
            logger.info("Downloading... (this may take a few minutes)")
            response = requests.get(url, stream=True, timeout=300)
            response.raise_for_status()

            # Get file size
            total_size = int(response.headers.get('content-length', 0))
            logger.info(f"File size: {total_size / (1024**2):.1f} MB")

            # Write to file with progress
            downloaded = 0
            chunk_size = 8192

            with open(output_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=chunk_size):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)

                        # Log progress every 10 MB
                        if downloaded % (10 * 1024 * 1024) < chunk_size:
                            progress = (downloaded / total_size) * 100 if total_size > 0 else 0
                            logger.info(f"Progress: {progress:.1f}% ({downloaded / (1024**2):.1f} MB)")

            logger.info(f"✅ Download complete from {source_name}!")
            logger.info("")
            return output_path

        except Exception as e:
            logger.warning(f"⚠️  Failed to download from {source_name}: {e}")
            if output_path.exists():
                output_path.unlink()  # Remove partial download
            continue

    # If we get here, all downloads failed
    raise Exception("Failed to download RouteLink file from all sources")


def analyze_routelink(nc_path: Path):
    """
    Analyze RouteLink NetCDF file to understand the mapping.

    Args:
        nc_path: Path to RouteLink NetCDF file
    """
    logger.info("=" * 80)
    logger.info("ANALYZING ROUTELINK FILE")
    logger.info("=" * 80)
    logger.info("")

    try:
        # Open NetCDF file
        logger.info("Opening NetCDF file...")
        ds = xr.open_dataset(nc_path)

        logger.info(f"\nVariables in RouteLink file:")
        for var in ds.variables:
            logger.info(f"  - {var}: {ds[var].dims}")
        logger.info("")

        # Look for key variables
        if 'link' in ds.variables:
            logger.info(f"Found 'link' variable (NWM feature_id)")
            logger.info(f"  Shape: {ds['link'].shape}")
            logger.info(f"  Sample values: {ds['link'].values[:10]}")

        if 'NHDPlusV2_COMID' in ds.variables:
            logger.info(f"\nFound 'NHDPlusV2_COMID' variable!")
            logger.info(f"  Shape: {ds['NHDPlusV2_COMID'].shape}")
            logger.info(f"  Sample values: {ds['NHDPlusV2_COMID'].values[:10]}")
        elif 'COMID' in ds.variables:
            logger.info(f"\nFound 'COMID' variable!")
            logger.info(f"  Shape: {ds['COMID'].shape}")
            logger.info(f"  Sample values: {ds['COMID'].values[:10]}")
        else:
            logger.warning("\n⚠️  No COMID variable found - checking all variables...")
            for var in ds.variables:
                if 'comid' in var.lower() or 'nhd' in var.lower():
                    logger.info(f"  Found: {var}")

        # Create sample crosswalk
        if 'link' in ds.variables and 'NHDPlusV2_COMID' in ds.variables:
            logger.info(f"\n✅ Can create crosswalk table!")
            logger.info(f"Total records: {len(ds['link']):,}")

            # Show sample mapping
            logger.info(f"\nSample NWM -> NHD mapping:")
            for i in range(min(10, len(ds['link']))):
                nwm_id = int(ds['link'].values[i])
                nhd_id = int(ds['NHDPlusV2_COMID'].values[i])
                logger.info(f"  NWM {nwm_id} -> NHD {nhd_id}")

        ds.close()
        logger.info("")
        logger.info("✅ Analysis complete!")
        logger.info("")

    except Exception as e:
        logger.error(f"❌ Analysis failed: {e}")
        raise


if __name__ == "__main__":
    # Download RouteLink file
    output_path = OUTPUT_DIR / "RouteLink_NHDPLUS.nc"

    try:
        download_routelink(output_path, force_download=False)
        analyze_routelink(output_path)

        logger.info("=" * 80)
        logger.info("NEXT STEPS")
        logger.info("=" * 80)
        logger.info("1. Review the RouteLink mapping above")
        logger.info("2. Create database table for NWM-NHD crosswalk")
        logger.info("3. Load RouteLink data into database")
        logger.info("4. Update ingestion script to filter by mapped feature IDs")
        logger.info("")

    except Exception as e:
        logger.error(f"Script failed: {e}")
        sys.exit(1)
