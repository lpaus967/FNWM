"""
Test Flow Percentile Calculations

Validates that flow percentile calculations work correctly with real NHD data.
"""
import sys
from pathlib import Path
from datetime import datetime, timezone

# Add src to path
src_path = Path(__file__).parent.parent.parent / 'src'
sys.path.insert(0, str(src_path))

import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from metrics.flow_percentile import (
    compute_flow_percentile,
    classify_flow_percentile,
    compute_flow_percentile_for_reach,
    get_monthly_mean_flow
)

load_dotenv()

print("=" * 80)
print("TESTING FLOW PERCENTILE CALCULATIONS")
print("=" * 80)

# Test 1: Basic percentile calculation
print("\n" + "-" * 80)
print("TEST 1: Basic Percentile Calculation")
print("-" * 80)

test_cases = [
    (1.5, 1.5, "At mean (should be ~50th percentile)"),
    (3.0, 1.5, "2x mean (should be ~86th percentile)"),
    (0.75, 1.5, "0.5x mean (should be ~14th percentile)"),
    (0.0, 1.5, "Zero flow (should be 0th percentile)"),
]

for current, mean, description in test_cases:
    percentile = compute_flow_percentile(current, mean)
    classification = classify_flow_percentile(percentile)
    print(f"{description}")
    print(f"  Current: {current:.2f} m³/s, Mean: {mean:.2f} m³/s")
    print(f"  Percentile: {percentile:.1f}% ({classification})")

# Test 2: Database query for monthly mean flows
print("\n" + "-" * 80)
print("TEST 2: Database Query for Monthly Mean Flows")
print("-" * 80)

try:
    engine = create_engine(os.getenv('DATABASE_URL'))

    # Get a sample feature_id with flow data
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT nhdplusid, qama
            FROM nhd.flow_statistics
            WHERE qama IS NOT NULL
            ORDER BY nhdplusid
            LIMIT 1
        """))
        row = result.fetchone()

        if row:
            test_feature_id = row[0]
            jan_mean = row[1]

            print(f"Sample Feature ID: {test_feature_id}")
            print(f"January Mean Flow (qama): {jan_mean:.4f} m³/s")

            # Test get_monthly_mean_flow function
            print("\nTesting get_monthly_mean_flow() for all 12 months:")
            for month in range(1, 13):
                mean_flow = get_monthly_mean_flow(test_feature_id, month)
                month_name = datetime(2026, month, 1).strftime("%B")
                if mean_flow is not None:
                    print(f"  {month_name:>9}: {mean_flow:.4f} m³/s")
                else:
                    print(f"  {month_name:>9}: No data")
        else:
            print("[ERROR] No flow statistics found in database")
            test_feature_id = None

except Exception as e:
    print(f"[ERROR] Database error: {e}")
    test_feature_id = None

# Test 3: Full percentile calculation for reach
if test_feature_id:
    print("\n" + "-" * 80)
    print("TEST 3: Full Percentile Calculation for Reach")
    print("-" * 80)

    # Get current flow data from nwm.hydro_timeseries
    try:
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT value, valid_time
                FROM nwm.hydro_timeseries
                WHERE feature_id = :feature_id
                  AND source = 'analysis_assim'
                  AND variable = 'streamflow'
                ORDER BY valid_time DESC
                LIMIT 1
            """), {'feature_id': test_feature_id})

            row = result.fetchone()

            if row:
                current_flow = row[0]
                timestamp = row[1]

                print(f"Feature ID: {test_feature_id}")
                print(f"Current Flow: {current_flow:.4f} m³/s")
                print(f"Timestamp: {timestamp}")

                # Compute percentile using the main API function
                result = compute_flow_percentile_for_reach(
                    feature_id=test_feature_id,
                    current_flow=current_flow,
                    timestamp=timestamp
                )

                print(f"\nResults:")
                print(f"  Percentile: {result.get('percentile', 'N/A'):.1f}%")
                print(f"  Classification: {result.get('classification', 'N/A')}")
                print(f"  Monthly Mean: {result.get('monthly_mean', 'N/A'):.4f} m³/s")
                print(f"  Ratio to Mean: {result.get('ratio_to_mean', 'N/A'):.1f}%")
                print(f"  Data Available: {result.get('data_available', False)}")
                print(f"  Explanation: {result.get('explanation', 'N/A')}")

                if result['data_available']:
                    print("\n[OK] Flow percentile calculation successful!")
                else:
                    print("\n[WARN] No historical data available for this month")
            else:
                print(f"[ERROR] No streamflow data found for feature {test_feature_id}")

    except Exception as e:
        print(f"[ERROR] Error during percentile calculation: {e}")

# Test 4: Check data coverage
print("\n" + "-" * 80)
print("TEST 4: Data Coverage Analysis")
print("-" * 80)

try:
    with engine.connect() as conn:
        # Count total reaches
        result = conn.execute(text("""
            SELECT COUNT(*) as total
            FROM nhd.flowlines
        """))
        total_reaches = result.fetchone()[0]

        # Count reaches with flow statistics
        result = conn.execute(text("""
            SELECT COUNT(*) as with_stats
            FROM nhd.flow_statistics
            WHERE qama IS NOT NULL OR qbma IS NOT NULL OR qcma IS NOT NULL
        """))
        with_stats = result.fetchone()[0]

        # Count reaches with NWM data
        result = conn.execute(text("""
            SELECT COUNT(DISTINCT feature_id) as with_nwm
            FROM nwm.hydro_timeseries
            WHERE variable = 'streamflow'
        """))
        with_nwm = result.fetchone()[0]

        # Count reaches with both NHD and NWM data
        result = conn.execute(text("""
            SELECT COUNT(DISTINCT h.feature_id) as with_both
            FROM nwm.hydro_timeseries h
            INNER JOIN nhd.flow_statistics nfs ON h.feature_id = nfs.nhdplusid
            WHERE h.variable = 'streamflow'
              AND nfs.qama IS NOT NULL
        """))
        with_both = result.fetchone()[0]

        print(f"Total NHD Reaches: {total_reaches:,}")
        print(f"Reaches with Flow Statistics: {with_stats:,} ({with_stats/total_reaches*100:.1f}%)")
        print(f"Reaches with NWM Data: {with_nwm:,}")
        print(f"Reaches with BOTH (can compute percentiles): {with_both:,}")

        if with_both > 0:
            print(f"\n[OK] Flow percentile system ready for {with_both:,} reaches!")
        else:
            print(f"\n[WARN] No reaches have both NHD statistics and NWM data yet")

except Exception as e:
    print(f"[ERROR] Coverage analysis error: {e}")

print("\n" + "=" * 80)
print("FLOW PERCENTILE TESTING COMPLETE")
print("=" * 80)
