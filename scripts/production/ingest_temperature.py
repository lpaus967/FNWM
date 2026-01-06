#!/usr/bin/env python3
"""
Temperature Ingestion Script

Fetches temperature data from Open-Meteo API for all stream reach centroids
and stores it in the temperature_timeseries table.

Usage:
    python scripts/production/ingest_temperature.py [--reaches N] [--forecast-days N]

Options:
    --reaches N          Limit to N reaches (for testing)
    --forecast-days N    Number of forecast days to fetch (default: 7, max: 16)
    --batch-size N       Process N reaches per batch (default: 100)
    --delay SECONDS      Delay between API requests (default: 0.1)
"""

import argparse
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.temperature import (
    OpenMeteoClient,
    TemperatureQuery,
    TemperatureReading,
    TemperatureBatchResult,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment
load_dotenv()


def get_db_engine():
    """Create database engine."""
    db_url = (
        f"postgresql://{os.getenv('DATABASE_USER')}:{os.getenv('DATABASE_PASSWORD')}"
        f"@{os.getenv('DATABASE_HOST')}:{os.getenv('DATABASE_PORT')}"
        f"/{os.getenv('DATABASE_NAME')}"
    )
    return create_engine(db_url)


def fetch_reach_centroids(engine, limit: int = None) -> List[dict]:
    """
    Fetch reach centroids from database.

    Args:
        engine: SQLAlchemy engine
        limit: Optional limit on number of reaches

    Returns:
        List of dicts with nhdplusid, latitude, longitude
    """
    query = """
        SELECT nhdplusid, latitude, longitude
        FROM nhd_reach_centroids
        ORDER BY nhdplusid
    """

    if limit:
        query += f" LIMIT {limit}"

    with engine.begin() as conn:
        result = conn.execute(text(query))
        return [
            {
                'nhdplusid': row.nhdplusid,
                'latitude': row.latitude,
                'longitude': row.longitude,
            }
            for row in result
        ]


def insert_temperature_readings(
    engine,
    readings: List[TemperatureReading]
) -> int:
    """
    Insert temperature readings into database.

    Args:
        engine: SQLAlchemy engine
        readings: List of TemperatureReading objects

    Returns:
        Number of readings inserted
    """
    if not readings:
        return 0

    insert_query = text("""
        INSERT INTO temperature_timeseries
            (nhdplusid, valid_time, temperature_2m, apparent_temperature,
             precipitation, cloud_cover, source, forecast_hour, ingested_at)
        VALUES
            (:nhdplusid, :valid_time, :temperature_2m, :apparent_temperature,
             :precipitation, :cloud_cover, :source, :forecast_hour, :ingested_at)
        ON CONFLICT (nhdplusid, valid_time, source, forecast_hour)
        DO UPDATE SET
            temperature_2m = EXCLUDED.temperature_2m,
            apparent_temperature = EXCLUDED.apparent_temperature,
            precipitation = EXCLUDED.precipitation,
            cloud_cover = EXCLUDED.cloud_cover,
            ingested_at = EXCLUDED.ingested_at
    """)

    ingested_at = datetime.now(timezone.utc)

    with engine.begin() as conn:
        for reading in readings:
            conn.execute(insert_query, {
                'nhdplusid': reading.nhdplusid,
                'valid_time': reading.valid_time,
                'temperature_2m': reading.temperature_2m,
                'apparent_temperature': reading.apparent_temperature,
                'precipitation': reading.precipitation,
                'cloud_cover': reading.cloud_cover,
                'source': reading.source,
                'forecast_hour': reading.forecast_hour,
                'ingested_at': ingested_at,
            })

    return len(readings)


def run_ingestion(
    max_reaches: int = None,
    forecast_days: int = 7,
    batch_size: int = 100,
    delay: float = 0.1,
) -> TemperatureBatchResult:
    """
    Run temperature ingestion for all reach centroids.

    Args:
        max_reaches: Maximum number of reaches to process (None = all)
        forecast_days: Number of forecast days to fetch
        batch_size: Number of reaches to process per batch
        delay: Delay between API requests (seconds)

    Returns:
        TemperatureBatchResult with ingestion statistics
    """
    start_time = time.time()

    # Initialize
    engine = get_db_engine()
    client = OpenMeteoClient()

    # Fetch centroids
    logger.info("Fetching reach centroids from database...")
    centroids = fetch_reach_centroids(engine, limit=max_reaches)
    total_reaches = len(centroids)

    logger.info(f"Processing {total_reaches} reaches...")
    logger.info(f"Forecast days: {forecast_days}")
    logger.info(f"Batch size: {batch_size}")
    logger.info(f"API delay: {delay}s")
    logger.info("=" * 60)

    # Track results
    successful_reaches = 0
    failed_reaches = 0
    total_readings_inserted = 0
    errors = []

    # Process in batches
    for batch_start in range(0, total_reaches, batch_size):
        batch_end = min(batch_start + batch_size, total_reaches)
        batch = centroids[batch_start:batch_end]

        logger.info(
            f"\nProcessing batch {batch_start+1}-{batch_end} of {total_reaches}..."
        )

        for i, centroid in enumerate(batch, start=1):
            nhdplusid = centroid['nhdplusid']
            lat = centroid['latitude']
            lon = centroid['longitude']

            try:
                # Create query
                query = TemperatureQuery(
                    nhdplusid=nhdplusid,
                    latitude=lat,
                    longitude=lon,
                    forecast_days=forecast_days,
                    include_current=True,
                )

                # Fetch temperature data
                readings = client.fetch_for_reach(query)

                if readings:
                    # Insert into database
                    inserted = insert_temperature_readings(engine, readings)
                    total_readings_inserted += inserted
                    successful_reaches += 1

                    if i % 10 == 0:
                        logger.info(
                            f"  [{i}/{len(batch)}] Reach {nhdplusid}: "
                            f"{inserted} readings inserted"
                        )
                else:
                    failed_reaches += 1
                    error_msg = f"Reach {nhdplusid}: No data returned from API"
                    errors.append(error_msg)
                    logger.warning(f"  {error_msg}")

                # Rate limiting delay
                time.sleep(delay)

            except Exception as e:
                failed_reaches += 1
                error_msg = f"Reach {nhdplusid}: {type(e).__name__}: {e}"
                errors.append(error_msg)
                logger.error(f"  ERROR: {error_msg}")

        # Batch summary
        logger.info(
            f"Batch complete: {successful_reaches} successful, "
            f"{failed_reaches} failed"
        )

    # Final summary
    duration = time.time() - start_time

    logger.info("\n" + "=" * 60)
    logger.info("INGESTION COMPLETE")
    logger.info("=" * 60)
    logger.info(f"Total reaches: {total_reaches}")
    logger.info(f"Successful: {successful_reaches}")
    logger.info(f"Failed: {failed_reaches}")
    logger.info(f"Total readings inserted: {total_readings_inserted}")
    logger.info(f"Duration: {duration:.2f} seconds")
    logger.info(f"Throughput: {successful_reaches / duration:.2f} reaches/sec")
    logger.info("=" * 60)

    client.close()

    return TemperatureBatchResult(
        total_reaches=total_reaches,
        successful_reaches=successful_reaches,
        failed_reaches=failed_reaches,
        total_readings_inserted=total_readings_inserted,
        errors=errors[:10],  # Limit error list to first 10
        duration_seconds=duration,
    )


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Ingest temperature data from Open-Meteo API"
    )
    parser.add_argument(
        '--reaches',
        type=int,
        default=None,
        help='Limit to N reaches (for testing)',
    )
    parser.add_argument(
        '--forecast-days',
        type=int,
        default=7,
        help='Number of forecast days (default: 7, max: 16)',
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=100,
        help='Reaches per batch (default: 100)',
    )
    parser.add_argument(
        '--delay',
        type=float,
        default=0.1,
        help='Delay between API requests in seconds (default: 0.1)',
    )

    args = parser.parse_args()

    # Validate forecast days
    if args.forecast_days < 0 or args.forecast_days > 16:
        logger.error("forecast-days must be between 0 and 16")
        sys.exit(1)

    # Run ingestion
    result = run_ingestion(
        max_reaches=args.reaches,
        forecast_days=args.forecast_days,
        batch_size=args.batch_size,
        delay=args.delay,
    )

    # Exit with appropriate code
    if result.failed_reaches > 0:
        logger.warning(
            f"Completed with {result.failed_reaches} failures "
            f"({result.success_rate:.1f}% success rate)"
        )
        sys.exit(0)  # Still exit 0 if we got some data
    else:
        logger.info("All reaches processed successfully!")
        sys.exit(0)


if __name__ == "__main__":
    main()
