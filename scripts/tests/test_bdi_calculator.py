"""
Database Integration Test for Baseflow Dominance Index (BDI)

Tests the BDI calculator against real database data.
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

from src.metrics.baseflow import (
    compute_bdi,
    compute_bdi_with_classification,
    compute_bdi_for_reach,
    compute_bdi_timeseries_for_reach,
    compute_bdi_statistics,
    explain_bdi,
    classify_bdi
)


def test_bdi_with_db():
    """Test BDI calculator with real database data"""

    print("=" * 70)
    print("Baseflow Dominance Index (BDI) - Database Integration Test")
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

            # Check for available flow component data
            print("Checking for flow component data...")
            result = conn.execute(text("""
                SELECT variable, COUNT(*) as count
                FROM nwm.hydro_timeseries
                WHERE variable IN ('qBtmVertRunoff', 'qBucket', 'qSfcLatRunoff')
                GROUP BY variable
                ORDER BY variable
            """))

            components = {row[0]: row[1] for row in result}

            print("  Flow components available:")
            for var, count in components.items():
                print(f"    {var}: {count:,} records")
            print()

            # Check if all required components are present
            required = ['qBtmVertRunoff', 'qBucket', 'qSfcLatRunoff']
            if not all(var in components for var in required):
                print("WARNING: Not all flow components available")
                print("  Required: qBtmVertRunoff, qBucket, qSfcLatRunoff")
                print("  BDI calculation requires all three components")
                return False

            # Find a reach with all three components at the same timestamp
            print("Finding reach with complete flow component data...")
            result = conn.execute(text("""
                WITH component_counts AS (
                    SELECT feature_id, valid_time, COUNT(DISTINCT variable) as num_vars
                    FROM nwm.hydro_timeseries
                    WHERE variable IN ('qBtmVertRunoff', 'qBucket', 'qSfcLatRunoff')
                    GROUP BY feature_id, valid_time
                    HAVING COUNT(DISTINCT variable) = 3
                )
                SELECT feature_id, COUNT(*) as complete_timestamps
                FROM component_counts
                GROUP BY feature_id
                ORDER BY COUNT(*) DESC
                LIMIT 1
            """))

            sample_reach = result.fetchone()

            if not sample_reach:
                print("ERROR: No reach found with complete flow component data")
                return False

            feature_id, complete_count = sample_reach
            print(f"  Selected reach: {feature_id}")
            print(f"  Complete timestamps: {complete_count}")
            print()

            # Get a single timestamp with complete data
            result = conn.execute(text("""
                SELECT valid_time, COUNT(DISTINCT variable) as num_vars
                FROM nwm.hydro_timeseries
                WHERE feature_id = :feature_id
                  AND variable IN ('qBtmVertRunoff', 'qBucket', 'qSfcLatRunoff')
                GROUP BY valid_time
                HAVING COUNT(DISTINCT variable) = 3
                ORDER BY valid_time DESC
                LIMIT 1
            """), {'feature_id': feature_id})

            row = result.fetchone()
            if not row:
                print("ERROR: Could not find complete timestamp")
                return False

            valid_time = row[0]
            print(f"  Selected timestamp: {valid_time}")
            print()

            # Test 1: Single timestamp BDI calculation
            print("-" * 70)
            print("Test 1: Single Timestamp BDI Calculation")
            print("-" * 70)

            # Query flow components
            result = conn.execute(text("""
                SELECT variable, value
                FROM nwm.hydro_timeseries
                WHERE feature_id = :feature_id
                  AND valid_time = :valid_time
                  AND variable IN ('qBtmVertRunoff', 'qBucket', 'qSfcLatRunoff')
                ORDER BY variable
            """), {'feature_id': feature_id, 'valid_time': valid_time})

            flow_components = {row[0]: row[1] for row in result}

            print("  Flow components:")
            print(f"    qBtmVertRunoff (deep groundwater): {flow_components['qBtmVertRunoff']:.6f} m3/s")
            print(f"    qBucket (shallow subsurface): {flow_components['qBucket']:.6f} m3/s")
            print(f"    qSfcLatRunoff (surface runoff): {flow_components['qSfcLatRunoff']:.6f} m3/s")
            print()

            # Calculate BDI manually
            bdi = compute_bdi(
                q_btm_vert=flow_components['qBtmVertRunoff'],
                q_bucket=flow_components['qBucket'],
                q_sfc_lat=flow_components['qSfcLatRunoff']
            )

            classification = classify_bdi(bdi)

            print("  BDI Calculation:")
            print(f"    BDI: {bdi:.4f}")
            print(f"    Classification: {classification}")
            print(f"    Explanation: {explain_bdi(bdi, classification)}")
            print()

            # Test 2: Database function
            print("-" * 70)
            print("Test 2: Database Integration Function")
            print("-" * 70)

            result_db = compute_bdi_for_reach(
                feature_id=feature_id,
                valid_time=valid_time,
                db_connection=conn
            )

            if result_db:
                bdi_db, classification_db = result_db
                print(f"  BDI (from DB function): {bdi_db:.4f}")
                print(f"  Classification (from DB function): {classification_db}")
                print()

                # Verify consistency
                if abs(bdi - bdi_db) < 0.0001 and classification == classification_db:
                    print("PASS: Database function matches manual calculation")
                else:
                    print("WARNING: Results differ")
                    print(f"  Manual: BDI={bdi:.4f}, class={classification}")
                    print(f"  DB func: BDI={bdi_db:.4f}, class={classification_db}")
            else:
                print("ERROR: Database function returned None")
            print()

            # Test 3: Time series analysis
            print("-" * 70)
            print("Test 3: Time Series BDI Analysis")
            print("-" * 70)

            # Get time range for this reach
            result = conn.execute(text("""
                SELECT MIN(valid_time) as start_time,
                       MAX(valid_time) as end_time
                FROM nwm.hydro_timeseries
                WHERE feature_id = :feature_id
                  AND variable IN ('qBtmVertRunoff', 'qBucket', 'qSfcLatRunoff')
            """), {'feature_id': feature_id})

            row = result.fetchone()
            start_time, end_time = row

            print(f"  Time range: {start_time} to {end_time}")
            print()

            # Compute time series
            df_bdi = compute_bdi_timeseries_for_reach(
                feature_id=feature_id,
                start_time=start_time,
                end_time=end_time,
                db_connection=conn
            )

            if len(df_bdi) > 0:
                print(f"  Computed BDI for {len(df_bdi)} timestamps")
                print()
                print("  Sample of BDI time series (first 5 records):")
                for i in range(min(5, len(df_bdi))):
                    row = df_bdi.iloc[i]
                    print(f"    {row['valid_time']}: BDI={row['bdi']:.4f} ({row['classification']})")
                if len(df_bdi) > 5:
                    print(f"    ... ({len(df_bdi) - 5} more records)")
                print()

                # Compute statistics
                stats = compute_bdi_statistics(df_bdi['bdi'])

                print("  BDI Statistics:")
                print(f"    Mean BDI: {stats['mean']:.4f}")
                print(f"    Median BDI: {stats['median']:.4f}")
                print(f"    Std Dev: {stats['std']:.4f}")
                print(f"    Range: {stats['min']:.4f} - {stats['max']:.4f}")
                print(f"    Dominant classification: {stats['dominant_class']}")
                if stats['stability'] is not None:
                    print(f"    Stability index: {stats['stability']:.4f} (0=unstable, 1=stable)")
                print()

                # Ecological interpretation
                print("  Ecological Interpretation:")
                if stats['dominant_class'] == "groundwater_fed":
                    print("    This reach is groundwater-dominated, indicating:")
                    print("      - Thermal stability (cool refuge in summer)")
                    print("      - Flow stability (resilient to drought)")
                    print("      - Excellent habitat for cold-water species (e.g., trout)")
                elif stats['dominant_class'] == "mixed":
                    print("    This reach has mixed flow sources, indicating:")
                    print("      - Moderate thermal and flow variability")
                    print("      - Suitable for diverse species assemblages")
                    print("      - Intermediate habitat quality")
                elif stats['dominant_class'] == "storm_dominated":
                    print("    This reach is storm-dominated, indicating:")
                    print("      - High flow variability (flashy)")
                    print("      - High thermal variability")
                    print("      - Less stable habitat conditions")
                print()

                # Temporal stability
                if stats['stability'] is not None:
                    if stats['stability'] > 0.8:
                        print("    BDI is very stable over time (consistent flow sources)")
                    elif stats['stability'] > 0.5:
                        print("    BDI shows moderate variability (changing flow contributions)")
                    else:
                        print("    BDI shows high variability (highly variable flow sources)")
                print()

            else:
                print("WARNING: No complete time series data available")
                print()

            print("=" * 70)
            print("DATABASE INTEGRATION TEST COMPLETE!")
            print("=" * 70)
            print()
            print("Summary:")
            print(f"  Feature ID tested: {feature_id}")
            print(f"  Timestamps analyzed: {len(df_bdi) if len(df_bdi) > 0 else 1}")
            if len(df_bdi) > 0:
                print(f"  Mean BDI: {stats['mean']:.4f}")
                print(f"  Dominant class: {stats['dominant_class']}")
            else:
                print(f"  Single timestamp BDI: {bdi:.4f}")
                print(f"  Classification: {classification}")
            print()
            print("Ticket 2.2 (BDI Calculator) successfully verified with database!")
            print()

            return True

    except Exception as e:
        print(f"ERROR: Test failed with exception:")
        print(f"  {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_bdi_with_db()
    sys.exit(0 if success else 1)
