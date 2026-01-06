"""
Export map_current_conditions materialized view as GeoJSON.

This script exports the map-ready hydrology data with flowline geometry
as a GeoJSON file for use in mapping applications.

Based on EPIC 8 from IMPLEMENTATION_GUIDE.md

Usage:
    # Export all reaches
    python scripts/production/export_map_geojson.py

    # Export with filters
    python scripts/production/export_map_geojson.py --min-bdi 0.7
    python scripts/production/export_map_geojson.py --bdi-category groundwater_fed
    python scripts/production/export_map_geojson.py --min-flow 0.5
    python scripts/production/export_map_geojson.py --output custom_export.geojson
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
import os
from sqlalchemy import create_engine, text
import json
import argparse
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def build_query(args):
    """Build SQL query based on command-line arguments."""

    query = """
        SELECT
            feature_id,
            ST_AsGeoJSON(geom)::json as geometry,
            gnis_name,
            reachcode,
            drainage_area_sqkm,
            slope,
            stream_order,
            gradient_class,
            size_class,
            valid_time,
            streamflow,
            velocity,
            qbtmvertrunoff,
            qbucket,
            qsfclatrunoff,
            nudge,
            bdi,
            bdi_category,
            flow_percentile,
            flow_percentile_category,
            monthly_mean,
            air_temp_c,
            apparent_temp_c,
            water_temp_estimate_c,
            air_temp_f,
            apparent_temp_f,
            water_temp_estimate_f,
            precipitation_mm,
            cloud_cover_pct,
            temp_valid_time,
            source,
            forecast_hour,
            confidence
        FROM map_current_conditions
        WHERE 1=1
    """

    params = {}

    if args.min_bdi is not None:
        query += " AND bdi >= :min_bdi"
        params['min_bdi'] = args.min_bdi

    if args.max_bdi is not None:
        query += " AND bdi <= :max_bdi"
        params['max_bdi'] = args.max_bdi

    if args.bdi_category:
        query += " AND bdi_category = :bdi_category"
        params['bdi_category'] = args.bdi_category

    if args.min_flow is not None:
        query += " AND streamflow >= :min_flow"
        params['min_flow'] = args.min_flow

    if args.max_flow is not None:
        query += " AND streamflow <= :max_flow"
        params['max_flow'] = args.max_flow

    if args.min_percentile is not None:
        query += " AND flow_percentile >= :min_percentile"
        params['min_percentile'] = args.min_percentile

    if args.max_percentile is not None:
        query += " AND flow_percentile <= :max_percentile"
        params['max_percentile'] = args.max_percentile

    if args.stream_name:
        query += " AND gnis_name ILIKE :stream_name"
        params['stream_name'] = f"%{args.stream_name}%"

    if args.limit:
        query += f" LIMIT {args.limit}"

    return query, params

def export_geojson(args):
    """Export materialized view to GeoJSON file."""

    # Load environment
    load_dotenv()
    database_url = os.getenv('DATABASE_URL')

    if not database_url:
        logger.error("DATABASE_URL not set in environment")
        sys.exit(1)

    # Build query
    query, params = build_query(args)

    logger.info("Connecting to database...")
    engine = create_engine(database_url)

    try:
        with engine.begin() as conn:
            logger.info("Querying map data...")
            logger.info(f"Filters: {params if params else 'None'}")

            result = conn.execute(text(query), params)

            # Build GeoJSON FeatureCollection
            features = []

            for row in result:
                feature = {
                    "type": "Feature",
                    "geometry": row.geometry,
                    "properties": {
                        "feature_id": row.feature_id,
                        "stream_name": row.gnis_name,
                        "reachcode": row.reachcode,
                        "drainage_area_sqkm": round(row.drainage_area_sqkm, 2) if row.drainage_area_sqkm else None,
                        "slope": round(row.slope, 5) if row.slope else None,
                        "stream_order": row.stream_order,
                        "gradient_class": row.gradient_class,
                        "size_class": row.size_class,
                        "valid_time": row.valid_time.isoformat() if row.valid_time else None,
                        "streamflow_m3s": round(row.streamflow, 3) if row.streamflow else None,
                        "velocity_ms": round(row.velocity, 3) if row.velocity else None,
                        "qBtmVertRunoff_m3s": round(row.qbtmvertrunoff, 3) if row.qbtmvertrunoff else None,
                        "qBucket_m3s": round(row.qbucket, 3) if row.qbucket else None,
                        "qSfcLatRunoff_m3s": round(row.qsfclatrunoff, 3) if row.qsfclatrunoff else None,
                        "nudge_m3s": round(row.nudge, 3) if row.nudge else None,
                        "bdi": round(row.bdi, 3) if row.bdi else None,
                        "bdi_category": row.bdi_category,
                        "flow_percentile": round(row.flow_percentile, 1) if row.flow_percentile else None,
                        "flow_percentile_category": row.flow_percentile_category,
                        "monthly_mean_m3s": round(row.monthly_mean, 3) if row.monthly_mean else None,
                        "air_temp_c": round(row.air_temp_c, 1) if row.air_temp_c is not None else None,
                        "apparent_temp_c": round(row.apparent_temp_c, 1) if row.apparent_temp_c is not None else None,
                        "water_temp_estimate_c": round(row.water_temp_estimate_c, 1) if row.water_temp_estimate_c is not None else None,
                        "air_temp_f": round(row.air_temp_f, 1) if row.air_temp_f is not None else None,
                        "apparent_temp_f": round(row.apparent_temp_f, 1) if row.apparent_temp_f is not None else None,
                        "water_temp_estimate_f": round(row.water_temp_estimate_f, 1) if row.water_temp_estimate_f is not None else None,
                        "precipitation_mm": round(row.precipitation_mm, 1) if row.precipitation_mm is not None else None,
                        "cloud_cover_pct": round(row.cloud_cover_pct, 0) if row.cloud_cover_pct is not None else None,
                        "temp_valid_time": row.temp_valid_time.isoformat() if row.temp_valid_time else None,
                        "source": row.source,
                        "forecast_hour": row.forecast_hour,
                        "confidence": row.confidence
                    }
                }

                features.append(feature)

            geojson = {
                "type": "FeatureCollection",
                "metadata": {
                    "generated_at": datetime.utcnow().isoformat() + "Z",
                    "source": "FNWM - Fisheries National Water Model",
                    "view": "map_current_conditions",
                    "feature_count": len(features),
                    "filters": params if params else None
                },
                "features": features
            }

            logger.info(f"Exporting {len(features):,} features to GeoJSON...")

            # Determine output path
            output_path = Path(args.output) if args.output else project_root / 'data' / 'exports' / 'map_current_conditions.geojson'

            # Create output directory if needed
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Write GeoJSON file
            with open(output_path, 'w') as f:
                json.dump(geojson, f, indent=2)

            logger.info(f"✅ GeoJSON exported to: {output_path}")
            logger.info(f"File size: {output_path.stat().st_size / 1024 / 1024:.2f} MB")

            # Print summary statistics
            logger.info("\n" + "=" * 80)
            logger.info("EXPORT SUMMARY")
            logger.info("=" * 80)

            # Calculate some statistics
            if features:
                flows = [f['properties']['streamflow_m3s'] for f in features if f['properties']['streamflow_m3s']]
                bdis = [f['properties']['bdi'] for f in features if f['properties']['bdi']]

                logger.info(f"Total features: {len(features):,}")

                if flows:
                    logger.info(f"Streamflow range: {min(flows):.3f} - {max(flows):.3f} m³/s")
                    logger.info(f"Mean streamflow: {sum(flows)/len(flows):.3f} m³/s")

                if bdis:
                    logger.info(f"BDI range: {min(bdis):.3f} - {max(bdis):.3f}")
                    logger.info(f"Mean BDI: {sum(bdis)/len(bdis):.3f}")

                # Count by BDI category
                bdi_counts = {}
                for f in features:
                    cat = f['properties']['bdi_category']
                    if cat:
                        bdi_counts[cat] = bdi_counts.get(cat, 0) + 1

                if bdi_counts:
                    logger.info("\nBDI category distribution:")
                    for cat, count in sorted(bdi_counts.items()):
                        logger.info(f"  {cat}: {count:,} ({count/len(features)*100:.1f}%)")

            logger.info("\n" + "=" * 80)
            logger.info("NEXT STEPS")
            logger.info("=" * 80)
            logger.info(f"1. Load GeoJSON in QGIS, ArcGIS, or web mapping application")
            logger.info(f"2. Style features by BDI category, flow percentile, or confidence")
            logger.info(f"3. Use properties for map popups and filtering")

            return output_path

    except Exception as e:
        logger.error(f"Error exporting GeoJSON: {e}")
        raise

def main():
    parser = argparse.ArgumentParser(
        description="Export map_current_conditions view as GeoJSON",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    # Filter arguments
    parser.add_argument('--min-bdi', type=float, help='Minimum BDI threshold (0-1)')
    parser.add_argument('--max-bdi', type=float, help='Maximum BDI threshold (0-1)')
    parser.add_argument('--bdi-category', choices=['groundwater_fed', 'mixed', 'storm_dominated'],
                        help='Filter by BDI category')
    parser.add_argument('--min-flow', type=float, help='Minimum streamflow (m³/s)')
    parser.add_argument('--max-flow', type=float, help='Maximum streamflow (m³/s)')
    parser.add_argument('--min-percentile', type=float, help='Minimum flow percentile (0-100)')
    parser.add_argument('--max-percentile', type=float, help='Maximum flow percentile (0-100)')
    parser.add_argument('--stream-name', type=str, help='Filter by stream name (partial match)')
    parser.add_argument('--limit', type=int, help='Limit number of features')

    # Output argument
    parser.add_argument('--output', '-o', type=str, help='Output file path (default: data/exports/map_current_conditions.geojson)')

    args = parser.parse_args()

    export_geojson(args)

if __name__ == "__main__":
    main()
