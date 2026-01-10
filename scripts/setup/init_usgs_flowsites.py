"""
USGS Flowsites Table Initialization Script

This script:
1. Creates the USGS_Flowsites table in the database
2. Loads GeoJSON data from usgsGuageTest.geojson into the table

Run this script after setting up your database connection.
"""

import os
import sys
import json
from pathlib import Path

# Add src to path
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


def create_usgs_flowsites_table(conn):
    """Create the USGS_Flowsites table using SQL file"""

    sql_file = Path(__file__).parent / "create_usgs_flowsites_table.sql"

    if not sql_file.exists():
        raise FileNotFoundError(f"SQL file not found: {sql_file}")

    print(f"Reading SQL file: {sql_file.name}")
    with open(sql_file, 'r', encoding='utf-8') as f:
        sql_content = f.read()

    print("Creating USGS_Flowsites table...")
    conn.execute(text(sql_content))
    print("✅ Table created successfully")


def load_geojson_data(conn, geojson_path):
    """Load GeoJSON data into observations.usgs_flowsites table"""

    if not os.path.exists(geojson_path):
        raise FileNotFoundError(f"GeoJSON file not found: {geojson_path}")

    print(f"\nReading GeoJSON file: {geojson_path}")
    with open(geojson_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    features = data.get('features', [])
    print(f"Found {len(features)} features to load")

    if len(features) == 0:
        print("⚠️  No features found in GeoJSON file")
        return 0

    # Prepare insert statement
    insert_sql = text("""
        INSERT INTO "USGS_Flowsites" (
            id, name, "siteId", "agencyCode", network, "stateCd", state,
            "siteTypeCd", "noaaId", "managingOr", uuid, "webcamUrl",
            "isEnabled", geom, "createdOn", "createdBy", "updatedOn", "updatedBy"
        ) VALUES (
            :id, :name, :site_id, :agency_code, :network, :state_cd, :state,
            :site_type_cd, :noaa_id, :managing_or, :uuid, :webcam_url,
            :is_enabled, ST_SetSRID(ST_MakePoint(:longitude, :latitude), 4326),
            :created_on, :created_by, :updated_on, :updated_by
        )
        ON CONFLICT ("siteId") DO UPDATE SET
            name = EXCLUDED.name,
            "agencyCode" = EXCLUDED."agencyCode",
            network = EXCLUDED.network,
            "stateCd" = EXCLUDED."stateCd",
            state = EXCLUDED.state,
            "siteTypeCd" = EXCLUDED."siteTypeCd",
            "noaaId" = EXCLUDED."noaaId",
            "managingOr" = EXCLUDED."managingOr",
            uuid = EXCLUDED.uuid,
            "webcamUrl" = EXCLUDED."webcamUrl",
            "isEnabled" = EXCLUDED."isEnabled",
            geom = EXCLUDED.geom,
            "updatedOn" = EXCLUDED."updatedOn",
            "updatedBy" = EXCLUDED."updatedBy";
    """)

    loaded_count = 0
    error_count = 0

    print("\nLoading features into database...")
    for i, feature in enumerate(features, 1):
        try:
            props = feature['properties']
            geom = feature['geometry']
            coords = geom['coordinates']

            # Extract coordinates (GeoJSON is [lon, lat, elevation])
            longitude = float(coords[0])
            latitude = float(coords[1])

            # Parse boolean for isEnabled
            is_enabled = props.get('isEnabled', 't') == 't'

            # Execute insert
            conn.execute(insert_sql, {
                'id': int(props['id']),
                'name': props['name'],
                'site_id': props['siteId'],
                'agency_code': props.get('agencyCode'),
                'network': props.get('network'),
                'state_cd': int(props['stateCd']) if props.get('stateCd') else None,
                'state': props.get('state'),
                'site_type_cd': props.get('siteTypeCd'),
                'noaa_id': props.get('noaaId'),
                'managing_or': props.get('managingOr'),
                'uuid': props.get('uuid'),
                'webcam_url': props.get('webcamUrl'),
                'is_enabled': is_enabled,
                'longitude': longitude,
                'latitude': latitude,
                'created_on': props.get('createdOn'),
                'created_by': int(props.get('createdBy', 0)),
                'updated_on': props.get('updatedOn'),
                'updated_by': int(props.get('updatedBy', 0))
            })

            loaded_count += 1

            if i % 10 == 0 or i == len(features):
                print(f"  Processed {i}/{len(features)} features...", end='\r')

        except Exception as e:
            error_count += 1
            print(f"\n⚠️  Error loading feature {i}: {e}")
            continue

    print(f"\n✅ Loaded {loaded_count} features successfully")
    if error_count > 0:
        print(f"⚠️  {error_count} features had errors")

    return loaded_count


def verify_data(conn):
    """Verify loaded data"""

    print("\nVerifying loaded data...")

    # Count rows
    result = conn.execute(text('SELECT COUNT(*) FROM "USGS_Flowsites";'))
    count = result.fetchone()[0]
    print(f"  Total records: {count}")

    # Sample data
    result = conn.execute(text('''
        SELECT id, name, "siteId", state, ST_AsText(geom) as geom_wkt
        FROM "USGS_Flowsites"
        LIMIT 3;
    '''))

    print("\n  Sample records:")
    for row in result:
        print(f"    - {row[1]} ({row[2]}) in {row[3]}")
        print(f"      Geometry: {row[4]}")

    # Count by state
    result = conn.execute(text('''
        SELECT state, COUNT(*) as count
        FROM "USGS_Flowsites"
        GROUP BY state
        ORDER BY count DESC;
    '''))

    print("\n  Records by state:")
    for row in result:
        print(f"    - {row[0]}: {row[1]} sites")


def init_usgs_flowsites(geojson_path=None):
    """Initialize USGS Flowsites table and load data"""

    # Load environment variables
    load_dotenv()

    database_url = os.getenv('DATABASE_URL')

    if not database_url:
        print("❌ ERROR: DATABASE_URL not found in .env file")
        return False

    # Default GeoJSON path if not provided
    if geojson_path is None:
        geojson_path = r"D:\Personal Projects\FNWM\Testing\Guages\usgsGuageTest.geojson"

    print("=" * 70)
    print("USGS Flowsites Table Initialization")
    print("=" * 70)
    print(f"Database Host: {os.getenv('DATABASE_HOST')}")
    print(f"Database Name: {os.getenv('DATABASE_NAME')}")
    print(f"GeoJSON File: {geojson_path}")
    print()

    try:
        # Create engine
        engine = create_engine(database_url)

        with engine.begin() as conn:
            print("✅ Connected to database")
            print()

            # Step 1: Create table
            print("-" * 70)
            print("STEP 1: Create Table")
            print("-" * 70)
            create_usgs_flowsites_table(conn)
            print()

            # Step 2: Load data
            print("-" * 70)
            print("STEP 2: Load GeoJSON Data")
            print("-" * 70)
            loaded_count = load_geojson_data(conn, geojson_path)
            print()

            # Step 3: Verify
            print("-" * 70)
            print("STEP 3: Verify Data")
            print("-" * 70)
            verify_data(conn)
            print()

            print("=" * 70)
            print("✅ USGS Flowsites initialization complete!")
            print("=" * 70)
            print()

            return True

    except Exception as e:
        print(f"❌ Initialization failed!")
        print(f"Error: {e}")
        print()
        print("Troubleshooting:")
        print("1. Check your .env file has correct credentials")
        print("2. Verify the GeoJSON file path is correct")
        print("3. Ensure you have CREATE TABLE permissions")
        return False


if __name__ == "__main__":
    # Allow custom GeoJSON path as command line argument
    geojson_path = sys.argv[1] if len(sys.argv) > 1 else None

    success = init_usgs_flowsites(geojson_path)
    sys.exit(0 if success else 1)
