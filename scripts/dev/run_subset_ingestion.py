"""
Run Full NWM Ingestion Workflow - SUBSET VERSION (NHD-FILTERED)

Tests the complete workflow using only the NHD feature IDs loaded in the database.
This ensures we only ingest NWM data for reaches that have corresponding NHD spatial data.
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


def get_nhd_feature_ids():
    """
    Query database to get all NHD feature IDs (nhdplusid values).

    Returns:
        set: Set of NHDPlusID values from nhd_flowlines table

    Raises:
        ValueError: If no NHD feature IDs are found in the database
    """
    logger.info("Querying database for NHD feature IDs...")

    try:
        engine = create_engine(os.getenv('DATABASE_URL'))

        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT nhdplusid
                FROM nhd_flowlines
                ORDER BY nhdplusid
            """))

            feature_ids = {row[0] for row in result}

        if len(feature_ids) == 0:
            logger.error("❌ No NHD feature IDs found in nhd_flowlines table!")
            logger.error("   NWM ingestion requires NHD data to be loaded first.")
            logger.error("   Please run: python scripts/production/load_nhd_data.py <geojson_file>")
            raise ValueError("No NHD feature IDs found. Cannot proceed with NWM ingestion.")

        logger.info(f"✅ Found {len(feature_ids):,} NHD feature IDs in database")
        return feature_ids

    except Exception as e:
        logger.error(f"❌ Failed to query NHD feature IDs: {e}")
        raise


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


def run_subset_ingestion(target_date: datetime):
    """
    Run full ingestion workflow filtered by test feature IDs.

    Args:
        target_date: Date to ingest
    """
    logger.info("=" * 80)
    logger.info(f"NHD-FILTERED INGESTION - {target_date.strftime('%Y-%m-%d %HZ')}")
    logger.info("=" * 80)

    # Get all feature IDs from NHD database
    nhd_feature_ids = get_nhd_feature_ids()

    scheduler = IngestionScheduler()
    client = NWMClient()
    total_records = 0

    # Product 1: analysis_assim
    logger.info("\n" + "=" * 80)
    logger.info(f"PRODUCT 1/4: analysis_assim")
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

        # Filter to only NHD feature IDs
        df_subset = df_full[df_full['feature_id'].isin(nhd_feature_ids)].copy()
        logger.info(f"Filtered to {len(df_subset):,} records matching NHD data")

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

    # Product 2: short_range (ALL 18 hours)
    logger.info("\n" + "=" * 80)
    logger.info(f"PRODUCT 2/4: short_range (f001-f018 - all hours)")
    logger.info("=" * 80)

    for forecast_hour in range(1, 19):  # All 18 forecast hours
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

            # Filter to only NHD feature IDs
            df_subset = df_full[df_full['feature_id'].isin(nhd_feature_ids)].copy()
            logger.info(f"f{forecast_hour:03d}: Filtered to {len(df_subset):,} records matching NHD data")

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

    # Product 3: medium_range_blend (ALL hours - f003 to f240 every 3 hours)
    # Only runs at 00Z, 06Z, 12Z, 18Z
    if target_date.hour in [0, 6, 12, 18]:
        logger.info("\n" + "=" * 80)
        logger.info(f"PRODUCT 3/4: medium_range_blend (f003-f240 every 3 hours)")
        logger.info("=" * 80)

        # Forecast hours: 3, 6, 9, ..., 240 (every 3 hours for 10 days)
        for forecast_hour in range(3, 241, 3):
            started_at = datetime.now(timezone.utc)
            product_name = f"medium_range_blend_f{forecast_hour:03d}"

            try:
                filepath = client.download_product(
                    product="medium_range_blend",
                    reference_time=target_date,
                    forecast_hour=forecast_hour,
                    domain="conus"
                )
                df_full = client.parse_channel_rt(filepath)

                # Filter to only NHD feature IDs
                df_subset = df_full[df_full['feature_id'].isin(nhd_feature_ids)].copy()
                logger.info(f"f{forecast_hour:03d}: Filtered to {len(df_subset):,} records matching NHD data")

                records = scheduler._insert_hydro_data(
                    df=df_subset,
                    product="medium_range_blend",
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
                logger.info(f"✅ medium_range_blend f{forecast_hour:03d}: {records:,} records")
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

                logger.error(f"❌ medium_range_blend f{forecast_hour:03d} failed: {e}")

    # Product 4: analysis_assim_no_da
    # Only runs at 00Z (midnight UTC)
    if target_date.hour == 0:
        logger.info("\n" + "=" * 80)
        logger.info(f"PRODUCT 4/4: analysis_assim_no_da")
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

            # Filter to only NHD feature IDs
            df_subset = df_full[df_full['feature_id'].isin(nhd_feature_ids)].copy()
            logger.info(f"Filtered to {len(df_subset):,} records matching NHD data")

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
    logger.info("NHD-FILTERED INGESTION COMPLETE")
    logger.info("=" * 80)
    logger.info(f"Total records ingested: {total_records:,}")
    logger.info(f"NHD feature IDs used: {len(nhd_feature_ids):,}")
    logger.info(f"Date: {target_date.strftime('%Y-%m-%d %HZ')}")

    if total_records > 0:
        logger.info(f"\n✅ SUCCESS! Ingested NWM data for {len(nhd_feature_ids):,} NHD reaches")
        logger.info(f"   Average: {total_records / len(nhd_feature_ids):.1f} records per reach")
        logger.info("   NWM-NHD integration is working correctly!")
    else:
        logger.info("\n⚠️  No data found for NHD feature IDs")
        logger.info("   Check if NHD feature IDs exist in NWM files")


if __name__ == "__main__":
    # January 5, 2026 at 00Z
    target_date = datetime(2026, 1, 6, 11, 0, 0, tzinfo=timezone.utc)

    logger.info("\nNHD-Filtered Ingestion Parameters:")
    logger.info(f"  Target Date: {target_date.strftime('%Y-%m-%d %HZ')}")
    logger.info(f"  Filter: Using all NHD feature IDs from database (nhd_flowlines table)")
    logger.info(f"  Products:")
    logger.info(f"    - analysis_assim: f000 (current conditions)")
    logger.info(f"    - short_range: f001-f018 (18-hour forecast, ALL hours)")
    logger.info(f"    - medium_range_blend: f003-f240 every 3hrs (10-day outlook, 80 forecast hours)")
    logger.info(f"    - analysis_assim_no_da: f000 (baseline, only at 00Z)")
    logger.info(f"  Purpose: Full NWM ingestion for API 'now', 'today', and 'outlook' timeframes")
    logger.info("\nStarting in 2 seconds...")
    logger.info("Press Ctrl+C to cancel\n")

    import time
    time.sleep(2)

    run_subset_ingestion(target_date)
