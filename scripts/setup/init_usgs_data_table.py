"""
USGS Data Table Initialization Script

Creates the usgs_instantaneous_values table and associated materialized view
for storing real-time USGS gage data.
"""

import os
import sys
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


def init_usgs_data_table():
    """Initialize USGS data table"""

    # Load environment variables
    load_dotenv()

    database_url = os.getenv('DATABASE_URL')

    if not database_url:
        print("ERROR: DATABASE_URL not found in .env file")
        return False

    print("=" * 70)
    print("USGS Data Table Initialization")
    print("=" * 70)
    print(f"Database Host: {os.getenv('DATABASE_HOST')}")
    print(f"Database Name: {os.getenv('DATABASE_NAME')}")
    print()

    try:
        # Create engine
        engine = create_engine(database_url)

        with engine.begin() as conn:
            print("Connected to database")
            print()

            # Read SQL file
            sql_file = Path(__file__).parent / "create_usgs_data_table.sql"

            if not sql_file.exists():
                raise FileNotFoundError(f"SQL file not found: {sql_file}")

            print(f"Reading SQL file: {sql_file.name}")
            with open(sql_file, 'r', encoding='utf-8') as f:
                sql_content = f.read()

            # Execute SQL
            print("Creating USGS data tables...")
            conn.execute(text(sql_content))
            print("Tables created successfully")
            print()

            # Verify table creation
            print("-" * 70)
            print("Verifying table structure...")
            print("-" * 70)

            result = conn.execute(text("""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_name = 'usgs_instantaneous_values'
                ORDER BY ordinal_position;
            """))

            print("\nTable: usgs_instantaneous_values")
            print(f"{'Column':<30} {'Type':<20} {'Nullable':<10}")
            print("-" * 60)
            for row in result:
                print(f"{row[0]:<30} {row[1]:<20} {row[2]:<10}")

            # Check indexes
            result = conn.execute(text("""
                SELECT indexname, indexdef
                FROM pg_indexes
                WHERE tablename = 'usgs_instantaneous_values';
            """))

            print("\nIndexes:")
            for row in result:
                print(f"  - {row[0]}")

            # Check materialized view
            result = conn.execute(text("""
                SELECT COUNT(*) as exists
                FROM pg_matviews
                WHERE matviewname = 'usgs_latest_readings';
            """))

            if result.fetchone()[0] > 0:
                print("\nMaterialized View: usgs_latest_readings")
                print("  Status: Created")

            print()
            print("=" * 70)
            print("USGS data table initialization complete!")
            print("=" * 70)
            print()
            print("Next steps:")
            print("1. Run: python scripts/production/ingest_usgs_data.py")
            print("   to fetch and store current USGS gage data")
            print()
            print("2. Refresh materialized view with:")
            print("   REFRESH MATERIALIZED VIEW CONCURRENTLY usgs_latest_readings;")
            print()

            return True

    except Exception as e:
        print(f"Initialization failed!")
        print(f"Error: {e}")
        print()
        print("Troubleshooting:")
        print("1. Check your .env file has correct credentials")
        print("2. Verify USGS_Flowsites table exists (run init_usgs_flowsites.py first)")
        print("3. Ensure you have CREATE TABLE permissions")
        return False


if __name__ == "__main__":
    success = init_usgs_data_table()
    sys.exit(0 if success else 1)
