"""
NWM Ingestion Schedulers

Manages scheduled ingestion of NWM products according to their update frequency.

Design Principles:
- Each product has its own update schedule
- Graceful failure handling with retry logic
- Comprehensive logging for monitoring
- Store ingestion metadata for auditing
"""

import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from ingest.nwm_client import NWMClient, NWMProduct, Domain
from ingest.validators import validate_all
from normalize.schemas import HydroRecord, NWMSource
from normalize.time_normalizer import TimeNormalizer

# Load environment
load_dotenv()

logger = logging.getLogger(__name__)


class IngestionScheduler:
    """
    Orchestrates scheduled ingestion of NWM products.

    Each product type has a different update frequency:
    - analysis_assim: Hourly
    - short_range: Hourly
    - medium_range_blend: Every 6 hours
    - analysis_assim_no_da: Daily
    """

    # Product update frequencies (in hours)
    UPDATE_FREQUENCIES = {
        "analysis_assim": 1,
        "short_range": 1,
        "medium_range_blend": 6,
        "analysis_assim_no_da": 24,
    }

    def __init__(
        self,
        database_url: Optional[str] = None,
        nwm_client: Optional[NWMClient] = None,
        domain: Domain = "conus"
    ):
        """
        Initialize ingestion scheduler.

        Args:
            database_url: PostgreSQL connection string
            nwm_client: NWM client instance (created if not provided)
            domain: Geographic domain to ingest
        """
        self.database_url = database_url or os.getenv('DATABASE_URL')
        self.nwm_client = nwm_client or NWMClient()
        self.domain = domain

        if not self.database_url:
            raise ValueError("DATABASE_URL must be provided or set in environment")

        # Create database engine
        self.engine = create_engine(self.database_url)

        logger.info(f"Scheduler initialized for domain: {domain}")

    def log_ingestion_start(
        self,
        product: str,
        cycle_time: datetime,
        domain: str
    ) -> int:
        """
        Log the start of an ingestion job.

        Args:
            product: NWM product name
            cycle_time: Model cycle time
            domain: Geographic domain

        Returns:
            Log entry ID
        """
        with self.engine.begin() as conn:
            result = conn.execute(text("""
                INSERT INTO ingestion_log (
                    product, cycle_time, domain, status, started_at
                )
                VALUES (:product, :cycle_time, :domain, 'running', NOW())
                RETURNING id;
            """), {
                'product': product,
                'cycle_time': cycle_time,
                'domain': domain
            })
            log_id = result.fetchone()[0]

        logger.info(f"Ingestion log started: ID={log_id}")
        return log_id

    def log_ingestion_complete(
        self,
        log_id: int,
        records_ingested: int,
        error_message: Optional[str] = None
    ):
        """
        Log the completion of an ingestion job.

        Args:
            log_id: Log entry ID from log_ingestion_start
            records_ingested: Number of records successfully ingested
            error_message: Error message if failed
        """
        status = 'success' if error_message is None else 'failed'

        with self.engine.begin() as conn:
            conn.execute(text("""
                UPDATE ingestion_log
                SET
                    status = :status,
                    records_ingested = :records,
                    error_message = :error,
                    completed_at = NOW(),
                    duration_seconds = EXTRACT(EPOCH FROM (NOW() - started_at))
                WHERE id = :log_id;
            """), {
                'log_id': log_id,
                'status': status,
                'records': records_ingested,
                'error': error_message
            })

        logger.info(f"Ingestion log completed: ID={log_id}, status={status}")

    def ingest_product(
        self,
        product: NWMProduct,
        reference_time: datetime,
        forecast_hour: Optional[int] = None,
        validate: bool = True
    ) -> int:
        """
        Ingest a single NWM product into the database.

        Args:
            product: NWM product name
            reference_time: Model cycle time
            forecast_hour: Forecast hour (for forecast products)
            validate: Run validation checks before inserting

        Returns:
            Number of records inserted

        Raises:
            Exception: If ingestion fails
        """
        log_id = self.log_ingestion_start(product, reference_time, self.domain)

        try:
            # Download product
            logger.info(f"Downloading {product} for {reference_time}")
            filepath = self.nwm_client.download_product(
                product=product,
                reference_time=reference_time,
                forecast_hour=forecast_hour,
                domain=self.domain
            )

            # Parse NetCDF
            logger.info(f"Parsing {filepath}")
            df = self.nwm_client.parse_channel_rt(filepath)

            # Validate data
            if validate:
                logger.info("Validating data quality")
                is_valid, validation_results = validate_all(
                    df=df,
                    product=product,
                    domain=self.domain,
                    reference_time=reference_time,
                    forecast_hour=forecast_hour
                )

                if not is_valid:
                    error_msg = f"Validation failed: {validation_results}"
                    logger.error(error_msg)
                    self.log_ingestion_complete(log_id, 0, error_msg)
                    raise ValueError(error_msg)

            # Insert into database
            logger.info("Inserting into database")
            records_inserted = self._insert_hydro_data(
                df=df,
                product=product,
                reference_time=reference_time,
                forecast_hour=forecast_hour
            )

            # Log success
            self.log_ingestion_complete(log_id, records_inserted)

            logger.info(f"✅ Ingested {records_inserted} records for {product}")
            return records_inserted

        except Exception as e:
            error_msg = str(e)
            logger.error(f"❌ Ingestion failed: {error_msg}")
            self.log_ingestion_complete(log_id, 0, error_msg)
            raise

    def _insert_hydro_data(
        self,
        df: pd.DataFrame,
        product: str,
        reference_time: datetime,
        forecast_hour: Optional[int] = None
    ) -> int:
        """
        Insert hydrology data into hydro_timeseries table.

        Uses TimeNormalizer to convert to canonical time abstraction.
        Uses PostgreSQL COPY for fast bulk insertion.

        Args:
            df: Parsed NWM data
            product: Product name
            reference_time: Model cycle time
            forecast_hour: Forecast hour (if applicable)

        Returns:
            Number of records inserted
        """
        # Normalize the data using TimeNormalizer
        logger.info("Normalizing data to canonical time abstraction")
        records = TimeNormalizer.normalize_product(
            df=df,
            product=product,
            reference_time=reference_time,
            forecast_hour=forecast_hour
        )

        if len(records) == 0:
            logger.warning("No records to insert")
            return 0

        # Convert records to DataFrame for bulk insertion
        records_df = TimeNormalizer.records_to_dataframe(records)

        # Use PostgreSQL COPY for fast bulk insert
        logger.info(f"Inserting {len(records):,} records using PostgreSQL COPY")
        self._bulk_insert_with_copy(records_df)

        logger.info(f"Inserted {len(records):,} variable records")
        return len(records)

    def _bulk_insert_with_copy(self, df: pd.DataFrame):
        """
        Fast bulk insert using PostgreSQL COPY command.

        This is 10-100x faster than executemany() for large datasets.

        Args:
            df: DataFrame with columns: feature_id, valid_time, variable, value, source, forecast_hour
        """
        from io import StringIO
        import csv

        # Create a temporary table for staging
        with self.engine.begin() as conn:
            # Step 1: Create temp table with same structure
            conn.execute(text("""
                CREATE TEMP TABLE hydro_timeseries_staging (
                    feature_id BIGINT,
                    valid_time TIMESTAMPTZ,
                    variable VARCHAR(50),
                    value DOUBLE PRECISION,
                    source VARCHAR(50),
                    forecast_hour SMALLINT
                ) ON COMMIT DROP;
            """))

            # Step 2: Use COPY to load data into temp table (very fast)
            # Handle NULLs properly for PostgreSQL
            buffer = StringIO()
            df.to_csv(
                buffer,
                index=False,
                header=False,
                sep='\t',
                na_rep='',  # Empty string for NULL
                quoting=csv.QUOTE_NONE
            )
            buffer.seek(0)

            # Get raw connection for COPY
            raw_conn = conn.connection
            cursor = raw_conn.cursor()

            try:
                cursor.copy_expert(
                    """
                    COPY hydro_timeseries_staging (
                        feature_id, valid_time, variable, value, source, forecast_hour
                    )
                    FROM STDIN WITH (FORMAT CSV, DELIMITER E'\\t', NULL '')
                    """,
                    buffer
                )
                logger.info(f"COPY completed: {len(df):,} rows loaded to staging table")

            except Exception as e:
                logger.error(f"COPY failed: {e}")
                raise

            # Step 3: Insert from staging to final table with conflict handling
            result = conn.execute(text("""
                INSERT INTO hydro_timeseries (
                    feature_id, valid_time, variable, value, source, forecast_hour, ingested_at
                )
                SELECT
                    feature_id, valid_time, variable, value, source, forecast_hour, NOW()
                FROM hydro_timeseries_staging
                ON CONFLICT (feature_id, valid_time, variable, source)
                DO UPDATE SET
                    value = EXCLUDED.value,
                    forecast_hour = EXCLUDED.forecast_hour,
                    ingested_at = NOW();
            """))

            logger.info("Data merged from staging to final table")

    def ingest_analysis_assim(self, cycle_time: Optional[datetime] = None):
        """
        Ingest analysis_assim product (current conditions).

        Args:
            cycle_time: Specific cycle to ingest (defaults to latest)
        """
        if cycle_time is None:
            # Download latest available
            logger.info("Ingesting latest analysis_assim")
            filepath, cycle_time = self.nwm_client.download_latest_analysis(self.domain)

        return self.ingest_product(
            product="analysis_assim",
            reference_time=cycle_time,
            forecast_hour=0
        )

    def ingest_short_range(self, cycle_time: datetime):
        """
        Ingest all forecast hours of short_range product.

        Args:
            cycle_time: Model cycle time
        """
        logger.info(f"Ingesting short_range for cycle {cycle_time}")

        total_records = 0

        for forecast_hour in range(1, 19):  # f001 to f018
            try:
                records = self.ingest_product(
                    product="short_range",
                    reference_time=cycle_time,
                    forecast_hour=forecast_hour
                )
                total_records += records

            except Exception as e:
                logger.error(f"Failed to ingest f{forecast_hour:03d}: {e}")
                # Continue with other forecast hours

        logger.info(f"Ingested {total_records} total records from short_range")
        return total_records

    def ingest_medium_range_blend(self, cycle_time: datetime):
        """
        Ingest medium_range_blend product (3-10 day outlook).

        Only ingests select forecast hours for efficiency.

        Args:
            cycle_time: Model cycle time (must be 00Z, 06Z, 12Z, or 18Z)
        """
        if cycle_time.hour not in [0, 6, 12, 18]:
            raise ValueError(f"medium_range_blend only runs at 00/06/12/18Z, got {cycle_time.hour}Z")

        logger.info(f"Ingesting medium_range_blend for cycle {cycle_time}")

        # Only ingest select forecast hours for efficiency
        # f003, f006, ..., f240 (every 3 hours) would be ~80 files
        # For MVP, ingest daily forecast hours: f024, f048, f072, ..., f240
        forecast_hours = list(range(24, 241, 24))  # Daily forecasts

        total_records = 0

        for forecast_hour in forecast_hours:
            try:
                records = self.ingest_product(
                    product="medium_range_blend",
                    reference_time=cycle_time,
                    forecast_hour=forecast_hour
                )
                total_records += records

            except Exception as e:
                logger.error(f"Failed to ingest f{forecast_hour:03d}: {e}")
                # Continue with other forecast hours

        logger.info(f"Ingested {total_records} total records from medium_range_blend")
        return total_records

    def run_hourly_ingestion(self):
        """
        Run hourly ingestion tasks.

        This should be called every hour by a scheduler (cron, Airflow, etc.)
        """
        logger.info("=" * 60)
        logger.info("Starting hourly ingestion")
        logger.info("=" * 60)

        current_time = datetime.utcnow()
        current_hour = current_time.replace(minute=0, second=0, microsecond=0)

        # Always ingest analysis_assim (current conditions)
        try:
            self.ingest_analysis_assim()
        except Exception as e:
            logger.error(f"analysis_assim ingestion failed: {e}")

        # Always ingest short_range
        try:
            self.ingest_short_range(current_hour)
        except Exception as e:
            logger.error(f"short_range ingestion failed: {e}")

        # Ingest medium_range_blend every 6 hours
        if current_hour.hour in [0, 6, 12, 18]:
            try:
                self.ingest_medium_range_blend(current_hour)
            except Exception as e:
                logger.error(f"medium_range_blend ingestion failed: {e}")

        # Ingest analysis_assim_no_da daily at 00Z
        if current_hour.hour == 0:
            try:
                self.ingest_product(
                    product="analysis_assim_no_da",
                    reference_time=current_hour,
                    forecast_hour=0
                )
            except Exception as e:
                logger.error(f"analysis_assim_no_da ingestion failed: {e}")

        logger.info("=" * 60)
        logger.info("Hourly ingestion complete")
        logger.info("=" * 60)


def main():
    """
    Example usage - test ingestion
    """
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    logger.info("=" * 60)
    logger.info("Testing NWM Ingestion Scheduler")
    logger.info("=" * 60)

    # Create scheduler
    scheduler = IngestionScheduler()

    # Test: Ingest latest analysis_assim
    logger.info("\nTest: Ingesting latest analysis_assim")
    try:
        records = scheduler.ingest_analysis_assim()
        logger.info(f"✅ Ingested {records} records")
    except Exception as e:
        logger.error(f"❌ Failed: {e}")

    logger.info("\nScheduler tests complete")


if __name__ == "__main__":
    main()
