"""
NHD Database Schema Initialization

Creates NHDPlus v2.1 tables for spatial integration with NWM hydrologic data.

This script creates:
- nhd_flowlines: Core spatial and attribute data
- nhd_network_topology: Stream network connections
- nhd_flow_statistics: Mean annual flow estimates

Run this script AFTER init_db.py to add NHD spatial capabilities.

Usage:
    python scripts/setup/init_nhd_schema.py
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


def init_nhd_schema():
    """Initialize NHD database schema"""

    # Load environment variables
    load_dotenv()

    database_url = os.getenv('DATABASE_URL')

    if not database_url:
        print("❌ ERROR: DATABASE_URL not found in .env file")
        return False

    print("=" * 60)
    print("NHD Schema Initialization")
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

            # Check for PostGIS extension
            print("Checking for PostGIS extension...")
            result = conn.execute(text(
                "SELECT extversion FROM pg_extension WHERE extname = 'postgis';"
            ))
            postgis_version = result.fetchone()

            has_postgis = postgis_version is not None

            if has_postgis:
                print(f"✅ PostGIS found: version {postgis_version[0]}")
            else:
                print("⚠️  PostGIS extension NOT installed")
                print("   Installing PostGIS...")
                try:
                    conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis;"))
                    print("   ✅ PostGIS installed successfully")
                    has_postgis = True
                except Exception as e:
                    print(f"   ❌ Could not install PostGIS: {e}")
                    print("   Spatial operations will not work!")
                    print("   Please install PostGIS manually")
                    return False
            print()

            # Start creating tables
            print("Creating NHD database schema...")
            print("-" * 60)

            # 1. Create nhd_flowlines table
            print("Creating table: nhd_flowlines...")
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS nhd_flowlines (
                    nhdplusid BIGINT PRIMARY KEY,
                    permanent_identifier VARCHAR(50) NOT NULL,

                    gnis_id VARCHAR(20),
                    gnis_name VARCHAR(255),
                    reachcode VARCHAR(14) NOT NULL,

                    lengthkm DOUBLE PRECISION NOT NULL,
                    areasqkm DOUBLE PRECISION,
                    totdasqkm DOUBLE PRECISION NOT NULL,
                    divdasqkm DOUBLE PRECISION,

                    streamorde SMALLINT,
                    streamleve SMALLINT,
                    streamcalc SMALLINT,
                    ftype SMALLINT,
                    fcode SMALLINT,

                    slope DOUBLE PRECISION,
                    slopelenkm DOUBLE PRECISION,
                    maxelevraw INTEGER,
                    minelevraw INTEGER,
                    maxelevsmo INTEGER,
                    minelevsmo INTEGER,

                    gradient_class VARCHAR(20),
                    size_class VARCHAR(20),
                    elev_drop_m_per_km DOUBLE PRECISION,

                    vpuid VARCHAR(4),
                    statusflag CHAR(1),
                    fdate BIGINT,
                    resolution SMALLINT,

                    geom GEOMETRY(LINESTRING, 4326) NOT NULL,

                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                );
            """))
            print("   ✅ nhd_flowlines created")

            # Create indexes for nhd_flowlines
            print("   Creating indexes...")
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_nhd_geom
                ON nhd_flowlines USING GIST (geom);
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_nhd_gnis_name
                ON nhd_flowlines (gnis_name) WHERE gnis_name IS NOT NULL;
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_nhd_streamorde
                ON nhd_flowlines (streamorde);
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_nhd_totdasqkm
                ON nhd_flowlines (totdasqkm);
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_nhd_reachcode
                ON nhd_flowlines (reachcode);
            """))
            print("   ✅ Indexes created")
            print()

            # 2. Create nhd_network_topology table
            print("Creating table: nhd_network_topology...")
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS nhd_network_topology (
                    nhdplusid BIGINT PRIMARY KEY REFERENCES nhd_flowlines(nhdplusid) ON DELETE CASCADE,

                    fromnode BIGINT,
                    tonode BIGINT,

                    hydroseq BIGINT NOT NULL,
                    levelpathi BIGINT NOT NULL,
                    terminalpa BIGINT NOT NULL,

                    uphydroseq BIGINT,
                    uplevelpat BIGINT,

                    dnhydroseq BIGINT,
                    dnlevelpat BIGINT,
                    dnminorhyd BIGINT,
                    dndraincou SMALLINT,

                    pathlength DOUBLE PRECISION,
                    arbolatesu DOUBLE PRECISION,

                    startflag SMALLINT,
                    terminalfl SMALLINT,
                    divergence SMALLINT,
                    mainpath SMALLINT,
                    innetwork SMALLINT,

                    frommeas DOUBLE PRECISION,
                    tomeas DOUBLE PRECISION
                );
            """))
            print("   ✅ nhd_network_topology created")

            # Create indexes
            print("   Creating indexes...")
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_topo_hydroseq
                ON nhd_network_topology (hydroseq);
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_topo_levelpathi
                ON nhd_network_topology (levelpathi);
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_topo_dnhydroseq
                ON nhd_network_topology (dnhydroseq) WHERE dnhydroseq IS NOT NULL;
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_topo_uphydroseq
                ON nhd_network_topology (uphydroseq) WHERE uphydroseq IS NOT NULL;
            """))
            print("   ✅ Indexes created")
            print()

            # 3. Create nhd_flow_statistics table
            print("Creating table: nhd_flow_statistics...")
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS nhd_flow_statistics (
                    nhdplusid BIGINT PRIMARY KEY REFERENCES nhd_flowlines(nhdplusid) ON DELETE CASCADE,

                    qama DOUBLE PRECISION,
                    qbma DOUBLE PRECISION,
                    qcma DOUBLE PRECISION,
                    qdma DOUBLE PRECISION,
                    qema DOUBLE PRECISION,
                    qfma DOUBLE PRECISION,

                    qincrama DOUBLE PRECISION,
                    qincrbma DOUBLE PRECISION,
                    qincrcma DOUBLE PRECISION,
                    qincrdma DOUBLE PRECISION,
                    qincrema DOUBLE PRECISION,
                    qincrfma DOUBLE PRECISION,

                    vama DOUBLE PRECISION,
                    vbma DOUBLE PRECISION,
                    vcma DOUBLE PRECISION,
                    vdma DOUBLE PRECISION,
                    vema DOUBLE PRECISION,

                    gageidma VARCHAR(20),
                    gageqma DOUBLE PRECISION,
                    gageadjma SMALLINT
                );
            """))
            print("   ✅ nhd_flow_statistics created")

            # Create indexes
            print("   Creating indexes...")
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_flow_stats_qama
                ON nhd_flow_statistics (qama) WHERE qama > 0;
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_flow_stats_qema
                ON nhd_flow_statistics (qema) WHERE qema > 0;
            """))
            print("   ✅ Indexes created")
            print()

            # 4. Create trigger function for derived metrics
            print("Creating trigger for derived metrics...")
            conn.execute(text("""
                CREATE OR REPLACE FUNCTION compute_nhd_derived_metrics()
                RETURNS TRIGGER AS $$
                BEGIN
                    NEW.gradient_class := CASE
                        WHEN NEW.slope IS NULL THEN NULL
                        WHEN NEW.slope < 0.001 THEN 'pool'
                        WHEN NEW.slope < 0.01 THEN 'run'
                        WHEN NEW.slope < 0.05 THEN 'riffle'
                        ELSE 'cascade'
                    END;

                    NEW.size_class := CASE
                        WHEN NEW.totdasqkm IS NULL THEN NULL
                        WHEN NEW.totdasqkm < 10 THEN 'headwater'
                        WHEN NEW.totdasqkm < 100 THEN 'creek'
                        WHEN NEW.totdasqkm < 1000 THEN 'small_river'
                        WHEN NEW.totdasqkm < 10000 THEN 'river'
                        ELSE 'large_river'
                    END;

                    IF NEW.maxelevraw IS NOT NULL AND NEW.minelevraw IS NOT NULL
                       AND NEW.lengthkm IS NOT NULL AND NEW.lengthkm > 0 THEN
                        NEW.elev_drop_m_per_km := ((NEW.maxelevraw - NEW.minelevraw) / 100.0) / NEW.lengthkm;
                    END IF;

                    NEW.updated_at := NOW();

                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql;
            """))

            conn.execute(text("""
                DROP TRIGGER IF EXISTS trigger_compute_nhd_metrics ON nhd_flowlines;
            """))

            conn.execute(text("""
                CREATE TRIGGER trigger_compute_nhd_metrics
                BEFORE INSERT OR UPDATE ON nhd_flowlines
                FOR EACH ROW
                EXECUTE FUNCTION compute_nhd_derived_metrics();
            """))
            print("   ✅ Trigger created")
            print()

            # Summary
            print("-" * 60)
            print("✅ NHD schema initialization complete!")
            print()

            # Verify tables
            result = conn.execute(text("""
                SELECT tablename
                FROM pg_tables
                WHERE schemaname = 'public'
                AND tablename IN (
                    'nhd_flowlines',
                    'nhd_network_topology',
                    'nhd_flow_statistics'
                )
                ORDER BY tablename;
            """))

            tables = [row[0] for row in result]
            print(f"Verified {len(tables)}/3 tables exist:")
            for table in tables:
                print(f"  ✅ {table}")
            print()

            print("=" * 60)
            print("Next Steps:")
            print("=" * 60)
            print("1. Load NHD data:")
            print("   python scripts/production/load_nhd_data.py \"D:\\Path\\To\\nhdHydrologyExample.geojson\"")
            print()
            print("2. Verify data loaded:")
            print("   (Run Python query to check row counts)")
            print()
            print("3. Test spatial queries and NWM-NHD joins")
            print()

            return True

    except Exception as e:
        print(f"❌ NHD schema initialization failed!")
        print(f"Error: {e}")
        print()
        print("Troubleshooting:")
        print("1. Ensure init_db.py was run first")
        print("2. Check that PostGIS extension is available")
        print("3. Verify you have CREATE TABLE permissions")
        return False


if __name__ == "__main__":
    success = init_nhd_schema()
    sys.exit(0 if success else 1)
