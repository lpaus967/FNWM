#!/usr/bin/env python3
"""
Fix Flow Units: Convert CFS to m³/s in nhd_flow_statistics

This script safely converts all flow values in the nhd_flow_statistics table
from CFS (cubic feet per second) to m³/s (cubic meters per second).

ISSUE: NHDPlus data is stored in CFS but the system expects m³/s, causing
       flow percentile calculations to show ~4% instead of ~50% for normal flows.

SOLUTION: Apply conversion factor of 35.3147 CFS per m³/s to all flow columns.

Usage:
    python scripts/setup/run_fix_flow_units.py

Author: Claude Code
Date: 2026-01-06
"""

import os
import sys
from pathlib import Path
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_database_engine():
    """Get database engine from environment variables."""
    load_dotenv()

    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        raise ValueError("DATABASE_URL not found in environment variables")

    return create_engine(database_url)


def show_sample_before(engine):
    """Show sample data before conversion."""
    logger.info("=" * 80)
    logger.info("BEFORE CONVERSION - Sample Data")
    logger.info("=" * 80)

    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT
                nhdplusid,
                qama as jan_flow,
                qema as may_flow,
                qfma as june_flow
            FROM nhd.flow_statistics
            WHERE qama IS NOT NULL
            LIMIT 3
        """))

        rows = result.fetchall()
        if rows:
            logger.info("Sample flows (currently in CFS):")
            for row in rows:
                logger.info(f"  NHDPlusID: {row[0]}")
                logger.info(f"    Jan: {row[1]:.2f} CFS")
                logger.info(f"    May: {row[2]:.2f} CFS")
                logger.info(f"    Jun: {row[3]:.2f} CFS")
        else:
            logger.warning("No flow statistics data found in database")


def apply_conversion(engine):
    """Apply CFS to m³/s conversion."""
    logger.info("=" * 80)
    logger.info("APPLYING CONVERSION: CFS → m³/s")
    logger.info("=" * 80)
    logger.info("Conversion factor: 1 m³/s = 35.3147 CFS")

    cfs_to_m3s = 35.3147

    with engine.begin() as conn:
        # Convert all flow columns
        # NOTE: Only Jan-Jun columns exist in schema (qama-qfma)
        result = conn.execute(text("""
            UPDATE nhd.flow_statistics
            SET
                -- Monthly mean flows (Jan-Jun only, as per schema)
                qama = CASE WHEN qama IS NOT NULL THEN qama / :factor ELSE NULL END,
                qbma = CASE WHEN qbma IS NOT NULL THEN qbma / :factor ELSE NULL END,
                qcma = CASE WHEN qcma IS NOT NULL THEN qcma / :factor ELSE NULL END,
                qdma = CASE WHEN qdma IS NOT NULL THEN qdma / :factor ELSE NULL END,
                qema = CASE WHEN qema IS NOT NULL THEN qema / :factor ELSE NULL END,
                qfma = CASE WHEN qfma IS NOT NULL THEN qfma / :factor ELSE NULL END,

                -- Incremental flows (Jan-Jun only)
                qincrama = CASE WHEN qincrama IS NOT NULL THEN qincrama / :factor ELSE NULL END,
                qincrbma = CASE WHEN qincrbma IS NOT NULL THEN qincrbma / :factor ELSE NULL END,
                qincrcma = CASE WHEN qincrcma IS NOT NULL THEN qincrcma / :factor ELSE NULL END,
                qincrdma = CASE WHEN qincrdma IS NOT NULL THEN qincrdma / :factor ELSE NULL END,
                qincrema = CASE WHEN qincrema IS NOT NULL THEN qincrema / :factor ELSE NULL END,
                qincrfma = CASE WHEN qincrfma IS NOT NULL THEN qincrfma / :factor ELSE NULL END,

                -- Gage flow
                gageqma = CASE WHEN gageqma IS NOT NULL THEN gageqma / :factor ELSE NULL END
        """), {"factor": cfs_to_m3s})

        rows_updated = result.rowcount
        logger.info(f"✓ Converted {rows_updated} rows from CFS to m³/s")


def show_sample_after(engine):
    """Show sample data after conversion."""
    logger.info("=" * 80)
    logger.info("AFTER CONVERSION - Sample Data")
    logger.info("=" * 80)

    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT
                nhdplusid,
                qama as jan_flow,
                qema as may_flow,
                qfma as june_flow
            FROM nhd.flow_statistics
            WHERE qama IS NOT NULL
            LIMIT 3
        """))

        rows = result.fetchall()
        if rows:
            logger.info("Sample flows (now in m³/s):")
            for row in rows:
                logger.info(f"  NHDPlusID: {row[0]}")
                logger.info(f"    Jan: {row[1]:.4f} m³/s")
                logger.info(f"    May: {row[2]:.4f} m³/s")
                logger.info(f"    Jun: {row[3]:.4f} m³/s")


def refresh_materialized_view(engine):
    """Refresh the materialized view to use corrected data."""
    logger.info("=" * 80)
    logger.info("REFRESHING MATERIALIZED VIEW")
    logger.info("=" * 80)

    with engine.begin() as conn:
        logger.info("Refreshing map_current_conditions...")
        conn.execute(text("REFRESH MATERIALIZED VIEW map_current_conditions"))
        logger.info("✓ Materialized view refreshed")


def verify_conversion(engine):
    """Verify the conversion worked correctly."""
    logger.info("=" * 80)
    logger.info("VERIFICATION")
    logger.info("=" * 80)

    with engine.connect() as conn:
        # Check if flow percentiles now make sense
        result = conn.execute(text("""
            SELECT
                COUNT(*) as total_reaches,
                AVG(flow_percentile) as avg_percentile,
                MIN(flow_percentile) as min_percentile,
                MAX(flow_percentile) as max_percentile
            FROM derived.map_current_conditions
            WHERE flow_percentile IS NOT NULL
        """))

        row = result.fetchone()
        if row and row[0] > 0:
            logger.info(f"Flow percentile statistics (should be reasonable now):")
            logger.info(f"  Total reaches with data: {row[0]}")
            logger.info(f"  Average percentile: {row[1]:.1f}%")
            logger.info(f"  Range: {row[2]:.1f}% to {row[3]:.1f}%")

            # Check if average is reasonable (should be closer to 50%)
            if 30 <= row[1] <= 70:
                logger.info("✓ Average percentile looks reasonable!")
            else:
                logger.warning("⚠ Average percentile still seems off. Manual review recommended.")
        else:
            logger.warning("No flow percentile data available for verification")


def main():
    """Main execution function."""
    try:
        logger.info("=" * 80)
        logger.info("FIX FLOW UNITS: Convert CFS to m³/s")
        logger.info("=" * 80)
        logger.info("")

        # Get database connection
        engine = get_database_engine()
        logger.info("✓ Connected to database")

        # Show before state
        show_sample_before(engine)

        # Confirm with user
        logger.info("")
        logger.info("=" * 80)
        response = input("Ready to convert flow units from CFS to m³/s? (yes/no): ")
        if response.lower() != 'yes':
            logger.info("Conversion cancelled by user")
            return

        # Apply conversion
        apply_conversion(engine)

        # Show after state
        show_sample_after(engine)

        # Refresh materialized view
        refresh_materialized_view(engine)

        # Verify results
        verify_conversion(engine)

        # Success
        logger.info("")
        logger.info("=" * 80)
        logger.info("✓ SUCCESS: Flow units converted and view refreshed")
        logger.info("=" * 80)
        logger.info("Next steps:")
        logger.info("  1. Restart your API server")
        logger.info("  2. Test flow percentile calculations")
        logger.info("  3. Verify map exports show correct classifications")

    except Exception as e:
        logger.error(f"❌ Error during conversion: {e}")
        logger.error("Database may be in inconsistent state. Review manually.")
        sys.exit(1)


if __name__ == "__main__":
    main()
