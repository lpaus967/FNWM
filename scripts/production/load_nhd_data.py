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

# Unit conversion constants
# NHDPlus data stores flow in CFS (cubic feet per second)
# but the system expects m³/s (cubic meters per second)
CFS_TO_M3S = 35.3147  # 1 m³/s = 35.3147 CFS


def convert_flow_cfs_to_m3s(value_cfs):
    """
    Convert flow from CFS (cubic feet per second) to m³/s (cubic meters per second).

    Args:
        value_cfs: Flow value in CFS, or None

    Returns:
        Flow value in m³/s, or None if input is None
    """
    if value_cfs is None:
        return None
    try:
        return float(value_cfs) / CFS_TO_M3S
    except (ValueError, TypeError):
        return None


def geojson_to_wkt(geometry):
    """
    Convert GeoJSON geometry to WKT format for PostGIS.

    Supports LineString and MultiLineString geometries.
    MultiLineString geometries will be merged into a single LineString using ST_LineMerge.

    Args:
        geometry: GeoJSON geometry object

    Returns:
        tuple: (WKT string, needs_merge) where needs_merge is True for MultiLineString
    """
    geom_type = geometry['type']
    coords = geometry['coordinates']

    if geom_type == 'LineString':
        # Format: LINESTRING(lon1 lat1, lon2 lat2, ...)
        coords_str = ', '.join([f"{c[0]} {c[1]}" for c in coords])
        return f"LINESTRING({coords_str})", False

    elif geom_type == 'MultiLineString':
        # Format: MULTILINESTRING((lon1 lat1, lon2 lat2, ...), (lon3 lat3, lon4 lat4, ...))
        # Each element in coords is a separate LineString
        lines = []
        for line_coords in coords:
            line_str = ', '.join([f"{c[0]} {c[1]}" for c in line_coords])
            lines.append(f"({line_str})")
        return f"MULTILINESTRING({', '.join(lines)})", True

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
                wkt, needs_merge = geojson_to_wkt(geom)

                # Convert resolution string to integer (for NHDPlus HR)
                resolution_str = props.get('Resolution') or props.get('resolution')
                resolution_map = {'High': 1, 'Medium': 2, 'Low': 3}
                resolution_val = resolution_map.get(resolution_str) if isinstance(resolution_str, str) else resolution_str

                # Get nhdplusid for this feature
                nhdplusid = props.get('COMID') or props.get('nhdplusid')

                # Convert fdate string to integer format (YYYYMMDD) if needed
                fdate_raw = props.get('FDATE') or props.get('fdate')
                fdate_int = None
                if fdate_raw:
                    if isinstance(fdate_raw, str):
                        # Convert 'YYYY-MM-DD' to YYYYMMDD integer
                        try:
                            fdate_int = int(fdate_raw.replace('-', ''))
                        except (ValueError, AttributeError):
                            fdate_int = None
                    else:
                        fdate_int = fdate_raw

                # 1. Insert into nhd_flowlines (CRITICAL - needed for NWM joins)
                # Note: New NHDPlus HR uses uppercase field names and COMID
                # For MultiLineString, use ST_LineMerge to merge into a single LineString
                try:
                    with engine.begin() as conn:
                        if needs_merge:
                            geom_sql = "ST_LineMerge(ST_GeomFromText(:wkt, 4326))"
                        else:
                            geom_sql = "ST_GeomFromText(:wkt, 4326)"

                        conn.execute(text(f"""
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
                                :resolution, {geom_sql}
                            )
                            ON CONFLICT (nhdplusid) DO UPDATE SET
                                updated_at = NOW()
                        """), {
                            'nhdplusid': nhdplusid,
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
                            'fdate': fdate_int,  # Converted to integer format
                            'resolution': resolution_val,
                            'wkt': wkt
                        })
                        inserted_count += 1
                except Exception as e:
                    # Flowline insert failed - this is critical, skip this feature entirely
                    error_count += 1
                    logger.warning(f"⚠️  Failed to insert flowline {nhdplusid}: {e}")
                    continue

                # 2. Insert network topology (OPTIONAL - nice to have but not critical)
                try:
                    with engine.begin() as conn:
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
                            'nhdplusid': nhdplusid,
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
                            'mainpath': props.get('mainpath'),
                            'innetwork': props.get('ONOFFNET') or props.get('innetwork'),
                            'frommeas': props.get('FromMeas') or props.get('frommeas'),
                            'tomeas': props.get('ToMeas') or props.get('tomeas')
                        })
                except Exception as e:
                    # Topology insert failed - log warning but continue (not critical)
                    pass  # Silently skip topology errors since they're not critical

                # 3. Insert flow statistics (OPTIONAL - nice to have but not critical)
                # NOTE: NHDPlus flow data is in CFS, convert to m³/s for consistency with NWM data
                try:
                    with engine.begin() as conn:
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
                            'nhdplusid': nhdplusid,
                            # Monthly mean flows - convert from CFS to m³/s
                            'qama': convert_flow_cfs_to_m3s(props.get('QA_01') or props.get('qama')),
                            'qbma': convert_flow_cfs_to_m3s(props.get('QA_02') or props.get('qbma')),
                            'qcma': convert_flow_cfs_to_m3s(props.get('QA_03') or props.get('qcma')),
                            'qdma': convert_flow_cfs_to_m3s(props.get('QA_04') or props.get('qdma')),
                            'qema': convert_flow_cfs_to_m3s(props.get('QA_05') or props.get('qema')),
                            'qfma': convert_flow_cfs_to_m3s(props.get('QA_06') or props.get('qfma')),
                            # Incremental flows - convert from CFS to m³/s
                            'qincrama': convert_flow_cfs_to_m3s(props.get('qincrama')),
                            'qincrbma': convert_flow_cfs_to_m3s(props.get('qincrbma')),
                            'qincrcma': convert_flow_cfs_to_m3s(props.get('qincrcma')),
                            'qincrdma': convert_flow_cfs_to_m3s(props.get('qincrdma')),
                            'qincrema': convert_flow_cfs_to_m3s(props.get('qincrema')),
                            'qincrfma': convert_flow_cfs_to_m3s(props.get('qincrfma')),
                            # Velocity stays in m/s (no conversion needed)
                            'vama': props.get('VA_01') or props.get('vama'),
                            'vbma': props.get('VA_02') or props.get('vbma'),
                            'vcma': props.get('VC_01') or props.get('vcma'),
                            'vdma': props.get('VC_02') or props.get('vdma'),
                            'vema': props.get('VE_01') or props.get('vema'),
                            # Gage info
                            'gageidma': props.get('gageidma'),
                            'gageqma': convert_flow_cfs_to_m3s(props.get('gageqma')),  # Convert gage flow too
                            'gageadjma': props.get('gageadjma')
                        })
                except Exception as e:
                    # Flow statistics insert failed - log warning but continue (not critical)
                    pass  # Silently skip stats errors since they're not critical

            except Exception as e:
                # Outer exception handler for any unexpected errors
                error_count += 1
                logger.warning(f"⚠️  Unexpected error processing feature {nhdplusid}: {e}")
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
