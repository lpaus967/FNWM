"""
NWM-USGS Validation Table Initialization Script

Creates the validation tables for storing NWM-USGS comparison metrics.
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


def init_validation_table():
    """Initialize validation table"""

    # Load environment variables
    load_dotenv()

    database_url = os.getenv('DATABASE_URL')

    if not database_url:
        print("ERROR: DATABASE_URL not found in .env file")
        return False

    print("=" * 70)
    print("NWM-USGS Validation Table Initialization")
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
            sql_file = Path(__file__).parent / "create_validation_table.sql"

            if not sql_file.exists():
                raise FileNotFoundError(f"SQL file not found: {sql_file}")

            print(f"Reading SQL file: {sql_file.name}")
            with open(sql_file, 'r', encoding='utf-8') as f:
                sql_content = f.read()

            # Execute SQL
            print("Creating validation tables...")
            conn.execute(text(sql_content))
            print("Tables created successfully")
            print()

            # Verify table creation
            print("-" * 70)
            print("Verifying table structure...")
            print("-" * 70)

            result = conn.execute(text("""
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_name = 'nwm_usgs_validation'
                ORDER BY ordinal_position;
            """))

            print("\nTable: nwm_usgs_validation")
            print(f"{'Column':<30} {'Type':<20}")
            print("-" * 50)
            for row in result:
                print(f"{row[0]:<30} {row[1]:<20}")

            print()
            print("=" * 70)
            print("Validation table initialization complete!")
            print("=" * 70)
            print()

            return True

    except Exception as e:
        print(f"Initialization failed!")
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = init_validation_table()
    sys.exit(0 if success else 1)
