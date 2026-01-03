"""
NWM HTTP Client for Fisheries-Focused Data Ingestion

This module provides a minimal, opinionated client for downloading only the NWM products
needed for fisheries intelligence.

Design Principles:
- Selectivity beats completeness: Only ingest the 4 products we use
- Fail fast with explicit errors
- Log all download attempts for monitoring
"""

import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal, Optional
from urllib.parse import urljoin

import pandas as pd
import requests
import xarray as xr
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=os.getenv('LOG_LEVEL', 'INFO'),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Type aliases for clarity
NWMProduct = Literal[
    "analysis_assim",
    "short_range",
    "medium_range_blend",
    "analysis_assim_no_da"
]

Domain = Literal["conus", "alaska", "hawaii", "puertorico"]


class NWMClient:
    """
    Client for downloading NWM channel routing products from NOAA NOMADS.

    This client ONLY supports the 4 products required for fisheries intelligence.
    It will not download any other NWM products.
    """

    # NOAA NOMADS base URL
    BASE_URL = "https://nomads.ncep.noaa.gov/pub/data/nccf/com/nwm/prod/"

    # Product paths relative to BASE_URL
    PRODUCT_PATHS = {
        "analysis_assim": "nwm.{date}/analysis_assim/nwm.t{hour:02d}z.analysis_assim.channel_rt.tm00.conus.nc",
        "short_range": "nwm.{date}/short_range/nwm.t{hour:02d}z.short_range.channel_rt.f{forecast:03d}.conus.nc",
        "medium_range_blend": "nwm.{date}/medium_range_blend/nwm.t{hour:02d}z.medium_range_blend.channel_rt.f{forecast:03d}.conus.nc",
        "analysis_assim_no_da": "nwm.{date}/analysis_assim_no_da/nwm.t{hour:02d}z.analysis_assim_no_da.channel_rt.tm00.conus.nc",
    }

    # Cycle hours for each product
    CYCLE_HOURS = {
        "analysis_assim": list(range(0, 24)),  # Every hour
        "short_range": list(range(0, 24)),     # Every hour
        "medium_range_blend": [0, 6, 12, 18],  # Every 6 hours
        "analysis_assim_no_da": [0],           # Daily at 00Z
    }

    # Forecast hours for each product
    FORECAST_HOURS = {
        "analysis_assim": [0],                    # No forecast (tm00 = analysis)
        "short_range": list(range(1, 19)),        # f001 to f018
        "medium_range_blend": list(range(3, 241, 3)),  # f003 to f240, every 3 hours
        "analysis_assim_no_da": [0],              # No forecast
    }

    def __init__(
        self,
        base_url: Optional[str] = None,
        cache_dir: Optional[Path] = None,
        timeout: int = 300
    ):
        """
        Initialize NWM client.

        Args:
            base_url: Override default NOAA NOMADS URL (for testing)
            cache_dir: Directory to cache downloaded files
            timeout: HTTP request timeout in seconds
        """
        self.base_url = base_url or os.getenv('NWM_BASE_URL', self.BASE_URL)
        self.cache_dir = cache_dir or Path(os.getenv('NWM_CACHE_DIR', 'data/raw/nwm'))
        self.timeout = timeout

        # Create cache directory if it doesn't exist
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"NWM Client initialized with base_url={self.base_url}")

    def download_product(
        self,
        product: NWMProduct,
        reference_time: datetime,
        forecast_hour: Optional[int] = None,
        domain: Domain = "conus",
        force_download: bool = False
    ) -> Path:
        """
        Download a specific NWM product.

        Args:
            product: NWM product name
            reference_time: Model cycle reference time (UTC)
            forecast_hour: Forecast hour (for forecast products)
            domain: Geographic domain
            force_download: Re-download even if cached

        Returns:
            Path to downloaded NetCDF file

        Raises:
            ValueError: Invalid product or parameters
            requests.HTTPError: Download failed
        """
        # Validate product
        if product not in self.PRODUCT_PATHS:
            raise ValueError(
                f"Invalid product '{product}'. "
                f"Must be one of: {list(self.PRODUCT_PATHS.keys())}"
            )

        # Validate cycle hour
        if reference_time.hour not in self.CYCLE_HOURS[product]:
            raise ValueError(
                f"Invalid cycle hour {reference_time.hour} for product '{product}'. "
                f"Valid hours: {self.CYCLE_HOURS[product]}"
            )

        # Validate forecast hour
        expected_forecast_hours = self.FORECAST_HOURS[product]
        if forecast_hour is None:
            forecast_hour = expected_forecast_hours[0]

        if forecast_hour not in expected_forecast_hours:
            raise ValueError(
                f"Invalid forecast hour {forecast_hour} for product '{product}'. "
                f"Valid hours: {expected_forecast_hours}"
            )

        # Build URL
        date_str = reference_time.strftime("%Y%m%d")
        hour = reference_time.hour

        # Format product path
        product_path = self.PRODUCT_PATHS[product].format(
            date=date_str,
            hour=hour,
            forecast=forecast_hour
        )

        url = urljoin(self.base_url, product_path)

        # Determine cache file path
        cache_filename = f"{product}_{date_str}_t{hour:02d}z_f{forecast_hour:03d}_{domain}.nc"
        cache_path = self.cache_dir / cache_filename

        # Check cache
        if cache_path.exists() and not force_download:
            logger.info(f"Using cached file: {cache_path}")
            return cache_path

        # Download file
        logger.info(f"Downloading {product} from {url}")

        try:
            response = requests.get(url, timeout=self.timeout, stream=True)
            response.raise_for_status()

            # Write to cache
            with open(cache_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            file_size_mb = cache_path.stat().st_size / (1024 * 1024)
            logger.info(f"Downloaded {file_size_mb:.2f} MB to {cache_path}")

            return cache_path

        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error downloading {url}: {e}")
            raise
        except requests.exceptions.Timeout:
            logger.error(f"Timeout downloading {url}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error downloading {url}: {e}")
            raise

    def parse_channel_rt(
        self,
        filepath: Path,
        feature_ids: Optional[list[int]] = None
    ) -> pd.DataFrame:
        """
        Parse NWM channel routing NetCDF file.

        Extracts key variables for fisheries intelligence:
        - streamflow (m³/s)
        - velocity (m/s)
        - Component flows (qSfcLatRunoff, qBucket, qBtmVertRunoff)
        - nudge (for gauge-corrected products)

        Args:
            filepath: Path to NetCDF file
            feature_ids: Optional list of feature IDs to filter (for testing)

        Returns:
            DataFrame with hydrology variables
        """
        logger.info(f"Parsing NetCDF: {filepath}")

        try:
            ds = xr.open_dataset(filepath)

            # Extract core variables
            data = {
                'feature_id': ds['feature_id'].values,
                'streamflow_m3s': ds['streamflow'].values,
                'velocity_ms': ds['velocity'].values,
                'qSfcLatRunoff_m3s': ds['qSfcLatRunoff'].values,
                'qBucket_m3s': ds['qBucket'].values,
                'qBtmVertRunoff_m3s': ds['qBtmVertRunoff'].values,
            }

            # Add nudge if available (only in analysis_assim)
            if 'nudge' in ds:
                data['nudge_m3s'] = ds['nudge'].values

            # Create DataFrame
            df = pd.DataFrame(data)

            # Extract reference time if available (scalar value, broadcast to all rows)
            if 'reference_time' in ds:
                # Convert numpy scalar to Python datetime
                ref_time_np = ds['reference_time'].values
                if hasattr(ref_time_np, 'item'):
                    ref_time_scalar = pd.to_datetime(ref_time_np.item())
                else:
                    ref_time_scalar = pd.to_datetime(ref_time_np)
                # This will broadcast the scalar to all rows automatically
                df['reference_time'] = ref_time_scalar

            # Filter by feature IDs if specified
            if feature_ids is not None:
                df = df[df['feature_id'].isin(feature_ids)]

            logger.info(f"Parsed {len(df):,} reaches with {len(df.columns)} variables")

            ds.close()

            return df

        except Exception as e:
            logger.error(f"Error parsing NetCDF {filepath}: {e}")
            raise

    def download_latest_analysis(
        self,
        domain: Domain = "conus"
    ) -> tuple[Path, datetime]:
        """
        Download the most recent analysis_assim product.

        This represents "now" in our time abstraction.

        Args:
            domain: Geographic domain

        Returns:
            Tuple of (file_path, reference_time)
        """
        # Start with current hour and work backwards
        now = datetime.utcnow()

        for hours_ago in range(0, 6):  # Try up to 6 hours back
            reference_time = now - timedelta(hours=hours_ago)
            reference_time = reference_time.replace(minute=0, second=0, microsecond=0)

            try:
                filepath = self.download_product(
                    product="analysis_assim",
                    reference_time=reference_time,
                    domain=domain
                )
                logger.info(f"Latest analysis from {reference_time}")
                return filepath, reference_time

            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 404:
                    logger.debug(f"Product not found for {reference_time}, trying earlier...")
                    continue
                else:
                    raise

        raise RuntimeError(
            f"Could not find analysis_assim product within last 6 hours. "
            f"NWM may be experiencing delays."
        )

    def download_short_range_forecast(
        self,
        reference_time: datetime,
        domain: Domain = "conus"
    ) -> list[Path]:
        """
        Download all forecast hours for a short_range cycle.

        This represents "today" in our time abstraction.

        Args:
            reference_time: Model cycle time (UTC)
            domain: Geographic domain

        Returns:
            List of paths to downloaded files (f001 to f018)
        """
        filepaths = []

        for forecast_hour in self.FORECAST_HOURS["short_range"]:
            try:
                filepath = self.download_product(
                    product="short_range",
                    reference_time=reference_time,
                    forecast_hour=forecast_hour,
                    domain=domain
                )
                filepaths.append(filepath)
            except Exception as e:
                logger.error(
                    f"Failed to download short_range f{forecast_hour:03d}: {e}"
                )
                # Continue with other forecast hours

        logger.info(f"Downloaded {len(filepaths)}/18 short_range forecast hours")
        return filepaths


def main():
    """
    Example usage and testing
    """
    client = NWMClient()

    # Test 1: Download latest analysis
    logger.info("=" * 60)
    logger.info("Test 1: Downloading latest analysis_assim")
    logger.info("=" * 60)

    try:
        filepath, ref_time = client.download_latest_analysis()
        logger.info(f"✅ Downloaded: {filepath}")
        logger.info(f"   Reference time: {ref_time}")

        # Parse the file
        df = client.parse_channel_rt(filepath)
        logger.info(f"   Parsed {len(df)} reaches")
        logger.info(f"   Sample data:\n{df.head()}")

    except Exception as e:
        logger.error(f"❌ Test 1 failed: {e}")

    # Test 2: Download specific short_range forecast
    logger.info("")
    logger.info("=" * 60)
    logger.info("Test 2: Downloading short_range f001")
    logger.info("=" * 60)

    try:
        # Use most recent 00Z cycle
        now = datetime.utcnow()
        ref_time = now.replace(hour=0, minute=0, second=0, microsecond=0)

        filepath = client.download_product(
            product="short_range",
            reference_time=ref_time,
            forecast_hour=1
        )
        logger.info(f"✅ Downloaded: {filepath}")

    except Exception as e:
        logger.error(f"❌ Test 2 failed: {e}")


if __name__ == "__main__":
    main()
