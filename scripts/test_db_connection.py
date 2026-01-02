"""
Test database connection script
Run this to verify your AWS RDS database is accessible
"""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

def test_connection():
    """Test database connection"""

    # Load environment variables
    load_dotenv()

    database_url = os.getenv('DATABASE_URL')

    if not database_url:
        print("❌ ERROR: DATABASE_URL not found in .env file")
        return False

    print("Testing database connection...")
    print(f"Host: {os.getenv('DATABASE_HOST')}")
    print(f"Database: {os.getenv('DATABASE_NAME')}")
    print(f"User: {os.getenv('DATABASE_USER')}")
    print()

    try:
        # Create engine
        engine = create_engine(database_url)

        # Test connection
        with engine.connect() as conn:
            # Run simple query
            result = conn.execute(text("SELECT version();"))
            version = result.fetchone()[0]

            print("✅ Connection successful!")
            print(f"PostgreSQL version: {version}")
            print()

            # Check for TimescaleDB
            try:
                result = conn.execute(text("SELECT extversion FROM pg_extension WHERE extname = 'timescaledb';"))
                timescale_version = result.fetchone()

                if timescale_version:
                    print(f"✅ TimescaleDB extension found: {timescale_version[0]}")
                else:
                    print("⚠️  TimescaleDB extension NOT installed")
                    print("   You may want to enable it later for time-series optimization")
            except Exception as e:
                print(f"⚠️  Could not check for TimescaleDB: {e}")

            print()

            # List databases
            result = conn.execute(text("SELECT datname FROM pg_database WHERE datistemplate = false;"))
            databases = [row[0] for row in result]
            print(f"Available databases: {', '.join(databases)}")

            print()
            print("🎉 Database is ready to use!")
            print()
            print("Next steps:")
            print("1. Create your database schema (will be in scripts/init_db.py)")
            print("2. Start implementing EPIC 1, Ticket 1.1 (NWM Product Ingestor)")

            return True

    except Exception as e:
        print(f"❌ Connection failed!")
        print(f"Error: {e}")
        print()
        print("Troubleshooting:")
        print("1. Check your .env file has correct credentials")
        print("2. Verify your IP is allowed in AWS RDS Security Group")
        print("3. Confirm the RDS instance is 'Available' in AWS Console")
        print("4. Check if VPC/Subnet allows public access")
        return False

if __name__ == "__main__":
    success = test_connection()
    sys.exit(0 if success else 1)
