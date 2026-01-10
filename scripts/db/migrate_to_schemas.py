"""
Database Schema Migration Script

Migrates existing tables from public schema to organized domain schemas.

Usage:
    python scripts/db/migrate_to_schemas.py                    # Interactive mode
    python scripts/db/migrate_to_schemas.py --skip-confirmation # Auto-run
    python scripts/db/migrate_to_schemas.py --dry-run          # Preview only
"""

import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
import argparse


def check_existing_schemas(conn):
    """Check which schemas already exist"""
    result = conn.execute(text("""
        SELECT schema_name
        FROM information_schema.schemata
        WHERE schema_name IN ('nwm', 'spatial', 'observations', 'derived', 'validation')
    """))
    existing = [row[0] for row in result]
    return existing


def check_tables_in_public(conn):
    """Check which tables exist in public schema"""
    result = conn.execute(text("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
        AND table_type = 'BASE TABLE'
        ORDER BY table_name
    """))
    tables = [row[0] for row in result]
    return tables


def run_migration_script(conn, dry_run=False):
    """Run the SQL migration script"""
    script_path = Path(__file__).parent / 'migrate_to_schemas.sql'

    if not script_path.exists():
        print(f"ERROR: Migration script not found: {script_path}")
        return False

    print(f"\nReading migration script: {script_path}")

    with open(script_path, 'r', encoding='utf-8') as f:
        sql_script = f.read()

    if dry_run:
        print("\n" + "=" * 60)
        print("DRY RUN - Would execute:")
        print("=" * 60)
        print(sql_script[:500] + "...")
        print("\n(Script preview truncated)")
        return True

    print("\nExecuting migration...")
    print("-" * 60)

    try:
        # Execute the migration script
        result = conn.execute(text(sql_script))
        conn.commit()
        print("-" * 60)
        print("SUCCESS: Migration completed successfully!")
        return True

    except Exception as e:
        print(f"\nERROR: Migration failed: {e}")
        conn.rollback()
        return False


def verify_migration(conn):
    """Verify tables were moved correctly"""
    print("\n" + "=" * 60)
    print("Verifying Migration")
    print("=" * 60)

    schemas = ['nwm', 'spatial', 'observations', 'derived', 'validation']

    for schema in schemas:
        result = conn.execute(text(f"""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = '{schema}'
            ORDER BY table_name
        """))
        tables = [row[0] for row in result]

        print(f"\n{schema.upper()} Schema ({len(tables)} tables):")
        if tables:
            for table in tables:
                print(f"  - {table}")
        else:
            print("  (no tables)")

    # Check if any important tables remain in public
    result = conn.execute(text("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
        AND table_name IN (
            'hydro_timeseries', 'ingestion_log',
            'nhd_flowlines', 'nhd_network_topology', 'nhd_flow_statistics', 'nhd_reach_centroids',
            'USGS_Flowsites', 'usgs_instantaneous_values', 'user_observations',
            'temperature_timeseries', 'computed_scores',
            'nwm_usgs_validation'
        )
    """))
    remaining = [row[0] for row in result]

    if remaining:
        print(f"\nWARNING: Tables still in public schema: {', '.join(remaining)}")
        return False
    else:
        print("\nSUCCESS: All tables successfully migrated!")
        return True


def main():
    parser = argparse.ArgumentParser(description='Migrate database to organized schemas')
    parser.add_argument('--skip-confirmation', action='store_true',
                       help='Skip confirmation prompt')
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be done without executing')
    args = parser.parse_args()

    # Load environment
    load_dotenv()
    database_url = os.getenv('DATABASE_URL')

    if not database_url:
        print("ERROR: DATABASE_URL not found in .env file")
        return 1

    print("=" * 60)
    print("FNWM Database Schema Migration")
    print("=" * 60)
    print(f"Host: {os.getenv('DATABASE_HOST')}")
    print(f"Database: {os.getenv('DATABASE_NAME')}")
    print()

    try:
        engine = create_engine(database_url)

        with engine.begin() as conn:
            # Check current state
            print("Checking current database state...")
            existing_schemas = check_existing_schemas(conn)
            tables_in_public = check_tables_in_public(conn)

            print(f"\nExisting schemas: {', '.join(existing_schemas) if existing_schemas else 'None'}")
            print(f"Tables in public schema: {len(tables_in_public)}")

            if tables_in_public:
                print("\nTables to migrate:")
                for table in tables_in_public:
                    print(f"  - {table}")

            # Confirmation
            if not args.skip_confirmation and not args.dry_run:
                print("\n" + "=" * 60)
                print("WARNING: This will reorganize your database structure")
                print("=" * 60)
                print("This migration will:")
                print("  1. Create 5 new schemas (nwm, spatial, observations, derived, validation)")
                print("  2. Move tables from 'public' schema to domain-specific schemas")
                print("  3. Rename some tables (e.g., nhd_flowlines → nhd.flowlines)")
                print("  4. Update foreign key constraints")
                print("  5. Recreate materialized views with new references")
                print()
                print("All data will be preserved. This is a structural change only.")
                print()
                response = input("Do you want to proceed? (yes/no): ").strip().lower()

                if response not in ['yes', 'y']:
                    print("\nMigration cancelled")
                    return 0

            # Run migration
            print("\n" + "=" * 60)
            print("Starting Migration")
            print("=" * 60)

            success = run_migration_script(conn, dry_run=args.dry_run)

            if not success:
                return 1

        # Verify migration with a new connection (outside the transaction)
        if not args.dry_run and success:
            with engine.connect() as conn:
                verify_migration(conn)

            print("\n" + "=" * 60)
            print("Next Steps")
            print("=" * 60)
            print("1. Update application code to use new schema names:")
            print("   - FROM nwm.hydro_timeseries → FROM nwm.hydro_timeseries")
            print("   - FROM nhd.flowlines → FROM nhd.flowlines")
            print("   - FROM observations.usgs_flowsites → FROM observations.usgs_flowsites")
            print()
            print("2. Run the code update script:")
            print("   python scripts/db/update_code_schema_references.py")
            print()
            print("3. Test all functionality:")
            print("   python -m uvicorn src.api.main:app --reload")
            print()

        return 0

    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
