"""
Run Full NWM Ingestion Workflow - SUBSET VERSION

Tests the complete workflow with a subset of reaches (100,000 by default).
Use this to verify everything works before running the full 2.7M reach ingestion.
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
from sqlalchemy import create_engine, text
from ingest.schedulers import IngestionScheduler
from ingest.nwm_client import NWMClient

# Load environment
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# SUBSET SIZE (change this to test with different amounts)
SUBSET_SIZE = 100_000  # Test with 100K reaches instead of 2.7M


def log_ingestion(product: str, cycle_time: datetime, status: str,
                  records: int = None, error: str = None,
                  started_at: datetime = None, completed_at: datetime = None):
    """Log ingestion run to ingestion_log table."""
    try:
        engine = create_engine(os.getenv('DATABASE_URL'))

        duration = None
        if started_at and completed_at:
            duration = (completed_at - started_at).total_seconds()

        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO ingestion_log (
                    product, cycle_time, domain, status, records_ingested,
                    error_message, started_at, completed_at, duration_seconds
                ) VALUES (
                    :product, :cycle_time, :domain, :status, :records,
                    :error, :started_at, :completed_at, :duration
                )
            """), {
                'product': product,
                'cycle_time': cycle_time,
                'domain': 'conus',
                'status': status,
                'records': records,
                'error': error,
                'started_at': started_at,
                'completed_at': completed_at,
                'duration': duration
            })
    except Exception as e:
        logger.warning(f"Failed to log ingestion for {product}: {e}")


def run_subset_ingestion(target_date: datetime, subset_size: int = SUBSET_SIZE):
    """
    Run full ingestion workflow with a subset of reaches.

    Args:
        target_date: Date to ingest
        subset_size: Number of reaches to include
    """
    logger.info("=" * 80)
    logger.info(f"SUBSET INGESTION TEST - {target_date.strftime('%Y-%m-%d %HZ')}")
    logger.info(f"Testing with {subset_size:,} reaches (out of 2.7M total)")
    logger.info("=" * 80)

    scheduler = IngestionScheduler()
    client = NWMClient()
    total_records = 0

    # Product 1: analysis_assim
    logger.info("\n" + "=" * 80)
    logger.info(f"PRODUCT 1/4: analysis_assim ({subset_size:,} reaches)")
    logger.info("=" * 80)

    started_at = datetime.now(timezone.utc)
    try:
        # Download and parse
        filepath = client.download_product(
            product="analysis_assim",
            reference_time=target_date,
            forecast_hour=0,
            domain="conus"
        )
        df_full = client.parse_channel_rt(filepath)
        df_subset = df_full.head(subset_size).copy()

        # Insert using scheduler's optimized method
        records = scheduler._insert_hydro_data(
            df=df_subset,
            product="analysis_assim",
            reference_time=target_date,
            forecast_hour=0
        )
        completed_at = datetime.now(timezone.utc)

        # Log success
        log_ingestion(
            product="analysis_assim",
            cycle_time=target_date,
            status="success",
            records=records,
            started_at=started_at,
            completed_at=completed_at
        )

        total_records += records
        logger.info(f"✅ analysis_assim: {records:,} records")
    except Exception as e:
        completed_at = datetime.now(timezone.utc)

        # Log failure
        log_ingestion(
            product="analysis_assim",
            cycle_time=target_date,
            status="failed",
            error=str(e),
            started_at=started_at,
            completed_at=completed_at
        )

        logger.error(f"❌ analysis_assim failed: {e}")

    # Product 2: short_range (just f001 and f018 for testing)
    logger.info("\n" + "=" * 80)
    logger.info(f"PRODUCT 2/4: short_range (f001, f018 only - {subset_size:,} reaches)")
    logger.info("=" * 80)

    for forecast_hour in [1, 18]:  # Just first and last hour for testing
        started_at = datetime.now(timezone.utc)
        product_name = f"short_range_f{forecast_hour:03d}"

        try:
            filepath = client.download_product(
                product="short_range",
                reference_time=target_date,
                forecast_hour=forecast_hour,
                domain="conus"
            )
            df_full = client.parse_channel_rt(filepath)
            df_subset = df_full.head(subset_size).copy()

            records = scheduler._insert_hydro_data(
                df=df_subset,
                product="short_range",
                reference_time=target_date,
                forecast_hour=forecast_hour
            )
            completed_at = datetime.now(timezone.utc)

            # Log success
            log_ingestion(
                product=product_name,
                cycle_time=target_date,
                status="success",
                records=records,
                started_at=started_at,
                completed_at=completed_at
            )

            total_records += records
            logger.info(f"✅ short_range f{forecast_hour:03d}: {records:,} records")
        except Exception as e:
            completed_at = datetime.now(timezone.utc)

            # Log failure
            log_ingestion(
                product=product_name,
                cycle_time=target_date,
                status="failed",
                error=str(e),
                started_at=started_at,
                completed_at=completed_at
            )

            logger.error(f"❌ short_range f{forecast_hour:03d} failed: {e}")

    # Product 3: medium_range_blend (just f024 for testing)
    if target_date.hour in [0, 6, 12, 18]:
        logger.info("\n" + "=" * 80)
        logger.info(f"PRODUCT 3/4: medium_range_blend (f024 only - {subset_size:,} reaches)")
        logger.info("=" * 80)

        started_at = datetime.now(timezone.utc)
        try:
            filepath = client.download_product(
                product="medium_range_blend",
                reference_time=target_date,
                forecast_hour=24,
                domain="conus"
            )
            df_full = client.parse_channel_rt(filepath)
            df_subset = df_full.head(subset_size).copy()

            records = scheduler._insert_hydro_data(
                df=df_subset,
                product="medium_range_blend",
                reference_time=target_date,
                forecast_hour=24
            )
            completed_at = datetime.now(timezone.utc)

            # Log success
            log_ingestion(
                product="medium_range_blend_f024",
                cycle_time=target_date,
                status="success",
                records=records,
                started_at=started_at,
                completed_at=completed_at
            )

            total_records += records
            logger.info(f"✅ medium_range_blend f024: {records:,} records")
        except Exception as e:
            completed_at = datetime.now(timezone.utc)

            # Log failure
            log_ingestion(
                product="medium_range_blend_f024",
                cycle_time=target_date,
                status="failed",
                error=str(e),
                started_at=started_at,
                completed_at=completed_at
            )

            logger.error(f"❌ medium_range_blend failed: {e}")

    # Product 4: analysis_assim_no_da
    # Only runs at 00Z (midnight UTC)
    if target_date.hour == 0:
        logger.info("\n" + "=" * 80)
        logger.info(f"PRODUCT 4/4: analysis_assim_no_da ({subset_size:,} reaches)")
        logger.info("=" * 80)

        started_at = datetime.now(timezone.utc)
        try:
            filepath = client.download_product(
                product="analysis_assim_no_da",
                reference_time=target_date,
                forecast_hour=0,
                domain="conus"
            )
            df_full = client.parse_channel_rt(filepath)
            df_subset = df_full.head(subset_size).copy()

            records = scheduler._insert_hydro_data(
                df=df_subset,
                product="analysis_assim_no_da",
                reference_time=target_date,
                forecast_hour=0
            )
            completed_at = datetime.now(timezone.utc)

            # Log success
            log_ingestion(
                product="analysis_assim_no_da",
                cycle_time=target_date,
                status="success",
                records=records,
                started_at=started_at,
                completed_at=completed_at
            )

            total_records += records
            logger.info(f"✅ analysis_assim_no_da: {records:,} records")
        except Exception as e:
            completed_at = datetime.now(timezone.utc)

            # Log failure
            log_ingestion(
                product="analysis_assim_no_da",
                cycle_time=target_date,
                status="failed",
                error=str(e),
                started_at=started_at,
                completed_at=completed_at
            )

            logger.error(f"❌ analysis_assim_no_da failed: {e}")
    else:
        logger.info("\n" + "=" * 80)
        logger.info(f"PRODUCT 4/4: analysis_assim_no_da SKIPPED (only runs at 00Z, got {target_date.hour}Z)")
        logger.info("=" * 80)

    # Summary
    logger.info("\n" + "=" * 80)
    logger.info("SUBSET INGESTION TEST COMPLETE")
    logger.info("=" * 80)
    logger.info(f"Total records ingested: {total_records:,}")
    logger.info(f"Subset size: {subset_size:,} reaches")
    logger.info(f"Date: {target_date.strftime('%Y-%m-%d %HZ')}")
    logger.info("\n✅ If this test succeeded, you're ready to run the full ingestion!")
    logger.info("   Run: python scripts/run_full_ingestion.py")


if __name__ == "__main__":
    # January 3, 2026 at 00Z
    target_date = datetime(2026, 1, 4, 20, 0, 0, tzinfo=timezone.utc)

    logger.info("\nSubset Ingestion Test Parameters:")
    logger.info(f"  Target Date: {target_date.strftime('%Y-%m-%d %HZ')}")
    logger.info(f"  Subset Size: {SUBSET_SIZE:,} reaches (out of 2.7M)")
    logger.info(f"  Products: 4 (analysis_assim, short_range sample, medium_range sample, analysis_assim_no_da)")
    logger.info(f"\n  Expected records: ~{SUBSET_SIZE * 6 * 4:,} (much faster than full run)")
    logger.info("\nStarting in 2 seconds...")
    logger.info("Press Ctrl+C to cancel\n")

    import time
    time.sleep(2)

    run_subset_ingestion(target_date, SUBSET_SIZE)
