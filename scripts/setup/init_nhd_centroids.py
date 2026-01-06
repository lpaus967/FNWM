#!/usr/bin/env python3
"""
Initialize NHD Reach Centroids Table

Extracts lat/lon centroids from nhd_flowlines PostGIS geometries
for use with temperature APIs (Open-Meteo).

Usage:
    python scripts/setup/init_nhd_centroids.py
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

def init_centroids():
    """Create and populate nhd_reach_centroids table."""

    # Build database URL
    db_url = (
        f"postgresql://{os.getenv('DATABASE_USER')}:{os.getenv('DATABASE_PASSWORD')}"
        f"@{os.getenv('DATABASE_HOST')}:{os.getenv('DATABASE_PORT')}/{os.getenv('DATABASE_NAME')}"
    )

    engine = create_engine(db_url)

    print("Initializing NHD reach centroids...")
    print("=" * 60)

    # Read SQL script
    sql_path = project_root / "scripts" / "setup" / "create_nhd_centroids.sql"

    if not sql_path.exists():
        print(f"ERROR: SQL script not found at {sql_path}")
        return False

    with open(sql_path, 'r') as f:
        sql_script = f.read()

    # Execute SQL in steps
    with engine.begin() as conn:
        try:
            # Step 1: Create table
            print("\n[1/4] Creating nhd_reach_centroids table...")
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS nhd_reach_centroids (
                    nhdplusid BIGINT PRIMARY KEY,
                    permanent_identifier VARCHAR(50) NOT NULL,
                    latitude DOUBLE PRECISION NOT NULL,
                    longitude DOUBLE PRECISION NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT fk_nhd_flowlines
                        FOREIGN KEY (nhdplusid)
                        REFERENCES nhd_flowlines(nhdplusid)
                        ON DELETE CASCADE
                )
            """))
            print("  Table created successfully")

            # Step 2: Create spatial index
            print("\n[2/4] Creating spatial index...")
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_nhd_centroids_latlon
                    ON nhd_reach_centroids(latitude, longitude)
            """))
            print("  Index created successfully")

            # Step 3: Populate with centroids
            print("\n[3/4] Extracting centroids from nhd_flowlines...")
            result = conn.execute(text("""
                INSERT INTO nhd_reach_centroids (nhdplusid, permanent_identifier, latitude, longitude)
                SELECT
                    nhdplusid,
                    permanent_identifier,
                    ST_Y(ST_Centroid(geom)) AS latitude,
                    ST_X(ST_Centroid(geom)) AS longitude
                FROM nhd_flowlines
                WHERE geom IS NOT NULL
                ON CONFLICT (nhdplusid) DO UPDATE
                    SET permanent_identifier = EXCLUDED.permanent_identifier,
                        latitude = EXCLUDED.latitude,
                        longitude = EXCLUDED.longitude
            """))
            rows_inserted = result.rowcount
            print(f"  Inserted/updated {rows_inserted} centroids")

            # Step 4: Verify results
            print("\n[4/4] Verifying coordinate ranges...")
            result = conn.execute(text("""
                SELECT
                    COUNT(*) as total_centroids,
                    ROUND(MIN(latitude)::numeric, 2) as min_lat,
                    ROUND(MAX(latitude)::numeric, 2) as max_lat,
                    ROUND(MIN(longitude)::numeric, 2) as min_lon,
                    ROUND(MAX(longitude)::numeric, 2) as max_lon
                FROM nhd_reach_centroids
            """))

            stats = result.fetchone()
            print(f"\n  Total centroids: {stats.total_centroids}")
            print(f"  Latitude range: {stats.min_lat} to {stats.max_lat}")
            print(f"  Longitude range: {stats.min_lon} to {stats.max_lon}")

            print("\n" + "=" * 60)
            print("SUCCESS: NHD centroids table initialized")
            print("=" * 60)

            return True

        except Exception as e:
            print(f"\nERROR: Failed to initialize centroids table")
            print(f"  {type(e).__name__}: {e}")
            return False

def verify_centroids():
    """Verify centroid data quality."""

    db_url = (
        f"postgresql://{os.getenv('DATABASE_USER')}:{os.getenv('DATABASE_PASSWORD')}"
        f"@{os.getenv('DATABASE_HOST')}:{os.getenv('DATABASE_PORT')}/{os.getenv('DATABASE_NAME')}"
    )

    engine = create_engine(db_url)

    print("\nVerifying centroid data...")
    print("-" * 60)

    with engine.begin() as conn:
        # Get sample centroids
        result = conn.execute(text("""
            SELECT
                nhdplusid,
                permanent_identifier,
                ROUND(latitude::numeric, 4) as lat,
                ROUND(longitude::numeric, 4) as lon
            FROM nhd_reach_centroids
            ORDER BY nhdplusid
            LIMIT 5
        """))

        print("\nSample centroids:")
        for row in result:
            print(f"  {row.nhdplusid} ({row.permanent_identifier}): ({row.lat}, {row.lon})")

        # Check for invalid coordinates
        result = conn.execute(text("""
            SELECT COUNT(*) as invalid_count
            FROM nhd_reach_centroids
            WHERE latitude < -90 OR latitude > 90
               OR longitude < -180 OR longitude > 180
        """))

        invalid_count = result.scalar()
        if invalid_count > 0:
            print(f"\nWARNING: Found {invalid_count} invalid coordinates")
        else:
            print("\nAll coordinates are valid")

    print("-" * 60)

if __name__ == "__main__":
    success = init_centroids()

    if success:
        verify_centroids()
        sys.exit(0)
    else:
        sys.exit(1)
