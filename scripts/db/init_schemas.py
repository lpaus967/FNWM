"""
Unified Database Schema Initialization

Creates and populates database schemas for FNWM project.
Supports initialization of individual schemas or all schemas at once.

Usage:
    python scripts/db/init_schemas.py --all                # Initialize all schemas
    python scripts/db/init_schemas.py --schema nwm          # Initialize specific schema
    python scripts/db/init_schemas.py --schema spatial --geojson path.json  # With data
    python scripts/db/init_schemas.py --list                # List available schemas
"""

import os
import sys
from pathlib import Path
import argparse

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv
from sqlalchemy import create_engine, text


# Schema definitions with their setup scripts
SCHEMAS = {
    'nwm': {
        'description': 'National Water Model hydrologic data',
        'tables': ['hydro_timeseries', 'ingestion_log'],
        'setup_sql': 'scripts/setup/schemas/nwm.sql',
        'init_script': None,
    },
    'spatial': {
        'description': 'Geospatial reference data (NHDPlus)',
        'tables': ['flowlines', 'network_topology', 'flow_statistics', 'reach_centroids', 'reach_metadata'],
        'setup_sql': 'scripts/setup/schemas/nhd.sql',
        'init_script': 'scripts/ingestion/spatial/load_nhd_data.py',
    },
    'observations': {
        'description': 'Ground truth data (USGS gages, user reports)',
        'tables': ['usgs_flowsites', 'usgs_instantaneous_values', 'usgs_latest_readings', 'user_observations'],
        'setup_sql': 'scripts/setup/schemas/observations.sql',
        'init_script': 'scripts/setup/init_usgs_flowsites.py',
    },
    'derived': {
        'description': 'Computed intelligence (temperature, scores)',
        'tables': ['temperature_timeseries', 'computed_scores', 'map_current_conditions'],
        'setup_sql': 'scripts/setup/schemas/derived.sql',
        'init_script': None,
    },
    'validation': {
        'description': 'Model performance metrics',
        'tables': ['nwm_usgs_validation', 'latest_validation_results', 'summary'],
        'setup_sql': 'scripts/setup/schemas/validation.sql',
        'init_script': None,
    },
}


def list_schemas():
    """List all available schemas"""
    print("=" * 60)
    print("Available FNWM Schemas")
    print("=" * 60)
    for name, info in SCHEMAS.items():
        print(f"\n{name.upper()}")
        print(f"  Description: {info['description']}")
        print(f"  Tables: {', '.join(info['tables'])}")
        if info['init_script']:
            print(f"  Data loader: {info['init_script']}")


def create_schema(conn, schema_name: str):
    """Create a schema if it doesn't exist"""
    conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema_name}"))
    print(f"✓ Created schema: {schema_name}")


def run_setup_sql(conn, sql_file: Path):
    """Run a SQL setup file"""
    if not sql_file.exists():
        print(f"⚠️  Setup SQL not found: {sql_file}")
        print(f"   Schema tables will need to be created manually")
        return False

    print(f"  Running: {sql_file.name}")
    with open(sql_file, 'r', encoding='utf-8') as f:
        sql = f.read()

    try:
        conn.execute(text(sql))
        conn.commit()
        return True
    except Exception as e:
        print(f"❌ Error running SQL: {e}")
        conn.rollback()
        return False


def initialize_schema(conn, schema_name: str, **kwargs):
    """Initialize a specific schema"""
    if schema_name not in SCHEMAS:
        print(f"❌ Unknown schema: {schema_name}")
        print(f"   Available: {', '.join(SCHEMAS.keys())}")
        return False

    schema_info = SCHEMAS[schema_name]
    print(f"\n{'=' * 60}")
    print(f"Initializing Schema: {schema_name.upper()}")
    print(f"{'=' * 60}")
    print(f"Description: {schema_info['description']}")
    print()

    # Create schema
    create_schema(conn, schema_name)

    # Run setup SQL
    sql_file = Path(schema_info['setup_sql'])
    if sql_file.exists():
        if run_setup_sql(conn, sql_file):
            print(f"✅ {schema_name} schema initialized")

            # Provide data loading instructions
            if schema_info['init_script']:
                print(f"\n📝 To load data, run:")
                if schema_name == 'spatial':
                    print(f"   python {schema_info['init_script']} <path-to-geojson>")
                else:
                    print(f"   python {schema_info['init_script']}")
        else:
            return False
    else:
        print(f"⚠️  Setup SQL not found: {sql_file}")
        print(f"   You'll need to create the schema manually")

    return True


def main():
    parser = argparse.ArgumentParser(
        description='Initialize FNWM database schemas',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('--all', action='store_true',
                       help='Initialize all schemas')
    parser.add_argument('--schema', type=str,
                       help='Initialize specific schema (nwm, spatial, observations, derived, validation)')
    parser.add_argument('--list', action='store_true',
                       help='List available schemas')
    parser.add_argument('--create-schemas-only', action='store_true',
                       help='Only create schema structures, no tables')

    args = parser.parse_args()

    if args.list:
        list_schemas()
        return 0

    if not args.all and not args.schema:
        parser.print_help()
        print("\nExamples:")
        print("  python scripts/db/init_schemas.py --list")
        print("  python scripts/db/init_schemas.py --all")
        print("  python scripts/db/init_schemas.py --schema spatial")
        return 1

    # Load environment
    load_dotenv()
    database_url = os.getenv('DATABASE_URL')

    if not database_url:
        print("❌ DATABASE_URL not found in .env file")
        return 1

    print("=" * 60)
    print("FNWM Schema Initialization")
    print("=" * 60)
    print(f"Host: {os.getenv('DATABASE_HOST')}")
    print(f"Database: {os.getenv('DATABASE_NAME')}")
    print()

    try:
        engine = create_engine(database_url)

        with engine.begin() as conn:
            # Check PostgreSQL version
            result = conn.execute(text("SELECT version();"))
            version = result.fetchone()[0]
            print(f"PostgreSQL: {version.split(',')[0]}")
            print()

            if args.create_schemas_only:
                # Just create the schema structures
                print("Creating schema structures only...")
                for schema_name in SCHEMAS.keys():
                    create_schema(conn, schema_name)
                print("\n✅ All schemas created")
                return 0

            # Initialize schemas
            if args.all:
                print("Initializing all schemas...")
                success_count = 0
                for schema_name in SCHEMAS.keys():
                    if initialize_schema(conn, schema_name):
                        success_count += 1

                print(f"\n{'=' * 60}")
                print(f"Initialized {success_count}/{len(SCHEMAS)} schemas successfully")
                print(f"{'=' * 60}")

            elif args.schema:
                if initialize_schema(conn, args.schema):
                    print(f"\n✅ {args.schema} schema ready")
                else:
                    print(f"\n❌ Failed to initialize {args.schema} schema")
                    return 1

        return 0

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
