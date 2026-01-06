"""
Run Full NWM Ingestion Workflow

Ingests all 4 NWM products for a specific date:
1. analysis_assim (current conditions, f000)
2. short_range (18-hour forecast, f001-f018)
3. medium_range_blend (10-day outlook, select hours)
4. analysis_assim_no_da (non-assimilated, f000)

This ingests ALL 2.7M reaches for each product.
"""

import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent.parent.parent / 'src'
sys.path.insert(0, str(src_path))

from dotenv import load_dotenv
from ingest.schedulers import IngestionScheduler

# Load environment
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def run_full_ingestion_for_date(target_date: datetime):
    """
    Run full ingestion workflow for all 4 NWM products.

    Args:
        target_date: Date to ingest (should be UTC, with hour=0,6,12,18 for medium_range)
    """
    logger.info("=" * 80)
    logger.info(f"FULL NWM INGESTION WORKFLOW - {target_date.strftime('%Y-%m-%d %HZ')}")
    logger.info("=" * 80)

    # Create scheduler
    scheduler = IngestionScheduler()

    # Track totals
    total_records = 0

    # Product 1: analysis_assim (current conditions)
    logger.info("\n" + "=" * 80)
    logger.info("PRODUCT 1/4: analysis_assim (current conditions, ALL reaches)")
    logger.info("=" * 80)
    try:
        records = scheduler.ingest_product(
            product="analysis_assim",
            reference_time=target_date,
            forecast_hour=0
        )
        total_records += records
        logger.info(f"✅ analysis_assim: {records:,} records")
    except Exception as e:
        logger.error(f"❌ analysis_assim failed: {e}")

    # Product 2: short_range (18-hour forecast)
    logger.info("\n" + "=" * 80)
    logger.info("PRODUCT 2/4: short_range (f001-f018, ALL reaches)")
    logger.info("=" * 80)
    try:
        records = scheduler.ingest_short_range(target_date)
        total_records += records
        logger.info(f"✅ short_range: {records:,} records")
    except Exception as e:
        logger.error(f"❌ short_range failed: {e}")

    # Product 3: medium_range_blend (10-day outlook)
    # Only runs at 00Z, 06Z, 12Z, 18Z
    if target_date.hour in [0, 6, 12, 18]:
        logger.info("\n" + "=" * 80)
        logger.info("PRODUCT 3/4: medium_range_blend (10-day outlook, ALL reaches)")
        logger.info("=" * 80)
        try:
            records = scheduler.ingest_medium_range_blend(target_date)
            total_records += records
            logger.info(f"✅ medium_range_blend: {records:,} records")
        except Exception as e:
            logger.error(f"❌ medium_range_blend failed: {e}")
    else:
        logger.info("\n" + "=" * 80)
        logger.info(f"PRODUCT 3/4: medium_range_blend SKIPPED (only runs at 00/06/12/18Z, got {target_date.hour}Z)")
        logger.info("=" * 80)

    # Product 4: analysis_assim_no_da (non-assimilated)
    # Only runs at 00Z (midnight UTC)
    if target_date.hour == 0:
        logger.info("\n" + "=" * 80)
        logger.info("PRODUCT 4/4: analysis_assim_no_da (non-assimilated, ALL reaches)")
        logger.info("=" * 80)
        try:
            records = scheduler.ingest_product(
                product="analysis_assim_no_da",
                reference_time=target_date,
                forecast_hour=0
            )
            total_records += records
            logger.info(f"✅ analysis_assim_no_da: {records:,} records")
        except Exception as e:
            logger.error(f"❌ analysis_assim_no_da failed: {e}")
    else:
        logger.info("\n" + "=" * 80)
        logger.info(f"PRODUCT 4/4: analysis_assim_no_da SKIPPED (only runs at 00Z, got {target_date.hour}Z)")
        logger.info("=" * 80)

    # Summary
    logger.info("\n" + "=" * 80)
    logger.info("FULL INGESTION COMPLETE")
    logger.info("=" * 80)
    logger.info(f"Total records ingested: {total_records:,}")
    logger.info(f"Date: {target_date.strftime('%Y-%m-%d %HZ')}")
    logger.info("\nExpected record counts (for 2.7M reaches, 6 variables each):")
    logger.info("  - analysis_assim: ~16.2M records (2.7M × 6)")
    logger.info("  - short_range: ~291.6M records (2.7M × 6 × 18 hours)")
    logger.info("  - medium_range_blend: ~162M records (2.7M × 6 × 10 days)")
    logger.info("  - analysis_assim_no_da: ~16.2M records (2.7M × 6)")
    logger.info("\n⚠️  NOTE: Full ingestion of all products may take several hours!")


if __name__ == "__main__":
    # January 3, 2026 - Use 00Z for complete workflow
    target_date = datetime(2026, 1, 5, 0, 0, 0, tzinfo=timezone.utc)

    logger.info("\nFull Ingestion Parameters:")
    logger.info(f"  Target Date: {target_date.strftime('%Y-%m-%d %HZ')}")
    logger.info(f"  Domain: conus (ALL ~2.7M stream reaches)")
    logger.info(f"  Products: 4 (analysis_assim, short_range, medium_range_blend, analysis_assim_no_da)")
    logger.info("\n⚠️  WARNING: This will ingest FULL dataset (2.7M reaches)")
    logger.info("  Estimated total records: ~486M (may take several hours)")
    logger.info("\nStarting in 3 seconds...")
    logger.info("Press Ctrl+C to cancel\n")

    import time
    time.sleep(3)

    run_full_ingestion_for_date(target_date)
