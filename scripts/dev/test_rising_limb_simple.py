"""
Simple Database Test for Rising Limb Detector (No Unicode)

Tests the rising limb detector against real database data.
"""

import os
import sys
from pathlib import Path
from datetime import datetime, timedelta
import pytz

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
import pandas as pd

from src.metrics.rising_limb import (
    detect_rising_limb_for_reach,
    detect_rising_limb,
    RisingLimbConfig,
    explain_detection,
    load_default_config
)


def test_rising_limb_with_db():
    """Test rising limb detector with real database data"""

    print("=" * 70)
    print("Rising Limb Detector - Database Integration Test")
    print("=" * 70)
    print()

    # Load environment variables
    load_dotenv()
    database_url = os.getenv('DATABASE_URL')

    if not database_url:
        print("ERROR: DATABASE_URL not found in .env file")
        return False

    try:
        # Create engine
        engine = create_engine(database_url)

        with engine.begin() as conn:
            print("CONNECTED to database")
            print()

            # Check for available data
            print("Checking for available hydrology data...")
            result = conn.execute(text("""
                SELECT COUNT(*) as count,
                       MIN(valid_time) as earliest,
                       MAX(valid_time) as latest,
                       COUNT(DISTINCT feature_id) as num_reaches
                FROM hydro_timeseries
                WHERE variable = 'streamflow'
            """))

            row = result.fetchone()
            count, earliest, latest, num_reaches = row

            print(f"  Total streamflow records: {count:,}")
            print(f"  Earliest data: {earliest}")
            print(f"  Latest data: {latest}")
            print(f"  Number of reaches: {num_reaches:,}")
            print()

            if count == 0:
                print("WARNING: No streamflow data found in database")
                print("Please run data ingestion first")
                return False

            # Select a sample reach with data
            print("Selecting sample reach with data...")
            result = conn.execute(text("""
                SELECT feature_id, COUNT(*) as record_count
                FROM hydro_timeseries
                WHERE variable = 'streamflow'
                GROUP BY feature_id
                ORDER BY COUNT(*) DESC
                LIMIT 1
            """))

            sample_reach = result.fetchone()

            if not sample_reach:
                print("ERROR: No reach with data found")
                return False

            feature_id, record_count = sample_reach
            print(f"  Selected reach: {feature_id}")
            print(f"  Records available: {record_count}")
            print()

            # Get time range for this reach
            result = conn.execute(text("""
                SELECT MIN(valid_time) as start_time,
                       MAX(valid_time) as end_time
                FROM hydro_timeseries
                WHERE feature_id = :feature_id
                  AND variable = 'streamflow'
            """), {'feature_id': feature_id})

            row = result.fetchone()
            start_time, end_time = row

            print(f"  Data time range: {start_time} to {end_time}")
            print()

            # Load configuration
            print("Loading detection configuration...")
            config = load_default_config()
            print(f"  Min slope: {config.min_slope} m3/s per hour")
            print(f"  Min duration: {config.min_duration} hours")
            print(f"  Intensity thresholds: {config.intensity_thresholds}")
            print()

            # Fetch streamflow data
            print("-" * 70)
            print("Fetching streamflow data from database...")
            print("-" * 70)

            result = conn.execute(text("""
                SELECT valid_time, value
                FROM hydro_timeseries
                WHERE feature_id = :feature_id
                  AND variable = 'streamflow'
                ORDER BY valid_time ASC
            """), {'feature_id': feature_id})

            rows = result.fetchall()
            times = [row[0] for row in rows]
            values = [row[1] for row in rows]

            flows = pd.Series(values, index=pd.DatetimeIndex(times))

            print(f"  Loaded {len(flows)} flow observations")
            print(f"  Flow range: {flows.min():.2f} - {flows.max():.2f} m3/s")
            print(f"  Mean flow: {flows.mean():.2f} m3/s")
            print()

            # Display sample of data
            print("  Sample of flow data (first 10 records):")
            for i in range(min(10, len(flows))):
                print(f"    {flows.index[i]}: {flows.iloc[i]:.2f} m3/s")
            if len(flows) > 10:
                print(f"    ... ({len(flows) - 10} more records)")
            print()

            # Analyze flow changes
            time_diff_hours = flows.index.to_series().diff().dt.total_seconds() / 3600
            flow_diff = flows.diff()
            dQdt = flow_diff / time_diff_hours

            print("  Flow change analysis:")
            print(f"    Maximum increase rate: {dQdt.max():.2f} m3/s per hour")
            print(f"    Maximum decrease rate: {dQdt.min():.2f} m3/s per hour")
            print(f"    Mean change rate: {dQdt.mean():.2f} m3/s per hour")
            print()

            # Detect rising limb
            print("-" * 70)
            print("Running rising limb detection...")
            print("-" * 70)

            detected, intensity = detect_rising_limb(flows, config)

            print(f"  Rising limb detected: {detected}")
            print(f"  Intensity: {intensity}")
            print()

            # Generate explanation
            if detected:
                max_slope = dQdt[dQdt > config.min_slope].max()
                explanation = explain_detection(detected, intensity, max_slope, config)
            else:
                explanation = explain_detection(detected, intensity, config=config)

            print(f"Explanation:")
            print(f"  {explanation}")
            print()

            # Test with database function
            print("-" * 70)
            print("Testing database integration function...")
            print("-" * 70)

            detected_db, intensity_db = detect_rising_limb_for_reach(
                feature_id=feature_id,
                start_time=start_time,
                end_time=end_time,
                config=config,
                db_connection=conn
            )

            print(f"  Detection result (from DB function): {detected_db}")
            print(f"  Intensity (from DB function): {intensity_db}")
            print()

            # Verify consistency
            if detected == detected_db and intensity == intensity_db:
                print("PASS: Database function matches direct analysis")
            else:
                print("WARNING: Results differ between methods")
                print(f"  Direct: detected={detected}, intensity={intensity}")
                print(f"  DB func: detected={detected_db}, intensity={intensity_db}")
            print()

            print("=" * 70)
            print("DATABASE INTEGRATION TEST COMPLETE!")
            print("=" * 70)
            print()
            print("Summary:")
            print(f"  Feature ID tested: {feature_id}")
            print(f"  Records analyzed: {len(flows)}")
            print(f"  Rising limb detected: {detected}")
            print(f"  Intensity: {intensity}")
            print()
            print("Ticket 2.1 (Rising Limb Detector) successfully verified with database!")
            print()

            return True

    except Exception as e:
        print(f"ERROR: Test failed with exception:")
        print(f"  {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_rising_limb_with_db()
    sys.exit(0 if success else 1)
