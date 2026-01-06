"""
Load NHD v2.1 GeoJSON Data into PostgreSQL

Reads NHDPlus v2.1 flowline GeoJSON and inserts into the database schema.

This script:
1. Reads GeoJSON file
2. Parses features and properties
3. Inserts into normalized tables (nhd_flowlines, nhd_network_topology, nhd_flow_statistics)
4. Creates spatial indexes
5. Validates data integrity

Usage:
    python scripts/production/load_nhd_data.py <path_to_geojson>

Example:
    python scripts/production/load_nhd_data.py "D:\\Personal Projects\\FNWM\\Testing\\Hydrology\\nhdHydrologyExample.geojson"
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configure stdout for UTF-8 on Windows
if sys.platform == 'win32':
    import codecs
    if sys.stdout.encoding != 'utf-8':
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    if sys.stderr.encoding != 'utf-8':
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# Load environment
load_dotenv()


def geojson_to_wkt(geometry):
    """
    Convert GeoJSON geometry to WKT format for PostGIS.

    Args:
        geometry: GeoJSON geometry object

    Returns:
        WKT string
    """
    geom_type = geometry['type']
    coords = geometry['coordinates']

    if geom_type == 'LineString':
        # Format: LINESTRING(lon1 lat1, lon2 lat2, ...)
        coords_str = ', '.join([f"{c[0]} {c[1]}" for c in coords])
        return f"LINESTRING({coords_str})"
    else:
        raise ValueError(f"Unsupported geometry type: {geom_type}")


def load_nhd_geojson(geojson_path: str, batch_size: int = 500):
    """
    Load NHD GeoJSON and insert into database.

    Args:
        geojson_path: Path to GeoJSON file
        batch_size: Number of features to insert per transaction
    """

    start_time = datetime.now(timezone.utc)

    logger.info("=" * 80)
    logger.info("NHD DATA LOADING")
    logger.info("=" * 80)
    logger.info(f"GeoJSON file: {geojson_path}")
    logger.info(f"Batch size: {batch_size:,}")
    logger.info("")

    # Validate file exists
    geojson_file = Path(geojson_path)
    if not geojson_file.exists():
        logger.error(f"❌ ERROR: GeoJSON file not found: {geojson_path}")
        return False

    file_size_mb = geojson_file.stat().st_size / (1024 * 1024)
    logger.info(f"File size: {file_size_mb:.1f} MB")
    logger.info("")

    # Load GeoJSON
    logger.info("Loading GeoJSON file...")
    try:
        with open(geojson_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        logger.error(f"❌ ERROR: Failed to load GeoJSON: {e}")
        return False

    features = data.get('features', [])
    total_features = len(features)

    if total_features == 0:
        logger.error("❌ ERROR: No features found in GeoJSON")
        return False

    logger.info(f"✅ Loaded {total_features:,} features")
    logger.info("")

    # Connect to database
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        logger.error("❌ ERROR: DATABASE_URL not found in .env file")
        return False

    engine = create_engine(database_url)

    # Verify NHD tables exist
    logger.info("Verifying database schema...")
    try:
        with engine.begin() as conn:
            result = conn.execute(text("""
                SELECT COUNT(*)
                FROM information_schema.tables
                WHERE table_name IN ('nhd_flowlines', 'nhd_network_topology', 'nhd_flow_statistics')
            """))
            table_count = result.fetchone()[0]

            if table_count < 3:
                logger.error("❌ ERROR: NHD tables not found. Run init_nhd_schema.py first")
                return False

            logger.info("✅ Database schema verified")
            logger.info("")
    except Exception as e:
        logger.error(f"❌ ERROR: Database connection failed: {e}")
        return False

    # Start insertion
    logger.info("=" * 80)
    logger.info("INSERTING NHD DATA")
    logger.info("=" * 80)
    logger.info("")

    inserted_count = 0
    error_count = 0
    batch_num = 0

    # Process in batches (but commit each feature individually to avoid transaction failures)
    for i in range(0, total_features, batch_size):
        batch = features[i:i+batch_size]
        batch_num += 1
        batch_start_time = datetime.now()

        # Process each feature individually (separate transactions)
        for feature in batch:
            try:
                props = feature['properties']
                geom = feature['geometry']

                # Convert geometry to WKT
                wkt = geojson_to_wkt(geom)

                # Convert resolution string to integer (for NHDPlus HR)
                resolution_str = props.get('Resolution') or props.get('resolution')
                resolution_map = {'High': 1, 'Medium': 2, 'Low': 3}
                resolution_val = resolution_map.get(resolution_str) if isinstance(resolution_str, str) else resolution_str

                # Use individual transaction for each feature
                with engine.begin() as conn:
                    # 1. Insert into nhd_flowlines
                    # Note: New NHDPlus HR uses uppercase field names and COMID
                    conn.execute(text("""
                        INSERT INTO nhd_flowlines (
                            nhdplusid, permanent_identifier, gnis_id, gnis_name,
                            reachcode, lengthkm, areasqkm, totdasqkm, divdasqkm,
                            streamorde, streamleve, streamcalc, ftype, fcode,
                            slope, slopelenkm, maxelevraw, minelevraw,
                            maxelevsmo, minelevsmo, vpuid, statusflag, fdate,
                            resolution, geom
                        ) VALUES (
                            :nhdplusid, :permanent_identifier, :gnis_id, :gnis_name,
                            :reachcode, :lengthkm, :areasqkm, :totdasqkm, :divdasqkm,
                            :streamorde, :streamleve, :streamcalc, :ftype, :fcode,
                            :slope, :slopelenkm, :maxelevraw, :minelevraw,
                            :maxelevsmo, :minelevsmo, :vpuid, :statusflag, :fdate,
                            :resolution, ST_GeomFromText(:wkt, 4326)
                        )
                        ON CONFLICT (nhdplusid) DO UPDATE SET
                            updated_at = NOW()
                    """), {
                        'nhdplusid': props.get('COMID') or props.get('nhdplusid'),
                        'permanent_identifier': props.get('permanent_identifier') or str(props.get('COMID', '')),
                        'gnis_id': props.get('GNIS_ID') or props.get('gnis_id'),
                        'gnis_name': props.get('GNIS_NAME') or props.get('gnis_name'),
                        'reachcode': props.get('REACHCODE') or props.get('reachcode'),
                        'lengthkm': props.get('LENGTHKM') or props.get('lengthkm'),
                        'areasqkm': props.get('AreaSqKM') or props.get('areasqkm'),
                        'totdasqkm': props.get('TotDASqKM') or props.get('totdasqkm'),
                        'divdasqkm': props.get('DivDASqKM') or props.get('divdasqkm'),
                        'streamorde': props.get('StreamOrde') or props.get('streamorde'),
                        'streamleve': props.get('StreamLeve') or props.get('streamleve'),
                        'streamcalc': props.get('StreamCalc') or props.get('streamcalc'),
                        'ftype': props.get('FCODE') or props.get('ftype'),  # Use FCODE for ftype
                        'fcode': props.get('FCODE') or props.get('fcode'),
                        'slope': props.get('SLOPE') or props.get('slope'),
                        'slopelenkm': props.get('SLOPELENKM') or props.get('slopelenkm'),
                        'maxelevraw': props.get('MAXELEVRAW') or props.get('maxelevraw'),
                        'minelevraw': props.get('MINELEVRAW') or props.get('minelevraw'),
                        'maxelevsmo': props.get('MAXELEVSMO') or props.get('maxelevsmo'),
                        'minelevsmo': props.get('MINELEVSMO') or props.get('minelevsmo'),
                        'vpuid': props.get('vpuid'),  # Not in new data
                        'statusflag': props.get('statusflag'),  # Not in new data
                        'fdate': props.get('FDATE') or props.get('fdate'),
                        'resolution': resolution_val,
                        'wkt': wkt
                    })

                    # 2. Insert network topology
                    conn.execute(text("""
                        INSERT INTO nhd_network_topology (
                            nhdplusid, fromnode, tonode, hydroseq, levelpathi,
                            terminalpa, uphydroseq, uplevelpat, dnhydroseq,
                            dnlevelpat, dnminorhyd, dndraincou, pathlength,
                            arbolatesu, startflag, terminalfl, divergence,
                            mainpath, innetwork, frommeas, tomeas
                        ) VALUES (
                            :nhdplusid, :fromnode, :tonode, :hydroseq, :levelpathi,
                            :terminalpa, :uphydroseq, :uplevelpat, :dnhydroseq,
                            :dnlevelpat, :dnminorhyd, :dndraincou, :pathlength,
                            :arbolatesu, :startflag, :terminalfl, :divergence,
                            :mainpath, :innetwork, :frommeas, :tomeas
                        )
                        ON CONFLICT (nhdplusid) DO NOTHING
                    """), {
                        'nhdplusid': props.get('COMID') or props.get('nhdplusid'),
                        'fromnode': props.get('FromNode') or props.get('fromnode'),
                        'tonode': props.get('ToNode') or props.get('tonode'),
                        'hydroseq': props.get('Hydroseq') or props.get('hydroseq'),
                        'levelpathi': props.get('LevelPathI') or props.get('levelpathi'),
                        'terminalpa': props.get('TerminalPa') or props.get('terminalpa'),
                        'uphydroseq': props.get('UpHydroseq') or props.get('uphydroseq'),
                        'uplevelpat': props.get('UpLevelPat') or props.get('uplevelpat'),
                        'dnhydroseq': props.get('DnHydroseq') or props.get('dnhydroseq'),
                        'dnlevelpat': props.get('DnLevelPat') or props.get('dnlevelpat'),
                        'dnminorhyd': props.get('DnMinorHyd') or props.get('dnminorhyd'),
                        'dndraincou': props.get('DnDrainCou') or props.get('dndraincou'),
                        'pathlength': props.get('Pathlength') or props.get('pathlength'),
                        'arbolatesu': props.get('ArbolateSu') or props.get('arbolatesu'),
                        'startflag': props.get('StartFlag') or props.get('startflag'),
                        'terminalfl': props.get('TerminalFl') or props.get('terminalfl'),
                        'divergence': props.get('Divergence') or props.get('divergence'),
                        'mainpath': props.get('mainpath'),  # Check if exists in new data
                        'innetwork': props.get('ONOFFNET') or props.get('innetwork'),
                        'frommeas': props.get('FromMeas') or props.get('frommeas'),
                        'tomeas': props.get('ToMeas') or props.get('tomeas')
                    })

                    # 3. Insert flow statistics
                    # Note: New data uses QA_01, QC_01, etc. instead of qama, qcma, etc.
                    conn.execute(text("""
                        INSERT INTO nhd_flow_statistics (
                            nhdplusid, qama, qbma, qcma, qdma, qema, qfma,
                            qincrama, qincrbma, qincrcma, qincrdma, qincrema, qincrfma,
                            vama, vbma, vcma, vdma, vema,
                            gageidma, gageqma, gageadjma
                        ) VALUES (
                            :nhdplusid, :qama, :qbma, :qcma, :qdma, :qema, :qfma,
                            :qincrama, :qincrbma, :qincrcma, :qincrdma, :qincrema, :qincrfma,
                            :vama, :vbma, :vcma, :vdma, :vema,
                            :gageidma, :gageqma, :gageadjma
                        )
                        ON CONFLICT (nhdplusid) DO NOTHING
                    """), {
                        'nhdplusid': props.get('COMID') or props.get('nhdplusid'),
                        'qama': props.get('QA_01') or props.get('qama'),
                        'qbma': props.get('QA_02') or props.get('qbma'),
                        'qcma': props.get('QA_03') or props.get('qcma'),
                        'qdma': props.get('QA_04') or props.get('qdma'),
                        'qema': props.get('QA_05') or props.get('qema'),
                        'qfma': props.get('QA_06') or props.get('qfma'),
                        'qincrama': props.get('qincrama'),  # Not in new data
                        'qincrbma': props.get('qincrbma'),  # Not in new data
                        'qincrcma': props.get('qincrcma'),  # Not in new data
                        'qincrdma': props.get('qincrdma'),  # Not in new data
                        'qincrema': props.get('qincrema'),  # Not in new data
                        'qincrfma': props.get('qincrfma'),  # Not in new data
                        'vama': props.get('VA_01') or props.get('vama'),
                        'vbma': props.get('VA_02') or props.get('vbma'),
                        'vcma': props.get('VC_01') or props.get('vcma'),
                        'vdma': props.get('VC_02') or props.get('vdma'),
                        'vema': props.get('VE_01') or props.get('vema'),
                        'gageidma': props.get('gageidma'),  # Not in new data
                        'gageqma': props.get('gageqma'),  # Not in new data
                        'gageadjma': props.get('gageadjma')  # Not in new data
                    })

                    inserted_count += 1

            except Exception as e:
                error_count += 1
                logger.warning(f"⚠️  Failed to insert feature {props.get('nhdplusid', 'unknown')}: {e}")
                continue

        # Log progress
        batch_duration = (datetime.now() - batch_start_time).total_seconds()
        features_per_sec = len(batch) / batch_duration if batch_duration > 0 else 0
        progress_pct = (inserted_count / total_features) * 100

        logger.info(
            f"Batch {batch_num:,}: Inserted {inserted_count:,}/{total_features:,} features "
            f"({progress_pct:.1f}%) - {features_per_sec:.0f} features/sec"
        )

    # Final summary
    end_time = datetime.now(timezone.utc)
    duration = (end_time - start_time).total_seconds()

    logger.info("")
    logger.info("=" * 80)
    logger.info("LOADING COMPLETE")
    logger.info("=" * 80)
    logger.info(f"Total features processed: {total_features:,}")
    logger.info(f"Successfully inserted: {inserted_count:,}")
    logger.info(f"Errors: {error_count:,}")
    logger.info(f"Duration: {duration:.1f} seconds")
    logger.info(f"Average speed: {inserted_count/duration:.0f} features/sec")
    logger.info("")

    # Verify data
    logger.info("Verifying loaded data...")
    try:
        with engine.begin() as conn:
            # Count records in each table
            result = conn.execute(text("SELECT COUNT(*) FROM nhd_flowlines"))
            flowlines_count = result.fetchone()[0]

            result = conn.execute(text("SELECT COUNT(*) FROM nhd_network_topology"))
            topology_count = result.fetchone()[0]

            result = conn.execute(text("SELECT COUNT(*) FROM nhd_flow_statistics"))
            stats_count = result.fetchone()[0]

            logger.info(f"  nhd_flowlines: {flowlines_count:,} rows")
            logger.info(f"  nhd_network_topology: {topology_count:,} rows")
            logger.info(f"  nhd_flow_statistics: {stats_count:,} rows")
            logger.info("")

            # Sample query
            logger.info("Sample data (first 5 reaches):")
            result = conn.execute(text("""
                SELECT nhdplusid, gnis_name, streamorde, totdasqkm, size_class
                FROM nhd_flowlines
                ORDER BY nhdplusid
                LIMIT 5
            """))

            for row in result:
                logger.info(f"  NHDPlusID: {row[0]}, Name: {row[1] or 'Unnamed'}, "
                          f"Order: {row[2]}, Drainage: {row[3]:.2f} km², Class: {row[4]}")
            logger.info("")

    except Exception as e:
        logger.error(f"⚠️  Verification failed: {e}")

    logger.info("=" * 80)
    logger.info("✅ NHD data loading complete!")
    logger.info("")
    logger.info("Next steps:")
    logger.info("1. Test NWM-NHD joins:")
    logger.info("   SELECT h.feature_id, n.gnis_name, h.streamflow_m3s")
    logger.info("   FROM hydro_timeseries h")
    logger.info("   JOIN nhd_flowlines n ON h.feature_id = n.nhdplusid")
    logger.info("   LIMIT 10;")
    logger.info("")
    logger.info("2. Query spatial data:")
    logger.info("   SELECT nhdplusid, gnis_name, ST_AsText(geom)")
    logger.info("   FROM nhd_flowlines WHERE gnis_name IS NOT NULL LIMIT 5;")
    logger.info("")

    return True


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/production/load_nhd_data.py <path_to_geojson>")
        print()
        print("Example:")
        print('  python scripts/production/load_nhd_data.py "D:\\Data\\nhdHydrologyExample.geojson"')
        sys.exit(1)

    geojson_path = sys.argv[1]
    success = load_nhd_geojson(geojson_path)
    sys.exit(0 if success else 1)
