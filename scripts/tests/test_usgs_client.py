"""
Test USGS Water Services Client

Fetches current conditions for all USGS sites in the USGS_Flowsites table.
"""

import os
import sys
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from src.usgs.client import USGSClient, ParameterCodes

# Configure stdout for UTF-8 on Windows
if sys.platform == 'win32':
    import codecs
    if sys.stdout.encoding != 'utf-8':
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    if sys.stderr.encoding != 'utf-8':
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')


def get_usgs_sites_from_db():
    """Fetch all USGS site IDs from the database."""
    load_dotenv()

    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        raise ValueError("DATABASE_URL not found in .env file")

    engine = create_engine(database_url)

    with engine.connect() as conn:
        result = conn.execute(text('''
            SELECT "siteId", name, state, ST_X(geom) as lon, ST_Y(geom) as lat
            FROM "USGS_Flowsites"
            WHERE "isEnabled" = TRUE
            ORDER BY "siteId";
        '''))

        sites = []
        for row in result:
            sites.append({
                'site_id': row[0],
                'name': row[1],
                'state': row[2],
                'longitude': row[3],
                'latitude': row[4]
            })

        return sites


def test_usgs_client():
    """Test USGS client with sites from database."""

    print("=" * 80)
    print("USGS Water Services Client Test")
    print("=" * 80)
    print()

    # Get sites from database
    print("Fetching USGS sites from database...")
    sites = get_usgs_sites_from_db()
    print(f"Found {len(sites)} enabled USGS sites")
    print()

    # Display sites
    print("Sites to query:")
    print("-" * 80)
    for site in sites:
        print(f"  {site['site_id']}: {site['name']}")
    print()

    # Initialize USGS client
    print("Initializing USGS client...")
    client = USGSClient(timeout=30)
    print("Client initialized")
    print()

    # Fetch current conditions
    print("-" * 80)
    print("Fetching current conditions...")
    print("-" * 80)
    site_ids = [site['site_id'] for site in sites]

    # Fetch discharge and gage height
    results = client.fetch_current_conditions(
        site_ids=site_ids,
        parameter_codes=[ParameterCodes.DISCHARGE, ParameterCodes.GAGE_HEIGHT]
    )

    # Display results
    print()
    print("=" * 80)
    print("RESULTS")
    print("=" * 80)
    print()

    success_count = 0
    failure_count = 0

    for result in results:
        site_name = next((s['name'] for s in sites if s['site_id'] == result.site_id), 'Unknown')

        if result.success:
            success_count += 1
            print(f"✓ {result.site_id}: {site_name}")

            if result.data:
                # Group by parameter
                discharge_readings = [r for r in result.data if r.parameter_cd == ParameterCodes.DISCHARGE]
                gage_height_readings = [r for r in result.data if r.parameter_cd == ParameterCodes.GAGE_HEIGHT]

                if discharge_readings:
                    latest = max(discharge_readings, key=lambda x: x.datetime)
                    status = "PROVISIONAL" if latest.is_provisional else "APPROVED"
                    print(f"  Discharge: {latest.value} {latest.unit} ({status})")
                    print(f"  Measured: {latest.datetime.strftime('%Y-%m-%d %H:%M:%S UTC')}")

                if gage_height_readings:
                    latest = max(gage_height_readings, key=lambda x: x.datetime)
                    print(f"  Gage Height: {latest.value} {latest.unit}")

                print(f"  Total readings: {len(result.data)}")
            else:
                print("  No data available")

        else:
            failure_count += 1
            print(f"✗ {result.site_id}: {site_name}")
            print(f"  Error: {result.error}")

        print()

    # Summary
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Total sites queried: {len(results)}")
    print(f"Successful: {success_count}")
    print(f"Failed: {failure_count}")
    print()

    # Additional test: Fetch with period parameter
    if success_count > 0:
        print("-" * 80)
        print("Testing period parameter (last 6 hours)...")
        print("-" * 80)

        # Test with first successful site
        test_site = next(r.site_id for r in results if r.success)
        period_results = client.fetch_current_conditions(
            site_ids=[test_site],
            parameter_codes=[ParameterCodes.DISCHARGE],
            period='PT6H'  # Last 6 hours
        )

        if period_results and period_results[0].success:
            data_count = len(period_results[0].data) if period_results[0].data else 0
            print(f"Site {test_site}: Retrieved {data_count} readings from last 6 hours")
            print()


if __name__ == "__main__":
    try:
        test_usgs_client()
        print("✓ Test completed successfully")
        sys.exit(0)
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
