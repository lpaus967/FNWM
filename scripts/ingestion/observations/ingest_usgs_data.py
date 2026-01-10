"""
USGS Data Ingestion Script

Fetches current conditions from all USGS sites in the USGS_Flowsites table
and stores them in the usgs_instantaneous_values table.

This script can be run on a schedule (e.g., hourly) to keep data up-to-date.
"""

import os
import sys
from pathlib import Path
from datetime import datetime
from typing import List

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from src.usgs.client import USGSClient, ParameterCodes
from src.usgs.schemas import USGSFetchResult, USGSInstantaneousValue

# Configure stdout for UTF-8 on Windows
if sys.platform == 'win32':
    import codecs
    if sys.stdout.encoding != 'utf-8':
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    if sys.stderr.encoding != 'utf-8':
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')


def get_enabled_sites(conn) -> List[str]:
    """Fetch all enabled USGS site IDs from database."""
    result = conn.execute(text('''
        SELECT "siteId"
        FROM "USGS_Flowsites"
        WHERE "isEnabled" = TRUE
        ORDER BY "siteId";
    '''))

    return [row[0] for row in result]


def store_usgs_data(conn, readings: List[USGSInstantaneousValue]) -> int:
    """
    Store USGS readings in the database.

    Uses ON CONFLICT to handle duplicates (upsert).

    Args:
        conn: Database connection
        readings: List of USGS readings to store

    Returns:
        Number of records inserted/updated
    """
    if not readings:
        return 0

    insert_sql = text("""
        INSERT INTO observations.usgs_instantaneous_values (
            site_id, parameter_cd, datetime, parameter_name,
            value, unit, qualifiers, is_provisional, fetched_at
        ) VALUES (
            :site_id, :parameter_cd, :datetime, :parameter_name,
            :value, :unit, :qualifiers, :is_provisional, :fetched_at
        )
        ON CONFLICT (site_id, parameter_cd, datetime)
        DO UPDATE SET
            value = EXCLUDED.value,
            unit = EXCLUDED.unit,
            qualifiers = EXCLUDED.qualifiers,
            is_provisional = EXCLUDED.is_provisional,
            fetched_at = EXCLUDED.fetched_at;
    """)

    count = 0
    fetched_at = datetime.utcnow()

    for reading in readings:
        conn.execute(insert_sql, {
            'site_id': reading.site_id,
            'parameter_cd': reading.parameter_cd,
            'datetime': reading.datetime,
            'parameter_name': reading.parameter_name,
            'value': reading.value,
            'unit': reading.unit,
            'qualifiers': reading.qualifiers,
            'is_provisional': reading.is_provisional,
            'fetched_at': fetched_at
        })
        count += 1

    return count


def refresh_materialized_view(conn):
    """Refresh the usgs_latest_readings materialized view."""
    try:
        conn.execute(text("REFRESH MATERIALIZED VIEW CONCURRENTLY usgs_latest_readings;"))
        return True
    except Exception as e:
        # Fallback to non-concurrent refresh if concurrent fails
        # (concurrent requires unique index which we have)
        print(f"Warning: Concurrent refresh failed, trying non-concurrent: {e}")
        try:
            conn.execute(text("REFRESH MATERIALIZED VIEW usgs_latest_readings;"))
            return True
        except Exception as e2:
            print(f"Error refreshing materialized view: {e2}")
            return False


def ingest_usgs_data(parameter_codes: List[str] = None):
    """
    Main ingestion function.

    Args:
        parameter_codes: List of USGS parameter codes to fetch.
                        Defaults to discharge and gage height.
    """
    # Load environment variables
    load_dotenv()

    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        print("ERROR: DATABASE_URL not found in .env file")
        return False

    # Default parameter codes
    if parameter_codes is None:
        parameter_codes = [
            ParameterCodes.DISCHARGE,
            ParameterCodes.GAGE_HEIGHT,
            ParameterCodes.WATER_TEMP
        ]

    print("=" * 80)
    print("USGS Data Ingestion")
    print("=" * 80)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    try:
        engine = create_engine(database_url)

        with engine.begin() as conn:
            # Step 1: Get enabled sites
            print("Fetching enabled USGS sites from database...")
            site_ids = get_enabled_sites(conn)
            print(f"Found {len(site_ids)} enabled sites")
            print()

            if not site_ids:
                print("No enabled sites found. Exiting.")
                return True

            # Step 2: Fetch data from USGS API
            print("-" * 80)
            print("Fetching current conditions from USGS API...")
            print(f"Parameters: {', '.join(parameter_codes)}")
            print("-" * 80)

            client = USGSClient()
            results = client.fetch_current_conditions(
                site_ids=site_ids,
                parameter_codes=parameter_codes
            )

            # Step 3: Process results
            print()
            print("Processing results...")
            print()

            total_readings = 0
            success_count = 0
            failure_count = 0
            all_readings = []

            for result in results:
                if result.success:
                    success_count += 1
                    if result.data:
                        reading_count = len(result.data)
                        total_readings += reading_count
                        all_readings.extend(result.data)
                        print(f"  Site {result.site_id}: {reading_count} readings")
                    else:
                        print(f"  Site {result.site_id}: No data available")
                else:
                    failure_count += 1
                    print(f"  Site {result.site_id}: FAILED - {result.error}")

            print()

            # Step 4: Store in database
            if all_readings:
                print("-" * 80)
                print("Storing data in database...")
                print("-" * 80)

                stored_count = store_usgs_data(conn, all_readings)
                print(f"Stored {stored_count} readings in usgs_instantaneous_values table")
                print()

                # Step 5: Refresh materialized view
                print("Refreshing materialized view...")
                if refresh_materialized_view(conn):
                    print("Materialized view refreshed successfully")
                else:
                    print("Warning: Could not refresh materialized view")
                print()

            # Summary
            print("=" * 80)
            print("SUMMARY")
            print("=" * 80)
            print(f"Sites queried: {len(site_ids)}")
            print(f"Successful: {success_count}")
            print(f"Failed: {failure_count}")
            print(f"Total readings fetched: {total_readings}")
            if all_readings:
                print(f"Records stored: {stored_count}")
            print()

            # Display sample of latest data
            if all_readings:
                print("-" * 80)
                print("Sample of Latest Data")
                print("-" * 80)

                result = conn.execute(text("""
                    SELECT site_id, parameter_name, value, unit,
                           measured_at, is_provisional
                    FROM observations.usgs_latest_readings
                    WHERE parameter_cd = '00060'
                    ORDER BY value DESC
                    LIMIT 5;
                """))

                print("\nTop 5 Sites by Discharge:")
                print(f"{'Site ID':<12} {'Discharge':<15} {'Status':<15} {'Measured At':<25}")
                print("-" * 70)
                for row in result:
                    status = "Provisional" if row[5] else "Approved"
                    measured_str = row[4].strftime('%Y-%m-%d %H:%M UTC')
                    print(f"{row[0]:<12} {row[2]:>8.2f} {row[3]:<6} {status:<15} {measured_str:<25}")

            print()
            print(f"Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print("=" * 80)

            return True

    except Exception as e:
        print(f"\nIngestion failed!")
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    # Allow custom parameter codes as command line arguments
    param_codes = sys.argv[1:] if len(sys.argv) > 1 else None

    success = ingest_usgs_data(param_codes)
    sys.exit(0 if success else 1)
