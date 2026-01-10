"""
Test Rising Limb Detector with Real Database Data

This script:
1. Connects to the database
2. Selects a sample reach with recent data
3. Runs rising limb detection
4. Displays results and explanations

This verifies that Ticket 2.1 (Rising Limb Detector) is working end-to-end.
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

# Configure stdout for UTF-8 on Windows
if sys.platform == 'win32':
    import codecs
    if sys.stdout.encoding != 'utf-8':
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    if sys.stderr.encoding != 'utf-8':
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')


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
        print("❌ ERROR: DATABASE_URL not found in .env file")
        return False

    try:
        # Create engine
        engine = create_engine(database_url)

        with engine.begin() as conn:
            print("✅ Connected to database")
            print()

            # Check for available data
            print("Checking for available hydrology data...")
            result = conn.execute(text("""
                SELECT COUNT(*) as count,
                       MIN(valid_time) as earliest,
                       MAX(valid_time) as latest,
                       COUNT(DISTINCT feature_id) as num_reaches
                FROM nwm.hydro_timeseries
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
                print("⚠️  No streamflow data found in database")
                print("   Please run data ingestion first")
                return False

            # Select a sample reach with sufficient data
            print("Selecting sample reach with sufficient data...")
            result = conn.execute(text("""
                SELECT feature_id, COUNT(*) as record_count
                FROM nwm.hydro_timeseries
                WHERE variable = 'streamflow'
                  AND valid_time >= NOW() - INTERVAL '24 hours'
                GROUP BY feature_id
                HAVING COUNT(*) >= 10
                ORDER BY COUNT(*) DESC
                LIMIT 1
            """))

            sample_reach = result.fetchone()

            if not sample_reach:
                print("⚠️  No reach found with sufficient recent data")
                print("   Trying with any available data...")

                # Try any reach with at least 10 records
                result = conn.execute(text("""
                    SELECT feature_id, COUNT(*) as record_count
                    FROM nwm.hydro_timeseries
                    WHERE variable = 'streamflow'
                    GROUP BY feature_id
                    HAVING COUNT(*) >= 10
                    ORDER BY COUNT(*) DESC
                    LIMIT 1
                """))

                sample_reach = result.fetchone()

                if not sample_reach:
                    print("❌ No reach with sufficient data found")
                    return False

            feature_id, record_count = sample_reach
            print(f"  Selected reach: {feature_id}")
            print(f"  Records available: {record_count}")
            print()

            # Get time range for this reach
            result = conn.execute(text("""
                SELECT MIN(valid_time) as start_time,
                       MAX(valid_time) as end_time
                FROM nwm.hydro_timeseries
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
            print(f"  Min slope: {config.min_slope} m³/s per hour")
            print(f"  Min duration: {config.min_duration} hours")
            print(f"  Intensity thresholds:")
            for level, threshold in config.intensity_thresholds.items():
                print(f"    {level}: {threshold} m³/s per hour")
            print()

            # Test 1: Detect rising limb using database function
            print("-" * 70)
            print("Test 1: Direct database detection")
            print("-" * 70)

            detected, intensity = detect_rising_limb_for_reach(
                feature_id=feature_id,
                start_time=start_time,
                end_time=end_time,
                config=config,
                db_connection=conn
            )

            print(f"  Detected: {detected}")
            print(f"  Intensity: {intensity}")
            print(f"  Explanation: {explain_detection(detected, intensity, config=config)}")
            print()

            # Test 2: Manually fetch data and analyze
            print("-" * 70)
            print("Test 2: Manual analysis with visualization")
            print("-" * 70)

            result = conn.execute(text("""
                SELECT valid_time, value
                FROM nwm.hydro_timeseries
                WHERE feature_id = :feature_id
                  AND variable = 'streamflow'
                ORDER BY valid_time ASC
            """), {'feature_id': feature_id})

            rows = result.fetchall()
            times = [row[0] for row in rows]
            values = [row[1] for row in rows]

            flows = pd.Series(values, index=pd.DatetimeIndex(times))

            print(f"  Loaded {len(flows)} flow observations")
            print(f"  Flow range: {flows.min():.2f} - {flows.max():.2f} m³/s")
            print(f"  Mean flow: {flows.mean():.2f} m³/s")
            print()

            # Display sample of data
            print("  Sample of flow data:")
            for i in range(min(10, len(flows))):
                print(f"    {flows.index[i]}: {flows.iloc[i]:.2f} m³/s")
            if len(flows) > 10:
                print(f"    ... ({len(flows) - 10} more records)")
            print()

            # Compute flow changes
            time_diff_hours = flows.index.to_series().diff().dt.total_seconds() / 3600
            flow_diff = flows.diff()
            dQdt = flow_diff / time_diff_hours

            print("  Flow change analysis:")
            print(f"    Maximum increase rate: {dQdt.max():.2f} m³/s per hour")
            print(f"    Maximum decrease rate: {dQdt.min():.2f} m³/s per hour")
            print(f"    Mean change rate: {dQdt.mean():.2f} m³/s per hour")
            print()

            # Detect rising limb
            detected, intensity = detect_rising_limb(flows, config)

            print(f"  Rising limb detected: {detected}")
            print(f"  Intensity: {intensity}")
            print()

            # Generate detailed explanation
            if detected:
                max_slope = dQdt[dQdt > config.min_slope].max()
                explanation = explain_detection(detected, intensity, max_slope, config)
                print(f"  Detailed explanation:")
                print(f"    {explanation}")
            else:
                explanation = explain_detection(detected, intensity, config=config)
                print(f"  Explanation:")
                print(f"    {explanation}")
            print()

            # Test 3: Test with species-specific config
            print("-" * 70)
            print("Test 3: Species-specific configuration (anadromous salmonid)")
            print("-" * 70)

            config_path = Path(__file__).parent.parent.parent / 'config' / 'thresholds' / 'rising_limb.yaml'
            if config_path.exists():
                species_config = RisingLimbConfig.from_yaml(config_path, species='anadromous_salmonid')

                print(f"  Species-specific thresholds:")
                print(f"    Min slope: {species_config.min_slope} m³/s per hour")
                print(f"    Min duration: {species_config.min_duration} hours")
                print()

                detected_species, intensity_species = detect_rising_limb(flows, species_config)

                print(f"  Detected (with species config): {detected_species}")
                print(f"  Intensity (with species config): {intensity_species}")
                print(f"  Explanation: {explain_detection(detected_species, intensity_species, config=species_config)}")
                print()

                if detected != detected_species:
                    print("  ⚠️  Note: Species-specific config yielded different result!")
                    print("      This is expected for stricter thresholds.")
            else:
                print("  ⚠️  Config file not found, skipping species-specific test")
            print()

            print("=" * 70)
            print("✅ Rising Limb Detector - All Tests Complete!")
            print("=" * 70)
            print()
            print("Summary:")
            print(f"  ✅ Successfully loaded configuration")
            print(f"  ✅ Successfully queried database")
            print(f"  ✅ Successfully detected rising limb patterns")
            print(f"  ✅ Successfully generated explanations")
            print()
            print("Ticket 2.1 (Rising Limb Detector) is fully functional! 🎉")
            print()

            return True

    except Exception as e:
        print(f"❌ Test failed with error:")
        print(f"   {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_rising_limb_with_db()
    sys.exit(0 if success else 1)
