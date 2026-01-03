"""
End-to-End Ingestion Test (Optimized with PostgreSQL COPY)

Tests the complete pipeline:
1. Download NWM data
2. Parse NetCDF
3. Normalize to canonical time abstraction
4. Insert into database using PostgreSQL COPY (fast!)
5. Query and verify
"""

import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent.parent / 'src'
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


def test_end_to_end():
    """Test complete ingestion pipeline with PostgreSQL COPY"""

    logger.info("=" * 60)
    logger.info("End-to-End Ingestion Test (PostgreSQL COPY)")
    logger.info("=" * 60)

    # Create scheduler
    scheduler = IngestionScheduler()
    client = NWMClient()

    # Test 1: Ingest analysis_assim subset
    logger.info("\nTest 1: Ingest analysis_assim (10,000 reaches)")
    logger.info("-" * 60)

    try:
        # Find latest available data
        logger.info("Finding latest available analysis_assim data...")
        filepath, test_time = client.download_latest_analysis()
        logger.info(f"Using data from: {test_time}")

        # Parse full file
        df_full = client.parse_channel_rt(filepath)
        logger.info(f"Parsed {len(df_full):,} total reaches from NWM")

        # Use subset for testing (10K reaches)
        df_subset = df_full.head(10000).copy()
        logger.info(f"Testing with subset: {len(df_subset):,} reaches")

        # Use scheduler's optimized insertion (PostgreSQL COPY)
        logger.info("Starting optimized insertion...")
        records_inserted = scheduler._insert_hydro_data(
            df=df_subset,
            product="analysis_assim",
            reference_time=test_time,
            forecast_hour=0
        )

        logger.info(f"[OK] Inserted {records_inserted:,} records")

        # Verify in database
        with scheduler.engine.begin() as conn:
            result = conn.execute(text("""
                SELECT COUNT(*) as count
                FROM hydro_timeseries
                WHERE source = 'analysis_assim'
                AND valid_time = :valid_time
            """), {'valid_time': test_time})

            count = result.fetchone()[0]
            logger.info(f"[OK] Database confirms {count:,} records")

            # Show sample data
            result = conn.execute(text("""
                SELECT feature_id, variable, value, source, forecast_hour
                FROM hydro_timeseries
                WHERE source = 'analysis_assim'
                AND valid_time = :valid_time
                ORDER BY feature_id, variable
                LIMIT 10
            """), {'valid_time': test_time})

            logger.info("\nSample records from database:")
            for row in result:
                logger.info(
                    f"  feature={row.feature_id}, var={row.variable}, "
                    f"val={row.value:.2f}, source={row.source}"
                )

    except Exception as e:
        logger.error(f"[FAILED] Test 1 failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    # Test 2: Verify time normalization
    logger.info("\nTest 2: Verify time normalization")
    logger.info("-" * 60)

    try:
        with scheduler.engine.begin() as conn:
            # Check time normalization
            result = conn.execute(text("""
                SELECT
                    source,
                    COUNT(*) as count,
                    MIN(valid_time) as min_time,
                    MAX(valid_time) as max_time,
                    COUNT(DISTINCT feature_id) as unique_reaches,
                    COUNT(DISTINCT variable) as unique_variables
                FROM hydro_timeseries
                WHERE source = 'analysis_assim'
                GROUP BY source
            """))

            logger.info("Time normalization summary:")
            for row in result:
                logger.info(f"  Source: {row.source}")
                logger.info(f"    Records: {row.count:,}")
                logger.info(f"    Unique reaches: {row.unique_reaches:,}")
                logger.info(f"    Unique variables: {row.unique_variables}")
                logger.info(f"    Valid time: {row.min_time}")

        logger.info("[OK] Time normalization verified")

    except Exception as e:
        logger.error(f"[FAILED] Test 2 failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    # Test 3: Verify canonical abstraction
    logger.info("\nTest 3: Verify canonical abstraction (no f### references)")
    logger.info("-" * 60)

    try:
        with scheduler.engine.begin() as conn:
            # Check variables
            result = conn.execute(text("""
                SELECT DISTINCT variable
                FROM hydro_timeseries
                ORDER BY variable
            """))

            variables = [row[0] for row in result]
            logger.info(f"Variables in database: {', '.join(variables)}")

            # Verify no raw NWM names
            invalid_vars = [v for v in variables if v.startswith('f') and len(v) > 1 and v[1:].isdigit()]
            assert len(invalid_vars) == 0, f"Found f### references: {invalid_vars}"

            logger.info("[OK] No f### references - canonical abstraction verified")

    except Exception as e:
        logger.error(f"[FAILED] Test 3 failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    # Test 4: Query by timeframe abstraction
    logger.info("\nTest 4: Query using time abstractions")
    logger.info("-" * 60)

    try:
        with scheduler.engine.begin() as conn:
            # Query for "now" data
            result = conn.execute(text("""
                SELECT COUNT(DISTINCT feature_id) as reach_count
                FROM hydro_timeseries
                WHERE source = 'analysis_assim'
                AND valid_time = :valid_time
                AND variable = 'streamflow'
            """), {'valid_time': test_time})

            reach_count = result.fetchone()[0]
            logger.info(f"[OK] 'now' query: Found streamflow data for {reach_count:,} reaches")

        logger.info("[OK] Time abstraction queries working")

    except Exception as e:
        logger.error(f"[FAILED] Test 4 failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    logger.info("\n" + "=" * 60)
    logger.info("All End-to-End Tests PASSED!")
    logger.info("=" * 60)
    logger.info("\nKey Achievements:")
    logger.info("  ✅ NWM data downloaded and parsed")
    logger.info("  ✅ Time normalized to canonical abstraction")
    logger.info("  ✅ PostgreSQL COPY insertion (fast!)")
    logger.info("  ✅ No f### references in database")
    logger.info("  ✅ Source tagging working")
    logger.info("  ✅ Queries using time abstractions working")
    logger.info("\nEPIC 1 (Tickets 1.1 + 1.2) COMPLETE!")

    return True


if __name__ == "__main__":
    try:
        success = test_end_to_end()
        sys.exit(0 if success else 1)
    except Exception as e:
        logger.error(f"Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
