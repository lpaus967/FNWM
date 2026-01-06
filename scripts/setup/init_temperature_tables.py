#!/usr/bin/env python3
"""
Initialize Temperature Tables

Creates the temperature_timeseries table in the database.

Usage:
    python scripts/setup/init_temperature_tables.py
"""

import os
import sys
from pathlib import Path
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Load environment variables
load_dotenv()


def init_temperature_tables():
    """Create temperature tables in database."""

    # Build database URL
    db_url = (
        f"postgresql://{os.getenv('DATABASE_USER')}:{os.getenv('DATABASE_PASSWORD')}"
        f"@{os.getenv('DATABASE_HOST')}:{os.getenv('DATABASE_PORT')}"
        f"/{os.getenv('DATABASE_NAME')}"
    )

    engine = create_engine(db_url)

    print("Initializing temperature tables...")
    print("=" * 60)

    # Read SQL script
    sql_path = project_root / "scripts" / "setup" / "create_temperature_tables.sql"

    if not sql_path.exists():
        print(f"ERROR: SQL script not found at {sql_path}")
        return False

    with open(sql_path, 'r') as f:
        sql_script = f.read()

    # Execute SQL
    with engine.begin() as conn:
        try:
            # Execute table creation
            print("\n[1/3] Creating temperature_timeseries table...")
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS temperature_timeseries (
                    nhdplusid BIGINT NOT NULL,
                    valid_time TIMESTAMP NOT NULL,
                    temperature_2m DOUBLE PRECISION,
                    apparent_temperature DOUBLE PRECISION,
                    precipitation DOUBLE PRECISION,
                    cloud_cover SMALLINT,
                    source VARCHAR(50) NOT NULL DEFAULT 'open-meteo',
                    forecast_hour SMALLINT,
                    ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT fk_temperature_reach
                        FOREIGN KEY (nhdplusid)
                        REFERENCES nhd_reach_centroids(nhdplusid)
                        ON DELETE CASCADE,
                    CONSTRAINT unique_temperature_reading
                        UNIQUE (nhdplusid, valid_time, source, forecast_hour)
                )
            """))
            print("  Table created successfully")

            # Create indexes
            print("\n[2/3] Creating indexes...")
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_temp_reach_time
                    ON temperature_timeseries(nhdplusid, valid_time)
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_temp_valid_time
                    ON temperature_timeseries(valid_time)
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_temp_source
                    ON temperature_timeseries(source)
            """))
            print("  Indexes created successfully")

            # Add comments
            print("\n[3/3] Adding table comments...")
            conn.execute(text("""
                COMMENT ON TABLE temperature_timeseries IS
                'Air temperature time series from Open-Meteo API for stream reach centroids'
            """))
            conn.execute(text("""
                COMMENT ON COLUMN temperature_timeseries.temperature_2m IS
                'Air temperature at 2 meters above ground (°C)'
            """))
            conn.execute(text("""
                COMMENT ON COLUMN temperature_timeseries.apparent_temperature IS
                'Apparent/"feels like" temperature (°C)'
            """))
            conn.execute(text("""
                COMMENT ON COLUMN temperature_timeseries.forecast_hour IS
                'Hours ahead of reference time (0 or NULL = current conditions)'
            """))
            print("  Comments added successfully")

            # Verify
            print("\n[Verification] Checking table...")
            result = conn.execute(text("""
                SELECT
                    schemaname,
                    tablename,
                    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
                FROM pg_tables
                WHERE tablename = 'temperature_timeseries'
            """))

            row = result.fetchone()
            if row:
                print(f"  Table: {row.tablename}")
                print(f"  Size: {row.size}")
            else:
                print("  WARNING: Table not found in verification query")

            print("\n" + "=" * 60)
            print("SUCCESS: Temperature tables initialized")
            print("=" * 60)

            return True

        except Exception as e:
            print(f"\nERROR: Failed to initialize temperature tables")
            print(f"  {type(e).__name__}: {e}")
            return False


if __name__ == "__main__":
    success = init_temperature_tables()
    sys.exit(0 if success else 1)
