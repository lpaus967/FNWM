"""
Query USGS Data from Database

Quick script to view stored USGS data and verify the database integration.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# Configure stdout for UTF-8 on Windows
if sys.platform == 'win32':
    import codecs
    if sys.stdout.encoding != 'utf-8':
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    if sys.stderr.encoding != 'utf-8':
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')


def query_usgs_data():
    """Query and display USGS data from database."""

    load_dotenv()
    database_url = os.getenv('DATABASE_URL')

    if not database_url:
        print("ERROR: DATABASE_URL not found in .env file")
        return False

    engine = create_engine(database_url)

    with engine.connect() as conn:
        print("=" * 80)
        print("USGS Data Query")
        print("=" * 80)
        print()

        # 1. Check total records
        result = conn.execute(text("""
            SELECT COUNT(*) as total_records,
                   COUNT(DISTINCT site_id) as total_sites,
                   COUNT(DISTINCT parameter_cd) as total_parameters,
                   MIN(datetime) as earliest_reading,
                   MAX(datetime) as latest_reading
            FROM observations.usgs_instantaneous_values;
        """))

        row = result.fetchone()
        print("Database Statistics:")
        print("-" * 80)
        print(f"Total records: {row[0]}")
        print(f"Unique sites: {row[1]}")
        print(f"Unique parameters: {row[2]}")
        print(f"Earliest reading: {row[3]}")
        print(f"Latest reading: {row[4]}")
        print()

        # 2. Records by parameter
        result = conn.execute(text("""
            SELECT parameter_cd, parameter_name, COUNT(*) as count
            FROM observations.usgs_instantaneous_values
            GROUP BY parameter_cd, parameter_name
            ORDER BY count DESC;
        """))

        print("Records by Parameter:")
        print("-" * 80)
        for row in result:
            print(f"  {row[0]} - {row[1]}: {row[2]} records")
        print()

        # 3. Latest readings (from materialized view)
        result = conn.execute(text("""
            SELECT
                lr.site_id,
                sf.name,
                lr.parameter_name,
                lr.value,
                lr.unit,
                lr.measured_at,
                CASE WHEN lr.is_provisional THEN 'Provisional' ELSE 'Approved' END as status
            FROM observations.usgs_latest_readings lr
            JOIN "USGS_Flowsites" sf ON lr.site_id = sf."siteId"
            WHERE lr.parameter_cd = '00060'
            ORDER BY lr.value DESC;
        """))

        print("Latest Discharge Readings (from materialized view):")
        print("-" * 80)
        print(f"{'Site ID':<12} {'Name':<35} {'Discharge':<15} {'Status':<12} {'Measured':<20}")
        print("-" * 80)
        for row in result:
            measured_str = row[5].strftime('%Y-%m-%d %H:%M')
            print(f"{row[0]:<12} {row[1][:34]:<35} {row[3]:>8.2f} {row[4]:<6} {row[6]:<12} {measured_str:<20}")
        print()

        # 4. Water temperature (if available)
        result = conn.execute(text("""
            SELECT
                lr.site_id,
                sf.name,
                lr.value,
                lr.unit,
                lr.measured_at
            FROM observations.usgs_latest_readings lr
            JOIN "USGS_Flowsites" sf ON lr.site_id = sf."siteId"
            WHERE lr.parameter_cd = '00010'
            ORDER BY lr.site_id;
        """))

        temp_rows = list(result)
        if temp_rows:
            print("Latest Water Temperature Readings:")
            print("-" * 80)
            print(f"{'Site ID':<12} {'Name':<35} {'Temp':<12} {'Measured':<20}")
            print("-" * 80)
            for row in temp_rows:
                measured_str = row[4].strftime('%Y-%m-%d %H:%M')
                print(f"{row[0]:<12} {row[1][:34]:<35} {row[2]:>6.2f} {row[3]:<5} {measured_str:<20}")
            print()

        # 5. Gage height readings
        result = conn.execute(text("""
            SELECT
                lr.site_id,
                sf.name,
                lr.value,
                lr.unit,
                lr.measured_at
            FROM observations.usgs_latest_readings lr
            JOIN "USGS_Flowsites" sf ON lr.site_id = sf."siteId"
            WHERE lr.parameter_cd = '00065'
            ORDER BY lr.value DESC;
        """))

        print("Latest Gage Height Readings:")
        print("-" * 80)
        print(f"{'Site ID':<12} {'Name':<35} {'Height':<12} {'Measured':<20}")
        print("-" * 80)
        for row in result:
            measured_str = row[4].strftime('%Y-%m-%d %H:%M')
            print(f"{row[0]:<12} {row[1][:34]:<35} {row[2]:>8.2f} {row[3]:<5} {measured_str:<20}")
        print()

        print("=" * 80)


if __name__ == "__main__":
    try:
        query_usgs_data()
        sys.exit(0)
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
