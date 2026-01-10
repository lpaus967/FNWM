"""
Initialize map_current_conditions materialized view.

This creates a map-ready view combining NHD flowline geometry with
the latest hydrology metrics for efficient GeoJSON export and map rendering.

Based on EPIC 8 from IMPLEMENTATION_GUIDE.md

Usage:
    python scripts/setup/init_map_view.py
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
import os
from sqlalchemy import create_engine, text
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def init_map_view():
    """Create the map_current_conditions materialized view."""

    # Load environment
    load_dotenv()
    database_url = os.getenv('DATABASE_URL')

    if not database_url:
        logger.error("DATABASE_URL not set in environment")
        sys.exit(1)

    # Read SQL file
    sql_file = project_root / 'scripts' / 'setup' / 'create_map_current_conditions_view.sql'

    if not sql_file.exists():
        logger.error(f"SQL file not found: {sql_file}")
        sys.exit(1)

    logger.info(f"Reading SQL from {sql_file}")
    with open(sql_file, 'r') as f:
        sql_content = f.read()

    # Connect to database
    logger.info("Connecting to database...")
    engine = create_engine(database_url)

    try:
        with engine.begin() as conn:
            logger.info("Creating materialized view...")

            # Execute the entire SQL as one block (handles multi-statement DDL)
            conn.execute(text(sql_content))

            logger.info("Materialized view created successfully!")

            # Check row count
            result = conn.execute(text("""
                SELECT COUNT(*) as count
                FROM derived.map_current_conditions
            """))

            row_count = result.scalar()
            logger.info(f"✅ View populated with {row_count:,} reaches")

            # Show sample data
            result = conn.execute(text("""
                SELECT
                    feature_id,
                    gnis_name,
                    streamflow,
                    velocity,
                    bdi,
                    bdi_category,
                    flow_percentile,
                    flow_percentile_category,
                    air_temp_c,
                    air_temp_f,
                    water_temp_estimate_c,
                    water_temp_estimate_f,
                    confidence
                FROM derived.map_current_conditions
                LIMIT 5
            """))

            logger.info("\nSample data:")
            logger.info("-" * 80)
            for row in result:
                bdi_str = f"{row.bdi:.2f}" if row.bdi is not None else "N/A"
                percentile_str = f"{row.flow_percentile:.1f}" if row.flow_percentile is not None else "N/A"
                air_temp_str = f"{row.air_temp_f:.1f}°F" if row.air_temp_f is not None else "N/A"
                water_temp_str = f"{row.water_temp_estimate_f:.1f}°F" if row.water_temp_estimate_f is not None else "N/A"

                logger.info(
                    f"Feature {row.feature_id} ({row.gnis_name or 'Unnamed'}): "
                    f"Flow={row.streamflow:.3f} m³/s, "
                    f"Velocity={row.velocity:.3f} m/s, "
                    f"BDI={bdi_str} ({row.bdi_category or 'N/A'}), "
                    f"Percentile={percentile_str} ({row.flow_percentile_category or 'N/A'}), "
                    f"AirTemp={air_temp_str}, WaterTemp={water_temp_str}, "
                    f"Confidence={row.confidence}"
                )

    except Exception as e:
        logger.error(f"Error creating materialized view: {e}")
        raise

    logger.info("\n" + "=" * 80)
    logger.info("MATERIALIZED VIEW SETUP COMPLETE")
    logger.info("=" * 80)
    logger.info("\nNext steps:")
    logger.info("1. Export as GeoJSON: python scripts/production/export_map_geojson.py")
    logger.info("2. Refresh after data updates: SELECT refresh_map_current_conditions();")

if __name__ == "__main__":
    init_map_view()
