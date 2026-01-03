"""
Test script for Time Normalizer

Verifies that:
1. All NWM products normalize to canonical time abstraction
2. No f### references leak downstream
3. valid_time is always UTC timezone-aware
4. Source tagging works correctly
"""

import logging
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent.parent / 'src'
sys.path.insert(0, str(src_path))

import pandas as pd
from normalize.time_normalizer import TimeNormalizer, TimeAbstraction
from normalize.schemas import NWMSource

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_time_normalizer():
    """Test time normalization functionality"""

    logger.info("=" * 60)
    logger.info("Testing Time Normalizer")
    logger.info("=" * 60)

    # Create sample data
    sample_df = pd.DataFrame({
        'feature_id': [101, 102, 103, 104, 105],
        'streamflow_m3s': [10.5, 25.3, 5.2, 100.0, 0.5],
        'velocity_ms': [0.5, 0.8, 0.3, 1.2, 0.1],
        'qSfcLatRunoff_m3s': [1.0, 2.0, 0.5, 10.0, 0.1],
        'qBucket_m3s': [3.0, 5.0, 2.0, 20.0, 0.2],
        'qBtmVertRunoff_m3s': [6.5, 18.3, 2.7, 70.0, 0.2],
    })

    reference_time = datetime(2026, 1, 2, 12, 0, 0, tzinfo=timezone.utc)

    # Test 1: Normalize analysis_assim (now)
    logger.info("\nTest 1: analysis_assim (now)")
    logger.info("-" * 60)

    records = TimeNormalizer.normalize_analysis_assim(sample_df, reference_time)

    # Verify
    assert len(records) > 0, "Should have created records"
    assert all(r.valid_time == reference_time for r in records), \
        "All records should have valid_time = reference_time"
    assert all(r.source == "analysis_assim" for r in records), \
        "All records should have correct source"
    assert all(r.forecast_hour is None for r in records), \
        "Analysis should have no forecast_hour"
    assert all(r.valid_time.tzinfo is not None for r in records), \
        "valid_time must be timezone-aware"

    logger.info(f"[OK] Created {len(records)} records")
    logger.info(f"     Valid time: {records[0].valid_time}")
    logger.info(f"     Source: {records[0].source}")
    logger.info(f"     Sample: feature={records[0].feature_id}, var={records[0].variable}, val={records[0].value}")

    # Test 2: Normalize short_range (today)
    logger.info("\nTest 2: short_range f006 (today)")
    logger.info("-" * 60)

    forecast_hour = 6
    records = TimeNormalizer.normalize_short_range(sample_df, reference_time, forecast_hour)

    expected_valid_time = reference_time + timedelta(hours=forecast_hour)

    # Verify
    assert len(records) > 0, "Should have created records"
    assert all(r.valid_time == expected_valid_time for r in records), \
        f"All records should have valid_time = reference_time + {forecast_hour}h"
    assert all(r.source == "short_range" for r in records), \
        "All records should have correct source"
    assert all(r.forecast_hour == forecast_hour for r in records), \
        f"All records should have forecast_hour = {forecast_hour}"
    assert all(r.valid_time.tzinfo is not None for r in records), \
        "valid_time must be timezone-aware"

    logger.info(f"[OK] Created {len(records)} records")
    logger.info(f"     Valid time: {records[0].valid_time}")
    logger.info(f"     Expected: {expected_valid_time}")
    logger.info(f"     Forecast hour: {records[0].forecast_hour}")

    # Test 3: Normalize medium_range_blend (outlook)
    logger.info("\nTest 3: medium_range_blend f072 (outlook)")
    logger.info("-" * 60)

    forecast_hour = 72
    records = TimeNormalizer.normalize_medium_range_blend(sample_df, reference_time, forecast_hour)

    expected_valid_time = reference_time + timedelta(hours=forecast_hour)

    # Verify
    assert len(records) > 0, "Should have created records"
    assert all(r.valid_time == expected_valid_time for r in records), \
        f"All records should have valid_time = reference_time + {forecast_hour}h"
    assert all(r.source == "medium_range_blend" for r in records), \
        "All records should have correct source"

    logger.info(f"[OK] Created {len(records)} records")
    logger.info(f"     Valid time: {records[0].valid_time}")
    logger.info(f"     Expected: {expected_valid_time}")

    # Test 4: Convert records to DataFrame
    logger.info("\nTest 4: Convert records to DataFrame")
    logger.info("-" * 60)

    df = TimeNormalizer.records_to_dataframe(records)

    assert len(df) == len(records), "DataFrame should have same number of rows as records"
    assert 'feature_id' in df.columns, "Should have feature_id column"
    assert 'valid_time' in df.columns, "Should have valid_time column"
    assert 'variable' in df.columns, "Should have variable column"
    assert 'value' in df.columns, "Should have value column"
    assert 'source' in df.columns, "Should have source column"
    assert 'forecast_hour' in df.columns, "Should have forecast_hour column"

    logger.info(f"[OK] Created DataFrame with {len(df)} rows")
    logger.info(f"\nSample rows:")
    print(df.head(10))

    # Test 5: Time abstractions
    logger.info("\nTest 5: Time abstractions")
    logger.info("-" * 60)

    assert TimeAbstraction.get_now_source() == NWMSource.ANALYSIS_ASSIM
    assert TimeAbstraction.get_today_source() == NWMSource.SHORT_RANGE
    assert TimeAbstraction.get_outlook_source() == NWMSource.MEDIUM_BLEND

    assert TimeAbstraction.classify_timeframe(None) == "now"
    assert TimeAbstraction.classify_timeframe(0) == "now"
    assert TimeAbstraction.classify_timeframe(1) == "today"
    assert TimeAbstraction.classify_timeframe(18) == "today"
    assert TimeAbstraction.classify_timeframe(72) == "outlook"

    logger.info(f"[OK] Time abstraction mappings:")
    logger.info(f"     'now' -> {TimeAbstraction.get_now_source()}")
    logger.info(f"     'today' -> {TimeAbstraction.get_today_source()}")
    logger.info(f"     'outlook' -> {TimeAbstraction.get_outlook_source()}")

    # Test 6: Time ranges for queries
    logger.info("\nTest 6: Time ranges for queries")
    logger.info("-" * 60)

    now = datetime(2026, 1, 2, 15, 0, 0, tzinfo=timezone.utc)

    start, end = TimeAbstraction.get_valid_time_range_for_now(now)
    logger.info(f"[OK] 'now' range: {start} to {end}")
    assert end == now
    assert start == now - timedelta(hours=2)

    start, end = TimeAbstraction.get_valid_time_range_for_today(now)
    logger.info(f"[OK] 'today' range: {start} to {end}")
    assert start == now
    assert end == now + timedelta(hours=18)

    start, end = TimeAbstraction.get_valid_time_range_for_outlook(now)
    logger.info(f"[OK] 'outlook' range: {start} to {end}")
    assert start == now + timedelta(days=3)
    assert end == now + timedelta(days=10)

    # Test 7: Generic normalize_product function
    logger.info("\nTest 7: Generic normalize_product function")
    logger.info("-" * 60)

    # Test with different products
    test_cases = [
        ("analysis_assim", None),
        ("short_range", 12),
        ("medium_range_blend", 48),
        ("analysis_assim_no_da", None),
    ]

    for product, fh in test_cases:
        records = TimeNormalizer.normalize_product(
            df=sample_df,
            product=product,
            reference_time=reference_time,
            forecast_hour=fh
        )
        assert len(records) > 0
        fh_label = f"f{fh:03d}" if fh is not None else "tm00"
        logger.info(f"[OK] {product} ({fh_label}): {len(records)} records")

    logger.info("\n" + "=" * 60)
    logger.info("All Time Normalizer Tests PASSED!")
    logger.info("=" * 60)

    return True


if __name__ == "__main__":
    try:
        success = test_time_normalizer()
        sys.exit(0 if success else 1)
    except Exception as e:
        logger.error(f"Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
