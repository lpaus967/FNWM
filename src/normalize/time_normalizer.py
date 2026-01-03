"""
Time Normalization Service

Converts all NWM products into a single canonical time abstraction.

Design Principles:
- All forecast hours (f001, f018, etc.) are converted to valid_time
- No f### references leak downstream
- valid_time is always UTC timezone-aware
- Source is explicitly tagged for traceability
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import pandas as pd
from pydantic import BaseModel

from normalize.schemas import NWMSource, HydroVariable, HydroRecord

logger = logging.getLogger(__name__)


class TimeNormalizer:
    """
    Normalizes NWM product time semantics into canonical abstractions.

    Maps NWM products to internal time concepts:
    - analysis_assim -> "now"
    - short_range (f001-f018) -> "today"
    - medium_range_blend -> "outlook"
    - analysis_assim_no_da -> internal use only
    """

    # Map product names to NWMSource enum
    PRODUCT_TO_SOURCE = {
        "analysis_assim": NWMSource.ANALYSIS_ASSIM,
        "short_range": NWMSource.SHORT_RANGE,
        "medium_range_blend": NWMSource.MEDIUM_BLEND,
        "analysis_assim_no_da": NWMSource.NO_DA,
    }

    @staticmethod
    def normalize_analysis_assim(
        df: pd.DataFrame,
        reference_time: datetime
    ) -> list[HydroRecord]:
        """
        Normalize analysis_assim product.

        This represents "now" - current conditions.
        For tm00 (analysis), valid_time = reference_time.

        Args:
            df: Parsed NWM data with wide format
            reference_time: Model cycle time

        Returns:
            List of normalized HydroRecord objects
        """
        logger.info(f"Normalizing analysis_assim for {reference_time}")

        # Ensure reference_time is UTC timezone-aware
        if reference_time.tzinfo is None:
            reference_time = reference_time.replace(tzinfo=timezone.utc)

        # For analysis (tm00), valid_time = reference_time
        valid_time = reference_time

        records = TimeNormalizer._dataframe_to_records(
            df=df,
            valid_time=valid_time,
            source=NWMSource.ANALYSIS_ASSIM,
            forecast_hour=None  # Analysis has no forecast
        )

        logger.info(f"Normalized {len(records)} records for analysis_assim")
        return records

    @staticmethod
    def normalize_short_range(
        df: pd.DataFrame,
        reference_time: datetime,
        forecast_hour: int
    ) -> list[HydroRecord]:
        """
        Normalize short_range forecast product.

        This represents "today" - next 18 hours.
        valid_time = reference_time + forecast_hour

        Args:
            df: Parsed NWM data
            reference_time: Model cycle time
            forecast_hour: Forecast hour (1-18)

        Returns:
            List of normalized HydroRecord objects
        """
        logger.info(f"Normalizing short_range f{forecast_hour:03d} for {reference_time}")

        # Ensure reference_time is UTC timezone-aware
        if reference_time.tzinfo is None:
            reference_time = reference_time.replace(tzinfo=timezone.utc)

        # Calculate valid_time
        valid_time = reference_time + timedelta(hours=forecast_hour)

        records = TimeNormalizer._dataframe_to_records(
            df=df,
            valid_time=valid_time,
            source=NWMSource.SHORT_RANGE,
            forecast_hour=forecast_hour
        )

        logger.info(f"Normalized {len(records)} records for short_range f{forecast_hour:03d}")
        return records

    @staticmethod
    def normalize_medium_range_blend(
        df: pd.DataFrame,
        reference_time: datetime,
        forecast_hour: int
    ) -> list[HydroRecord]:
        """
        Normalize medium_range_blend forecast product.

        This represents "outlook" - 3-10 day forecast.
        valid_time = reference_time + forecast_hour

        Args:
            df: Parsed NWM data
            reference_time: Model cycle time
            forecast_hour: Forecast hour (3-240)

        Returns:
            List of normalized HydroRecord objects
        """
        logger.info(f"Normalizing medium_range_blend f{forecast_hour:03d} for {reference_time}")

        # Ensure reference_time is UTC timezone-aware
        if reference_time.tzinfo is None:
            reference_time = reference_time.replace(tzinfo=timezone.utc)

        # Calculate valid_time
        valid_time = reference_time + timedelta(hours=forecast_hour)

        records = TimeNormalizer._dataframe_to_records(
            df=df,
            valid_time=valid_time,
            source=NWMSource.MEDIUM_BLEND,
            forecast_hour=forecast_hour
        )

        logger.info(f"Normalized {len(records)} records for medium_range_blend f{forecast_hour:03d}")
        return records

    @staticmethod
    def normalize_analysis_assim_no_da(
        df: pd.DataFrame,
        reference_time: datetime
    ) -> list[HydroRecord]:
        """
        Normalize analysis_assim_no_da product.

        This is for internal ecological analysis only (no gauge nudging).
        valid_time = reference_time

        Args:
            df: Parsed NWM data
            reference_time: Model cycle time

        Returns:
            List of normalized HydroRecord objects
        """
        logger.info(f"Normalizing analysis_assim_no_da for {reference_time}")

        # Ensure reference_time is UTC timezone-aware
        if reference_time.tzinfo is None:
            reference_time = reference_time.replace(tzinfo=timezone.utc)

        valid_time = reference_time

        records = TimeNormalizer._dataframe_to_records(
            df=df,
            valid_time=valid_time,
            source=NWMSource.NO_DA,
            forecast_hour=None
        )

        logger.info(f"Normalized {len(records)} records for analysis_assim_no_da")
        return records

    @staticmethod
    def _dataframe_to_records(
        df: pd.DataFrame,
        valid_time: datetime,
        source: NWMSource,
        forecast_hour: Optional[int]
    ) -> list[HydroRecord]:
        """
        Convert wide DataFrame to list of HydroRecord objects.

        Transforms from wide format (one row per reach, columns for variables)
        to long format (one record per reach per variable).

        Args:
            df: DataFrame with columns like streamflow_m3s, velocity_ms, etc.
            valid_time: Valid time for these records
            source: NWM product source
            forecast_hour: Forecast hour (None for analysis)

        Returns:
            List of HydroRecord objects
        """
        records = []

        # Define variable mappings (DataFrame column -> HydroVariable enum)
        variable_mapping = {
            'streamflow_m3s': HydroVariable.STREAMFLOW,
            'velocity_ms': HydroVariable.VELOCITY,
            'qSfcLatRunoff_m3s': HydroVariable.QSFC_LAT_RUNOFF,
            'qBucket_m3s': HydroVariable.QBUCKET,
            'qBtmVertRunoff_m3s': HydroVariable.QBTM_VERT_RUNOFF,
            'nudge_m3s': HydroVariable.NUDGE,
        }

        # Iterate through each reach
        for _, row in df.iterrows():
            feature_id = int(row['feature_id'])

            # Create record for each variable
            for df_col, hydro_var in variable_mapping.items():
                if df_col in row and pd.notna(row[df_col]):
                    try:
                        record = HydroRecord(
                            feature_id=feature_id,
                            valid_time=valid_time,
                            variable=hydro_var,
                            value=float(row[df_col]),
                            source=source,
                            forecast_hour=forecast_hour
                        )
                        records.append(record)
                    except Exception as e:
                        logger.warning(
                            f"Failed to create record for feature {feature_id}, "
                            f"variable {hydro_var}: {e}"
                        )
                        continue

        return records

    @staticmethod
    def normalize_product(
        df: pd.DataFrame,
        product: str,
        reference_time: datetime,
        forecast_hour: Optional[int] = None
    ) -> list[HydroRecord]:
        """
        Normalize any NWM product to canonical time abstraction.

        This is the main entry point for normalization.

        Args:
            df: Parsed NWM data
            product: Product name ('analysis_assim', 'short_range', etc.)
            reference_time: Model cycle time
            forecast_hour: Forecast hour (required for forecast products)

        Returns:
            List of normalized HydroRecord objects

        Raises:
            ValueError: If product is invalid or forecast_hour is missing
        """
        if product not in TimeNormalizer.PRODUCT_TO_SOURCE:
            raise ValueError(
                f"Invalid product '{product}'. "
                f"Must be one of: {list(TimeNormalizer.PRODUCT_TO_SOURCE.keys())}"
            )

        # Route to appropriate normalization function
        if product == "analysis_assim":
            return TimeNormalizer.normalize_analysis_assim(df, reference_time)

        elif product == "short_range":
            if forecast_hour is None:
                raise ValueError("forecast_hour required for short_range product")
            return TimeNormalizer.normalize_short_range(df, reference_time, forecast_hour)

        elif product == "medium_range_blend":
            if forecast_hour is None:
                raise ValueError("forecast_hour required for medium_range_blend product")
            return TimeNormalizer.normalize_medium_range_blend(df, reference_time, forecast_hour)

        elif product == "analysis_assim_no_da":
            return TimeNormalizer.normalize_analysis_assim_no_da(df, reference_time)

        else:
            raise ValueError(f"Unhandled product: {product}")

    @staticmethod
    def records_to_dataframe(records: list[HydroRecord]) -> pd.DataFrame:
        """
        Convert list of HydroRecord objects to DataFrame for bulk insertion.

        Args:
            records: List of HydroRecord objects

        Returns:
            DataFrame ready for database insertion
        """
        if not records:
            return pd.DataFrame()

        # Convert to list of dicts
        data = [
            {
                'feature_id': r.feature_id,
                'valid_time': r.valid_time,
                'variable': r.variable.value if hasattr(r.variable, 'value') else r.variable,
                'value': r.value,
                'source': r.source.value if hasattr(r.source, 'value') else r.source,
                'forecast_hour': r.forecast_hour
            }
            for r in records
        ]

        return pd.DataFrame(data)


class TimeAbstraction:
    """
    Helper class for working with time abstractions.

    Provides utilities for mapping between NWM products and our internal concepts:
    - "now" = current conditions
    - "today" = next 18 hours
    - "outlook" = 3-10 days
    """

    @staticmethod
    def get_now_source() -> NWMSource:
        """Get the canonical source for 'now' (current conditions)"""
        return NWMSource.ANALYSIS_ASSIM

    @staticmethod
    def get_today_source() -> NWMSource:
        """Get the canonical source for 'today' (next 18 hours)"""
        return NWMSource.SHORT_RANGE

    @staticmethod
    def get_outlook_source() -> NWMSource:
        """Get the canonical source for 'outlook' (3-10 days)"""
        return NWMSource.MEDIUM_BLEND

    @staticmethod
    def classify_timeframe(forecast_hour: Optional[int]) -> str:
        """
        Classify a forecast hour into a timeframe abstraction.

        Args:
            forecast_hour: Forecast hour (None for analysis)

        Returns:
            'now', 'today', or 'outlook'
        """
        if forecast_hour is None or forecast_hour == 0:
            return "now"
        elif 1 <= forecast_hour <= 18:
            return "today"
        else:
            return "outlook"

    @staticmethod
    def get_valid_time_range_for_now(reference_time: datetime) -> tuple[datetime, datetime]:
        """
        Get the valid_time range for querying 'now' data.

        Args:
            reference_time: Current time

        Returns:
            Tuple of (start_time, end_time) for query
        """
        # For 'now', we want the most recent analysis
        # Allow some flexibility for data delays
        end_time = reference_time
        start_time = end_time - timedelta(hours=2)
        return start_time, end_time

    @staticmethod
    def get_valid_time_range_for_today(reference_time: datetime) -> tuple[datetime, datetime]:
        """
        Get the valid_time range for querying 'today' forecast data.

        Args:
            reference_time: Current time

        Returns:
            Tuple of (start_time, end_time) for query
        """
        start_time = reference_time
        end_time = reference_time + timedelta(hours=18)
        return start_time, end_time

    @staticmethod
    def get_valid_time_range_for_outlook(reference_time: datetime) -> tuple[datetime, datetime]:
        """
        Get the valid_time range for querying 'outlook' forecast data.

        Args:
            reference_time: Current time

        Returns:
            Tuple of (start_time, end_time) for query
        """
        start_time = reference_time + timedelta(days=3)
        end_time = reference_time + timedelta(days=10)
        return start_time, end_time


def main():
    """
    Example usage and testing
    """
    logging.basicConfig(level=logging.INFO)

    logger.info("=" * 60)
    logger.info("Testing Time Normalization")
    logger.info("=" * 60)

    # Create sample data
    sample_df = pd.DataFrame({
        'feature_id': [101, 102, 103],
        'streamflow_m3s': [10.5, 25.3, 5.2],
        'velocity_ms': [0.5, 0.8, 0.3],
        'qSfcLatRunoff_m3s': [1.0, 2.0, 0.5],
        'qBucket_m3s': [3.0, 5.0, 2.0],
        'qBtmVertRunoff_m3s': [6.5, 18.3, 2.7],
    })

    reference_time = datetime(2026, 1, 2, 12, 0, 0, tzinfo=timezone.utc)

    # Test 1: Normalize analysis_assim
    logger.info("\nTest 1: Normalizing analysis_assim")
    records = TimeNormalizer.normalize_analysis_assim(sample_df, reference_time)
    logger.info(f"✅ Created {len(records)} records")
    logger.info(f"   Sample: {records[0]}")

    # Test 2: Normalize short_range
    logger.info("\nTest 2: Normalizing short_range f006")
    records = TimeNormalizer.normalize_short_range(sample_df, reference_time, forecast_hour=6)
    logger.info(f"✅ Created {len(records)} records")
    expected_valid_time = reference_time + timedelta(hours=6)
    logger.info(f"   Valid time: {records[0].valid_time} (expected: {expected_valid_time})")

    # Test 3: Convert records to DataFrame
    logger.info("\nTest 3: Converting records to DataFrame")
    df = TimeNormalizer.records_to_dataframe(records)
    logger.info(f"✅ Created DataFrame with {len(df)} rows")
    logger.info(f"\n{df.head()}")

    # Test 4: Time abstractions
    logger.info("\nTest 4: Time abstractions")
    logger.info(f"   'now' source: {TimeAbstraction.get_now_source()}")
    logger.info(f"   'today' source: {TimeAbstraction.get_today_source()}")
    logger.info(f"   'outlook' source: {TimeAbstraction.get_outlook_source()}")
    logger.info(f"   Classify f000: {TimeAbstraction.classify_timeframe(0)}")
    logger.info(f"   Classify f006: {TimeAbstraction.classify_timeframe(6)}")
    logger.info(f"   Classify f072: {TimeAbstraction.classify_timeframe(72)}")

    logger.info("\n✅ All time normalization tests passed!")


if __name__ == "__main__":
    main()
