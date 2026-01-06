"""
Database Reset and Repopulation Script

This script provides a complete workflow for resetting and repopulating the database
when changing geographic locations or starting fresh with new hydrology data.

Workflow:
1. Clear all existing tables (with confirmation prompt)
2. Load new NHD hydrology data from GeoJSON
3. Extract reach centroids for temperature API
4. Ingest NWM hydrology data (filtered by loaded NHD reaches)
5. Ingest temperature data from Open-Meteo API

Usage:
    python scripts/production/reset_and_repopulate_db.py \
        --nhd-geojson "path/to/nhdHydrologyExample.geojson" \
        --temp-reaches 100 \
        --temp-forecast-days 7 \
        --skip-confirmation

Options:
    --nhd-geojson: Path to NHDPlus GeoJSON file (REQUIRED)
    --temp-reaches: Number of reaches to fetch temperature data for (default: all)
    --temp-forecast-days: Days of temperature forecast to fetch (default: 7, max: 16)
    --temp-batch-size: Batch size for temperature API calls (default: 50)
    --temp-delay: Delay between temperature API calls in seconds (default: 1.0)
    --skip-confirmation: Skip the confirmation prompt (use with caution!)
    --skip-nwm: Skip NWM hydrology ingestion
    --skip-temperature: Skip temperature ingestion
"""

import os
import sys
import argparse
import subprocess
from pathlib import Path
from typing import Optional

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from dotenv import load_dotenv


def get_db_connection():
    """Get database connection from environment variables."""
    load_dotenv()

    db_url = os.getenv("DATABASE_URL")
    if db_url:
        return psycopg2.connect(db_url)

    # Fallback to individual parameters
    return psycopg2.connect(
        host=os.getenv("DATABASE_HOST", "localhost"),
        port=os.getenv("DATABASE_PORT", "5432"),
        dbname=os.getenv("DATABASE_NAME", "fnwm"),
        user=os.getenv("DATABASE_USER", "fnwm_user"),
        password=os.getenv("DATABASE_PASSWORD")
    )


def clear_all_tables(conn, skip_confirmation: bool = False):
    """
    Clear all tables in the database.

    Drops data from all tables in the correct order to handle foreign key constraints.
    This is faster than DELETE and resets auto-increment sequences.

    Tables cleared (in order):
    - temperature_timeseries
    - nhd_reach_centroids
    - computed_scores
    - user_observations
    - hydro_timeseries (hypertable)
    - ingestion_log
    - nhd_network_topology
    - nhd_flow_statistics
    - nhd_flowlines
    - reach_metadata
    """
    cursor = conn.cursor()

    # Get table counts for user information
    tables_info = []
    table_names = [
        'temperature_timeseries',
        'nhd_reach_centroids',
        'computed_scores',
        'user_observations',
        'hydro_timeseries',
        'ingestion_log',
        'nhd_network_topology',
        'nhd_flow_statistics',
        'nhd_flowlines',
        'reach_metadata'
    ]

    print("\n" + "="*80)
    print("DATABASE RESET - CURRENT TABLE STATUS")
    print("="*80)

    for table in table_names:
        try:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            tables_info.append((table, count))
            print(f"  {table:30s} : {count:>12,} rows")
        except psycopg2.Error:
            tables_info.append((table, 0))
            print(f"  {table:30s} : (table doesn't exist)")

    print("="*80)

    total_rows = sum(count for _, count in tables_info)

    if total_rows == 0:
        print("\nAll tables are already empty. Nothing to clear.")
        return

    # Confirmation prompt
    if not skip_confirmation:
        print(f"\nWARNING: This will DELETE {total_rows:,} rows from {len(table_names)} tables!")
        print("WARNING: This operation CANNOT be undone!")
        response = input("\nType 'DELETE ALL DATA' to confirm: ")

        if response != "DELETE ALL DATA":
            print("\nReset cancelled. No data was deleted.")
            sys.exit(0)

    print("\nClearing all tables...")

    # Truncate tables in correct order (children before parents due to FKs)
    truncate_order = [
        'temperature_timeseries',
        'nhd_reach_centroids',
        'computed_scores',
        'user_observations',
        'hydro_timeseries',
        'ingestion_log',
        'nhd_network_topology',
        'nhd_flow_statistics',
        'nhd_flowlines',
        'reach_metadata'
    ]

    for table in truncate_order:
        try:
            # Use TRUNCATE CASCADE for speed and to reset sequences
            cursor.execute(f"TRUNCATE TABLE {table} CASCADE")
            print(f"  * Cleared {table}")
        except psycopg2.Error as e:
            # Table might not exist, which is fine
            print(f"  - Skipped {table} ({e.pgerror.split(':')[0] if e.pgerror else 'does not exist'})")

    conn.commit()
    print("\nAll tables cleared successfully!\n")


def verify_nhd_data_loaded():
    """Verify that NHD data was successfully loaded into the database."""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT COUNT(*) FROM nhd_flowlines")
        flowline_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM nhd_network_topology")
        topology_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM nhd_flow_statistics")
        stats_count = cursor.fetchone()[0]

        conn.close()

        if flowline_count == 0:
            print("ERROR: No data found in nhd_flowlines table!")
            print("   NWM ingestion requires NHD feature IDs to be present.")
            return False

        print(f"Verified NHD data loaded:")
        print(f"  - {flowline_count:,} flowlines")
        print(f"  - {topology_count:,} topology records")
        print(f"  - {stats_count:,} flow statistics records")

        return True

    except psycopg2.Error as e:
        print(f"ERROR: Error verifying NHD data: {e}")
        conn.close()
        return False


def verify_centroids_created():
    """Verify that reach centroids were successfully created."""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT COUNT(*) FROM nhd_reach_centroids")
        centroid_count = cursor.fetchone()[0]
        conn.close()

        if centroid_count == 0:
            print("WARNING: No centroids found in nhd_reach_centroids table!")
            print("   Temperature ingestion may not work without centroids.")
            return False

        print(f"Verified {centroid_count:,} reach centroids created")
        return True

    except psycopg2.Error as e:
        print(f"WARNING: Could not verify centroids: {e}")
        conn.close()
        return False


def load_nhd_data(geojson_path: str):
    """Load NHD data from GeoJSON file."""
    print("="*80)
    print("STEP 1: LOADING NHD HYDROLOGY DATA")
    print("="*80)
    print(f"Source: {geojson_path}\n")

    if not os.path.exists(geojson_path):
        print(f"ERROR: GeoJSON file not found: {geojson_path}")
        sys.exit(1)

    script_path = Path(__file__).parent / "load_nhd_data.py"
    result = subprocess.run(
        [sys.executable, str(script_path), geojson_path],
        capture_output=False
    )

    if result.returncode != 0:
        print("\nERROR: NHD data loading failed!")
        sys.exit(1)

    print("\nNHD data loaded successfully!\n")


def extract_centroids():
    """Extract reach centroids from NHD flowlines."""
    print("="*80)
    print("STEP 2: EXTRACTING REACH CENTROIDS")
    print("="*80)
    print("Extracting lat/lon centroids from nhd_flowlines for temperature API...\n")

    script_path = Path(__file__).parent.parent / "setup" / "init_nhd_centroids.py"
    result = subprocess.run(
        [sys.executable, str(script_path)],
        capture_output=False
    )

    if result.returncode != 0:
        print("\nERROR: Centroid extraction failed!")
        sys.exit(1)

    print("\nCentroids extracted successfully!\n")


def ingest_nwm_data():
    """
    Run NWM hydrology data ingestion (subset filtered by NHD reaches).

    CRITICAL DEPENDENCY: This function REQUIRES that NHD data is already loaded
    in the nhd_flowlines table. The ingestion script queries nhd_flowlines to get
    the list of feature IDs, then filters NWM data to only include those IDs.

    If nhd_flowlines is empty, no NWM data will be ingested!
    """
    print("="*80)
    print("STEP 3: INGESTING NWM HYDROLOGY DATA")
    print("="*80)
    print("Running subset ingestion (filtered by loaded NHD reaches)...")
    print("NOTE: NWM data will be filtered to match feature IDs in nhd_flowlines table.\n")

    script_path = Path(__file__).parent.parent / "dev" / "run_subset_ingestion.py"

    # Check if file was moved to tests directory (based on git status)
    if not os.path.exists(script_path):
        script_path = Path(__file__).parent.parent / "tests" / "run_subset_ingestion.py"

    if not os.path.exists(script_path):
        print(f"ERROR: run_subset_ingestion.py not found!")
        print(f"   Looked in: scripts/dev/ and scripts/tests/")
        sys.exit(1)

    result = subprocess.run(
        [sys.executable, str(script_path)],
        capture_output=False
    )

    if result.returncode != 0:
        print("\nWARNING: NWM ingestion completed with errors (check logs)")
    else:
        print("\nNWM data ingested successfully!\n")


def ingest_temperature(
    reaches: Optional[int] = None,
    forecast_days: int = 7,
    batch_size: int = 50,
    delay: float = 1.0
):
    """Run temperature data ingestion from Open-Meteo API."""
    print("="*80)
    print("STEP 4: INGESTING TEMPERATURE DATA")
    print("="*80)

    cmd = [
        sys.executable,
        str(Path(__file__).parent / "ingest_temperature.py"),
        f"--forecast-days={forecast_days}",
        f"--batch-size={batch_size}",
        f"--delay={delay}"
    ]

    if reaches:
        cmd.append(f"--reaches={reaches}")
        print(f"Fetching temperature data for {reaches} reaches...")
    else:
        print(f"Fetching temperature data for ALL reaches...")

    print(f"Forecast days: {forecast_days}, Batch size: {batch_size}, Delay: {delay}s\n")

    result = subprocess.run(cmd, capture_output=False)

    if result.returncode != 0:
        print("\nWARNING: Temperature ingestion completed with errors (check logs)")
    else:
        print("\nTemperature data ingested successfully!\n")


def main():
    parser = argparse.ArgumentParser(
        description="Reset and repopulate database with new hydrology data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full reset and repopulation
  python reset_and_repopulate_db.py --nhd-geojson "D:\\Data\\nhdHydrology.geojson"

  # Skip confirmation prompt (use in automated scripts)
  python reset_and_repopulate_db.py --nhd-geojson "data.geojson" --skip-confirmation

  # Reset without temperature data
  python reset_and_repopulate_db.py --nhd-geojson "data.geojson" --skip-temperature

  # Temperature for specific number of reaches
  python reset_and_repopulate_db.py --nhd-geojson "data.geojson" --temp-reaches 50
        """
    )

    parser.add_argument(
        "--nhd-geojson",
        required=True,
        help="Path to NHDPlus GeoJSON file"
    )
    parser.add_argument(
        "--temp-reaches",
        type=int,
        default=None,
        help="Number of reaches to fetch temperature data for (default: all)"
    )
    parser.add_argument(
        "--temp-forecast-days",
        type=int,
        default=7,
        help="Days of temperature forecast to fetch (default: 7, max: 16)"
    )
    parser.add_argument(
        "--temp-batch-size",
        type=int,
        default=50,
        help="Batch size for temperature API calls (default: 50)"
    )
    parser.add_argument(
        "--temp-delay",
        type=float,
        default=1.0,
        help="Delay between temperature API calls in seconds (default: 1.0)"
    )
    parser.add_argument(
        "--skip-confirmation",
        action="store_true",
        help="Skip the confirmation prompt (use with caution!)"
    )
    parser.add_argument(
        "--skip-nwm",
        action="store_true",
        help="Skip NWM hydrology ingestion"
    )
    parser.add_argument(
        "--skip-temperature",
        action="store_true",
        help="Skip temperature ingestion"
    )

    args = parser.parse_args()

    print("\n" + "="*80)
    print("DATABASE RESET AND REPOPULATION SCRIPT")
    print("="*80 + "\n")

    try:
        # Step 0: Clear existing data
        conn = get_db_connection()
        clear_all_tables(conn, skip_confirmation=args.skip_confirmation)
        conn.close()

        # Step 1: Load NHD data
        load_nhd_data(args.nhd_geojson)

        # Verification: Ensure NHD data was loaded successfully
        print()
        if not verify_nhd_data_loaded():
            print("\nERROR: NHD data verification failed!")
            print("   Cannot proceed with NWM ingestion without NHD feature IDs.")
            sys.exit(1)
        print()

        # Step 2: Extract centroids
        extract_centroids()

        # Verification: Ensure centroids were created
        print()
        verify_centroids_created()
        print()

        # Step 3: Ingest NWM data (optional)
        if not args.skip_nwm:
            ingest_nwm_data()
        else:
            print("SKIPPED: NWM ingestion (--skip-nwm flag)\n")

        # Step 4: Ingest temperature data (optional)
        if not args.skip_temperature:
            ingest_temperature(
                reaches=args.temp_reaches,
                forecast_days=args.temp_forecast_days,
                batch_size=args.temp_batch_size,
                delay=args.temp_delay
            )
        else:
            print("SKIPPED: Temperature ingestion (--skip-temperature flag)\n")

        # Success summary
        print("\n" + "="*80)
        print("SUCCESS: DATABASE RESET AND REPOPULATION COMPLETE!")
        print("="*80)
        print("\nYour database has been successfully reset and repopulated with:")
        print("  * NHD hydrology spatial data (flowlines, topology, flow statistics)")
        print("  * Reach centroids for temperature API")
        if not args.skip_nwm:
            print("  * NWM hydrology time-series data (filtered by loaded NHD reaches)")
        if not args.skip_temperature:
            print("  * Temperature forecast data from Open-Meteo API")
        print("\nYou can now run your API and perform species scoring analysis.")
        print("="*80 + "\n")

    except KeyboardInterrupt:
        print("\n\nWARNING: Operation cancelled by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
