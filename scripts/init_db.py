"""
Database Initialization Script for FNWM

Creates all necessary tables and indexes for the Fisheries National Water Model intelligence engine.

Run this script once after setting up your database connection.
"""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
from sqlalchemy import create_engine, text


def init_database():
    """Initialize database schema"""

    # Load environment variables
    load_dotenv()

    database_url = os.getenv('DATABASE_URL')

    if not database_url:
        print("❌ ERROR: DATABASE_URL not found in .env file")
        return False

    print("=" * 60)
    print("FNWM Database Initialization")
    print("=" * 60)
    print(f"Host: {os.getenv('DATABASE_HOST')}")
    print(f"Database: {os.getenv('DATABASE_NAME')}")
    print(f"User: {os.getenv('DATABASE_USER')}")
    print()

    try:
        # Create engine
        engine = create_engine(database_url)

        with engine.begin() as conn:
            print("✅ Connected to database")
            print()

            # Check PostgreSQL version
            result = conn.execute(text("SELECT version();"))
            version = result.fetchone()[0]
            print(f"PostgreSQL version: {version.split(',')[0]}")
            print()

            # Check for TimescaleDB extension
            print("Checking for TimescaleDB extension...")
            result = conn.execute(text(
                "SELECT extversion FROM pg_extension WHERE extname = 'timescaledb';"
            ))
            timescale_version = result.fetchone()

            has_timescale = timescale_version is not None

            if has_timescale:
                print(f"✅ TimescaleDB found: version {timescale_version[0]}")
            else:
                print("⚠️  TimescaleDB extension NOT installed")
                print("   Time-series optimizations will be skipped")
                print("   Consider enabling TimescaleDB for production use")
            print()

            # Start creating tables
            print("Creating database schema...")
            print("-" * 60)

            # 1. Create hydro_timeseries table
            print("Creating table: hydro_timeseries...")
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS hydro_timeseries (
                    feature_id BIGINT NOT NULL,
                    valid_time TIMESTAMPTZ NOT NULL,
                    variable VARCHAR(50) NOT NULL,
                    value DOUBLE PRECISION,
                    source VARCHAR(50) NOT NULL,
                    forecast_hour SMALLINT,
                    ingested_at TIMESTAMPTZ DEFAULT NOW(),
                    PRIMARY KEY (feature_id, valid_time, variable, source)
                );
            """))
            print("   ✅ hydro_timeseries created")

            # Convert to hypertable if TimescaleDB is available
            if has_timescale:
                print("   Converting to TimescaleDB hypertable...")
                try:
                    # Check if already a hypertable
                    result = conn.execute(text("""
                        SELECT * FROM timescaledb_information.hypertables
                        WHERE hypertable_name = 'hydro_timeseries';
                    """))

                    if result.fetchone() is None:
                        conn.execute(text("""
                            SELECT create_hypertable(
                                'hydro_timeseries',
                                'valid_time',
                                if_not_exists => TRUE
                            );
                        """))
                        print("   ✅ Converted to hypertable")
                    else:
                        print("   ℹ️  Already a hypertable")
                except Exception as e:
                    print(f"   ⚠️  Could not create hypertable: {e}")

            # Create indexes
            print("   Creating indexes...")
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_feature_time
                ON hydro_timeseries (feature_id, valid_time DESC);
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_source
                ON hydro_timeseries (source);
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_variable
                ON hydro_timeseries (variable);
            """))
            print("   ✅ Indexes created")
            print()

            # 2. Create user_observations table (for validation loop - EPIC 7)
            print("Creating table: user_observations...")
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS user_observations (
                    id SERIAL PRIMARY KEY,
                    feature_id BIGINT NOT NULL,
                    observation_time TIMESTAMPTZ NOT NULL,
                    observation_type VARCHAR(50),
                    species VARCHAR(100),
                    hatch_name VARCHAR(100),
                    success_rating INTEGER CHECK (success_rating BETWEEN 1 AND 5),
                    notes TEXT,
                    user_id VARCHAR(255),
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );
            """))
            print("   ✅ user_observations created")

            # Create indexes
            print("   Creating indexes...")
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_obs_feature_time
                ON user_observations (feature_id, observation_time DESC);
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_obs_type
                ON user_observations (observation_type);
            """))
            print("   ✅ Indexes created")
            print()

            # 3. Create reach_metadata table (for storing reach-specific context)
            print("Creating table: reach_metadata...")
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS reach_metadata (
                    feature_id BIGINT PRIMARY KEY,
                    reach_name VARCHAR(255),
                    state VARCHAR(50),
                    region VARCHAR(100),
                    domain VARCHAR(20),
                    latitude DOUBLE PRECISION,
                    longitude DOUBLE PRECISION,
                    baseline_flow_m3s DOUBLE PRECISION,
                    baseline_period VARCHAR(50),
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                );
            """))
            print("   ✅ reach_metadata created")

            # Create indexes
            print("   Creating indexes...")
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_reach_state
                ON reach_metadata (state);
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_reach_region
                ON reach_metadata (region);
            """))
            print("   ✅ Indexes created")
            print()

            # 4. Create computed_scores table (for caching species/hatch scores)
            print("Creating table: computed_scores...")
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS computed_scores (
                    id SERIAL PRIMARY KEY,
                    feature_id BIGINT NOT NULL,
                    score_type VARCHAR(50) NOT NULL,
                    score_target VARCHAR(100) NOT NULL,
                    valid_time TIMESTAMPTZ NOT NULL,
                    score_value DOUBLE PRECISION NOT NULL,
                    rating VARCHAR(50),
                    components JSONB,
                    explanation TEXT,
                    confidence VARCHAR(20),
                    computed_at TIMESTAMPTZ DEFAULT NOW(),
                    UNIQUE (feature_id, score_type, score_target, valid_time)
                );
            """))
            print("   ✅ computed_scores created")

            # Create indexes
            print("   Creating indexes...")
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_scores_feature_time
                ON computed_scores (feature_id, valid_time DESC);
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_scores_type
                ON computed_scores (score_type);
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_scores_components
                ON computed_scores USING GIN (components);
            """))
            print("   ✅ Indexes created")
            print()

            # 5. Create ingestion_log table (for monitoring data pipeline)
            print("Creating table: ingestion_log...")
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS ingestion_log (
                    id SERIAL PRIMARY KEY,
                    product VARCHAR(100) NOT NULL,
                    cycle_time TIMESTAMPTZ NOT NULL,
                    domain VARCHAR(20),
                    status VARCHAR(20) NOT NULL,
                    records_ingested INTEGER,
                    error_message TEXT,
                    started_at TIMESTAMPTZ NOT NULL,
                    completed_at TIMESTAMPTZ,
                    duration_seconds DOUBLE PRECISION
                );
            """))
            print("   ✅ ingestion_log created")

            # Create indexes
            print("   Creating indexes...")
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_log_product_time
                ON ingestion_log (product, cycle_time DESC);
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_log_status
                ON ingestion_log (status);
            """))
            print("   ✅ Indexes created")
            print()

            # Summary
            print("-" * 60)
            print("✅ Database schema initialization complete!")
            print()
            print("Tables created:")
            print("  1. hydro_timeseries       - NWM data storage" + (" (hypertable)" if has_timescale else ""))
            print("  2. user_observations      - Trip reports & validation data")
            print("  3. reach_metadata         - Reach-specific context")
            print("  4. computed_scores        - Cached species/hatch scores")
            print("  5. ingestion_log          - Data pipeline monitoring")
            print()

            # Verify tables
            result = conn.execute(text("""
                SELECT tablename
                FROM pg_tables
                WHERE schemaname = 'public'
                AND tablename IN (
                    'hydro_timeseries',
                    'user_observations',
                    'reach_metadata',
                    'computed_scores',
                    'ingestion_log'
                )
                ORDER BY tablename;
            """))

            tables = [row[0] for row in result]
            print(f"Verified {len(tables)}/5 tables exist")
            print()

            print("=" * 60)
            print("Next Steps:")
            print("=" * 60)
            print("1. Start implementing EPIC 1, Ticket 1.1:")
            print("   - src/ingest/nwm_client.py")
            print("   - src/ingest/schedulers.py")
            print("   - src/ingest/validators.py")
            print()
            print("2. See docs/guides/implementation.md for detailed guidance")
            print()
            print("3. Run 'make test' to verify your setup")
            print()

            return True

    except Exception as e:
        print(f"❌ Database initialization failed!")
        print(f"Error: {e}")
        print()
        print("Troubleshooting:")
        print("1. Check your .env file has correct credentials")
        print("2. Verify database connection with scripts/test_db_connection.py")
        print("3. Ensure you have CREATE TABLE permissions")
        return False


if __name__ == "__main__":
    success = init_database()
    sys.exit(0 if success else 1)
