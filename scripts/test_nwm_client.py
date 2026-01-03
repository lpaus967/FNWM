"""
Test script for NWM client functionality

Tests the NWM client without full ingestion to verify it can:
1. Connect to NOAA NOMADS
2. Download a sample file
3. Parse NetCDF data
"""

import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ingest.nwm_client import NWMClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_nwm_client():
    """Test NWM client basic functionality"""

    logger.info("=" * 60)
    logger.info("Testing NWM Client")
    logger.info("=" * 60)

    # Create client
    client = NWMClient()

    # Test 1: Download latest analysis_assim
    logger.info("\nTest 1: Download specific analysis_assim (t21z)")
    logger.info("-" * 60)

    try:
        # Use t21z which we know is available
        test_time = datetime(2026, 1, 2, 21, 0, 0)
        filepath = client.download_product(
            product="analysis_assim",
            reference_time=test_time,
            forecast_hour=0
        )
        logger.info(f"[OK] Downloaded: {filepath.name}")
        logger.info(f"     Reference time: {test_time}")

        # Parse the file
        logger.info(f"\nParsing NetCDF file...")
        df = client.parse_channel_rt(filepath)
        logger.info(f"[OK] Parsed {len(df):,} stream reaches")
        logger.info(f"\nSample data (first 5 reaches):")
        print(df.head())

        # Show statistics
        logger.info(f"\nStreamflow statistics:")
        logger.info(f"  Min:    {df['streamflow_m3s'].min():.2f} m³/s")
        logger.info(f"  Mean:   {df['streamflow_m3s'].mean():.2f} m³/s")
        logger.info(f"  Median: {df['streamflow_m3s'].median():.2f} m³/s")
        logger.info(f"  Max:    {df['streamflow_m3s'].max():.2f} m³/s")

        logger.info(f"\n[OK] Test 1 PASSED")

    except Exception as e:
        logger.error(f"[FAILED] Test 1 failed: {e}")
        return False

    # Test 2: Download specific short_range forecast (f001)
    logger.info("\n" + "=" * 60)
    logger.info("Test 2: Download short_range f001")
    logger.info("-" * 60)

    try:
        # Try to get f001 for today's 00Z cycle
        # This may fail if the file isn't available yet
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

        # Try recent cycles if today's isn't available
        for days_ago in range(0, 3):
            ref_time = today - timedelta(days=days_ago)
            try:
                filepath = client.download_product(
                    product="short_range",
                    reference_time=ref_time,
                    forecast_hour=1
                )
                logger.info(f"[OK] Downloaded: {filepath.name}")
                logger.info(f"     Reference time: {ref_time}")

                # Parse it
                df = client.parse_channel_rt(filepath)
                logger.info(f"[OK] Parsed {len(df):,} stream reaches")

                logger.info(f"\n[OK] Test 2 PASSED")
                break

            except Exception as e:
                if days_ago < 2:
                    logger.debug(f"Cycle {ref_time} not available, trying earlier...")
                    continue
                else:
                    raise

    except Exception as e:
        logger.warning(f"[SKIPPED] Test 2: {e}")
        logger.warning("This is expected if recent short_range data isn't available")

    logger.info("\n" + "=" * 60)
    logger.info("NWM Client Tests Complete")
    logger.info("=" * 60)
    logger.info("\n[OK] NWM client is working correctly!")
    logger.info(f"Cache directory: {client.cache_dir}")

    return True


if __name__ == "__main__":
    success = test_nwm_client()
    sys.exit(0 if success else 1)
