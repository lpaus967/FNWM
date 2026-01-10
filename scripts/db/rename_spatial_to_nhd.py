"""
Rename spatial schema to nhd

This script renames the spatial schema to nhd for clearer semantic meaning.

Usage:
    python scripts/db/rename_spatial_to_nhd.py
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

def main():
    print("=" * 60)
    print("Rename spatial schema to nhd")
    print("=" * 60)

    # Load environment
    load_dotenv()
    database_url = os.getenv('DATABASE_URL')

    if not database_url:
        print("ERROR: DATABASE_URL not found in environment")
        return 1

    # Create engine
    engine = create_engine(database_url)

    print("\nRenaming spatial schema to nhd...")

    try:
        with engine.begin() as conn:
            # Check if spatial schema exists
            result = conn.execute(text("""
                SELECT COUNT(*) FROM information_schema.schemata
                WHERE schema_name = 'spatial'
            """))
            spatial_exists = result.scalar() > 0

            if spatial_exists:
                # Rename schema
                conn.execute(text("ALTER SCHEMA spatial RENAME TO nhd"))
                print("SUCCESS: Renamed spatial schema to nhd")
            else:
                print("INFO: spatial schema not found (may already be renamed)")

            # Verify nhd schema exists
            result = conn.execute(text("""
                SELECT COUNT(*) FROM information_schema.schemata
                WHERE schema_name = 'nhd'
            """))
            nhd_exists = result.scalar() > 0

            if nhd_exists:
                print("SUCCESS: nhd schema exists")

                # List tables in nhd schema
                result = conn.execute(text("""
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = 'nhd'
                    ORDER BY table_name
                """))
                tables = [row[0] for row in result]
                print(f"\nTables in nhd schema: {', '.join(tables)}")
            else:
                print("ERROR: nhd schema not found after rename")
                return 1

        print("\n" + "=" * 60)
        print("Schema rename completed successfully!")
        print("=" * 60)
        return 0

    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
