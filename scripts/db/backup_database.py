"""
Database Backup Script

Creates a backup of the database before migration.

Usage:
    python scripts/db/backup_database.py                    # Auto-generate filename
    python scripts/db/backup_database.py --output backup.sql # Specify filename
"""

import os
import sys
import subprocess
from pathlib import Path
from datetime import datetime
import argparse

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv


def create_backup(output_file: str = None):
    """Create database backup using pg_dump"""

    # Load environment
    load_dotenv()

    host = os.getenv('DATABASE_HOST')
    port = os.getenv('DATABASE_PORT', '5432')
    database = os.getenv('DATABASE_NAME')
    user = os.getenv('DATABASE_USER')
    password = os.getenv('DATABASE_PASSWORD')

    if not all([host, database, user, password]):
        print("❌ Missing database credentials in .env file")
        return 1

    # Generate output filename if not provided
    if not output_file:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = f"backup_{timestamp}.sql"

    output_path = Path(output_file)

    print("=" * 60)
    print("FNWM Database Backup")
    print("=" * 60)
    print(f"Host: {host}")
    print(f"Database: {database}")
    print(f"Output: {output_path.absolute()}")
    print()

    # Set password environment variable for pg_dump
    env = os.environ.copy()
    env['PGPASSWORD'] = password

    # Build pg_dump command
    cmd = [
        'pg_dump',
        '-h', host,
        '-p', port,
        '-U', user,
        '-d', database,
        '-f', str(output_path),
        '--verbose'
    ]

    print("Creating backup...")
    print("-" * 60)

    try:
        # Run pg_dump
        result = subprocess.run(
            cmd,
            env=env,
            capture_output=True,
            text=True
        )

        if result.returncode == 0:
            # Check file size
            size_bytes = output_path.stat().st_size
            size_mb = size_bytes / (1024 * 1024)

            print("-" * 60)
            print(f"✅ Backup created successfully!")
            print(f"   File: {output_path.absolute()}")
            print(f"   Size: {size_mb:.2f} MB")
            print()
            print("You can now proceed with migration:")
            print("   python scripts/db/migrate_to_schemas.py")
            return 0
        else:
            print(f"❌ Backup failed!")
            print(f"Error: {result.stderr}")
            return 1

    except FileNotFoundError:
        print("❌ pg_dump not found!")
        print()
        print("PostgreSQL client tools are not installed or not in PATH.")
        print()
        print("Options:")
        print("  1. Install PostgreSQL client tools")
        print("  2. Use pgAdmin or another GUI tool to create backup")
        print("  3. Use AWS RDS snapshot (recommended for production)")
        print()
        print("To proceed without backup (NOT RECOMMENDED):")
        print("   python scripts/db/migrate_to_schemas.py --skip-confirmation")
        return 1

    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return 1


def main():
    parser = argparse.ArgumentParser(description='Backup FNWM database')
    parser.add_argument('--output', '-o', type=str,
                       help='Output filename (default: backup_YYYYMMDD_HHMMSS.sql)')
    args = parser.parse_args()

    return create_backup(args.output)


if __name__ == "__main__":
    sys.exit(main())
