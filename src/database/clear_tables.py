"""
Database Table Clearing Utilities

Provides functions to clear all tables in the FNWM database.
Can be used as a standalone script or imported into other scripts.

Usage as script:
    python -m src.database.clear_tables
    python -m src.database.clear_tables --skip-confirmation

Usage as module:
    from src.database.clear_tables import clear_all_tables
    import psycopg2

    conn = psycopg2.connect(...)
    clear_all_tables(conn, skip_confirmation=True)
"""

import os
import sys
from typing import Optional
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from dotenv import load_dotenv


def get_db_connection():
    """Get database connection from environment variables."""
    load_dotenv()

    db_url = os.getenv("DATABASE_URL")
    if db_url:
        return psycopg2.connect(db_url)

    # Fallback to individual parameters
    return psycopg2.connect(
        host=os.getenv("DATABASE_HOST", "localhost"),
        port=os.getenv("DATABASE_PORT", "5432"),
        dbname=os.getenv("DATABASE_NAME", "fnwm"),
        user=os.getenv("DATABASE_USER", "fnwm_user"),
        password=os.getenv("DATABASE_PASSWORD")
    )


def clear_all_tables(conn, skip_confirmation: bool = False, verbose: bool = True) -> dict:
    """
    Clear all tables in the database.

    Uses TRUNCATE CASCADE for speed and to reset auto-increment sequences.
    Handles foreign key constraints by clearing tables in the correct order.

    Args:
        conn: psycopg2 database connection
        skip_confirmation: If True, skip the user confirmation prompt
        verbose: If True, print progress messages

    Returns:
        dict: Summary of cleared tables with row counts

    Tables cleared (in dependency order):
        - temperature_timeseries (FK to nhd_reach_centroids)
        - nhd_reach_centroids (FK to nhd_flowlines)
        - computed_scores (FK to reach_metadata)
        - user_observations (standalone)
        - hydro_timeseries (TimescaleDB hypertable)
        - ingestion_log (standalone)
        - nhd_network_topology (FK to nhd_flowlines)
        - nhd_flow_statistics (FK to nhd_flowlines)
        - nhd_flowlines (parent table)
        - reach_metadata (parent table)
    """
    cursor = conn.cursor()

    # Tables in dependency order (children before parents)
    table_names = [
        'temperature_timeseries',
        'nhd_reach_centroids',
        'computed_scores',
        'user_observations',
        'hydro_timeseries',
        'ingestion_log',
        'nhd_network_topology',
        'nhd_flow_statistics',
        'nhd_flowlines',
        'reach_metadata'
    ]

    # Get current table counts
    tables_info = []
    for table in table_names:
        try:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            tables_info.append((table, count))
        except psycopg2.Error:
            tables_info.append((table, 0))

    total_rows = sum(count for _, count in tables_info)

    # Display current status
    if verbose:
        print("\n" + "="*80)
        print("DATABASE TABLE STATUS")
        print("="*80)
        for table, count in tables_info:
            if count > 0:
                print(f"  {table:30s} : {count:>12,} rows")
            else:
                print(f"  {table:30s} : (empty or doesn't exist)")
        print("="*80)
        print(f"TOTAL: {total_rows:,} rows across {len(table_names)} tables")
        print("="*80)

    if total_rows == 0:
        if verbose:
            print("\n✓ All tables are already empty. Nothing to clear.")
        return {table: 0 for table in table_names}

    # Confirmation prompt
    if not skip_confirmation:
        print(f"\n⚠️  WARNING: This will DELETE {total_rows:,} rows from {len(table_names)} tables!")
        print("⚠️  This operation CANNOT be undone!")
        response = input("\nType 'DELETE ALL DATA' to confirm: ")

        if response != "DELETE ALL DATA":
            if verbose:
                print("\n❌ Operation cancelled. No data was deleted.")
            return {}

    if verbose:
        print("\n🗑️  Clearing all tables...")

    # Truncate tables
    cleared_tables = {}
    for table in table_names:
        try:
            # Get count before truncating
            count = next(c for t, c in tables_info if t == table)

            # Use TRUNCATE CASCADE for speed
            cursor.execute(f"TRUNCATE TABLE {table} CASCADE")
            cleared_tables[table] = count

            if verbose:
                print(f"  ✓ Cleared {table} ({count:,} rows)")
        except psycopg2.Error as e:
            if verbose:
                error_msg = e.pgerror.split(':')[0] if e.pgerror else 'does not exist'
                print(f"  ⚠ Skipped {table} ({error_msg})")
            cleared_tables[table] = 0

    conn.commit()

    if verbose:
        print(f"\n✓ Successfully cleared {len([c for c in cleared_tables.values() if c > 0])} tables!")
        print(f"✓ Total rows deleted: {sum(cleared_tables.values()):,}\n")

    return cleared_tables


def clear_specific_tables(conn, table_names: list, skip_confirmation: bool = False, verbose: bool = True) -> dict:
    """
    Clear specific tables by name.

    Args:
        conn: psycopg2 database connection
        table_names: List of table names to clear
        skip_confirmation: If True, skip the user confirmation prompt
        verbose: If True, print progress messages

    Returns:
        dict: Summary of cleared tables with row counts
    """
    cursor = conn.cursor()

    # Get current table counts
    tables_info = []
    for table in table_names:
        try:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            tables_info.append((table, count))
        except psycopg2.Error:
            tables_info.append((table, 0))

    total_rows = sum(count for _, count in tables_info)

    if verbose:
        print("\n" + "="*80)
        print("TABLES TO CLEAR")
        print("="*80)
        for table, count in tables_info:
            print(f"  {table:30s} : {count:>12,} rows")
        print("="*80)

    if total_rows == 0:
        if verbose:
            print("\n✓ Selected tables are already empty.")
        return {table: 0 for table in table_names}

    # Confirmation prompt
    if not skip_confirmation:
        print(f"\n⚠️  WARNING: This will DELETE {total_rows:,} rows from {len(table_names)} tables!")
        response = input("\nType 'DELETE' to confirm: ")

        if response != "DELETE":
            if verbose:
                print("\n❌ Operation cancelled.")
            return {}

    if verbose:
        print("\n🗑️  Clearing tables...")

    # Truncate tables
    cleared_tables = {}
    for table in table_names:
        try:
            count = next(c for t, c in tables_info if t == table)
            cursor.execute(f"TRUNCATE TABLE {table} CASCADE")
            cleared_tables[table] = count

            if verbose:
                print(f"  ✓ Cleared {table} ({count:,} rows)")
        except psycopg2.Error as e:
            if verbose:
                error_msg = e.pgerror.split(':')[0] if e.pgerror else 'error'
                print(f"  ✗ Failed to clear {table}: {error_msg}")
            cleared_tables[table] = 0

    conn.commit()

    if verbose:
        print(f"\n✓ Operation complete! Deleted {sum(cleared_tables.values()):,} rows.\n")

    return cleared_tables


def main():
    """Command-line interface for clearing tables."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Clear all tables in the FNWM database",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--skip-confirmation",
        action="store_true",
        help="Skip the confirmation prompt (use with caution!)"
    )
    parser.add_argument(
        "--tables",
        nargs="+",
        help="Specific tables to clear (default: all tables)"
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress output"
    )

    args = parser.parse_args()

    try:
        conn = get_db_connection()

        if args.tables:
            clear_specific_tables(
                conn,
                args.tables,
                skip_confirmation=args.skip_confirmation,
                verbose=not args.quiet
            )
        else:
            clear_all_tables(
                conn,
                skip_confirmation=args.skip_confirmation,
                verbose=not args.quiet
            )

        conn.close()

    except KeyboardInterrupt:
        print("\n\n⚠️  Operation cancelled by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
