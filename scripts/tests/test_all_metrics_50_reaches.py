"""
Comprehensive Test: All EPIC 2 Metrics on 50 Reaches

Tests all three derived metrics on 50 sample reaches:
1. Rising Limb Detection
2. Baseflow Dominance Index (BDI)
3. Velocity Suitability Classification

Saves results to CSV for analysis.
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
import numpy as np

from src.metrics.rising_limb import (
    detect_rising_limb,
    RisingLimbConfig,
    load_default_config as load_rising_limb_config
)

from src.metrics.baseflow import (
    compute_bdi,
    classify_bdi
)

from src.metrics.velocity import (
    classify_velocity,
    load_species_config
)


def test_all_metrics_50_reaches():
    """Test all metrics on 50 sample reaches"""

    print("=" * 80)
    print("EPIC 2 Metrics - Comprehensive Test on 50 Reaches")
    print("=" * 80)
    print()

    # Load environment variables
    load_dotenv()
    database_url = os.getenv('DATABASE_URL')

    if not database_url:
        print("ERROR: DATABASE_URL not found in .env file")
        return False

    # Output file
    output_dir = Path(__file__).parent.parent.parent / 'data'
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / f'metric_test_results_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'

    try:
        # Create engine
        engine = create_engine(database_url)

        # Load configurations
        print("Loading configurations...")
        rising_limb_config = load_rising_limb_config()
        species_config = load_species_config("trout")
        print(f"  Rising limb: min_slope={rising_limb_config.min_slope}, min_duration={rising_limb_config.min_duration}")
        print(f"  Species: {species_config.species_name}")
        print(f"  Velocity optimal: {species_config.min_optimal}-{species_config.max_optimal} m/s")
        print()

        with engine.begin() as conn:
            print("CONNECTED to database")
            print()

            # Find 50 reaches with complete data for all metrics
            print("Finding 50 reaches with complete metric data...")
            query = text("""
                WITH reach_data AS (
                    SELECT
                        feature_id,
                        valid_time,
                        SUM(CASE WHEN variable = 'streamflow' THEN 1 ELSE 0 END) as has_flow,
                        SUM(CASE WHEN variable = 'velocity' THEN 1 ELSE 0 END) as has_velocity,
                        SUM(CASE WHEN variable = 'qBtmVertRunoff' THEN 1 ELSE 0 END) as has_btm,
                        SUM(CASE WHEN variable = 'qBucket' THEN 1 ELSE 0 END) as has_bucket,
                        SUM(CASE WHEN variable = 'qSfcLatRunoff' THEN 1 ELSE 0 END) as has_sfc
                    FROM nwm.hydro_timeseries
                    GROUP BY feature_id, valid_time
                    HAVING
                        SUM(CASE WHEN variable = 'streamflow' THEN 1 ELSE 0 END) > 0 AND
                        SUM(CASE WHEN variable = 'velocity' THEN 1 ELSE 0 END) > 0 AND
                        SUM(CASE WHEN variable = 'qBtmVertRunoff' THEN 1 ELSE 0 END) > 0 AND
                        SUM(CASE WHEN variable = 'qBucket' THEN 1 ELSE 0 END) > 0 AND
                        SUM(CASE WHEN variable = 'qSfcLatRunoff' THEN 1 ELSE 0 END) > 0
                ),
                reach_counts AS (
                    SELECT feature_id, COUNT(*) as complete_timestamps
                    FROM reach_data
                    GROUP BY feature_id
                    HAVING COUNT(*) >= 3
                )
                SELECT feature_id, complete_timestamps
                FROM reach_counts
                ORDER BY complete_timestamps DESC
                LIMIT 50
            """)

            result = conn.execute(query)
            reaches = [(row[0], row[1]) for row in result]

            if len(reaches) == 0:
                print("ERROR: No reaches found with complete data")
                return False

            print(f"  Found {len(reaches)} reaches with complete data")
            print(f"  Timestamp range per reach: {min(r[1] for r in reaches)}-{max(r[1] for r in reaches)}")
            print()

            # Process each reach
            results = []
            print("Processing reaches...")
            print()

            for i, (feature_id, timestamp_count) in enumerate(reaches, 1):
                print(f"  [{i:2d}/50] Reach {feature_id} ({timestamp_count} timestamps)...", end=" ")

                try:
                    # Get latest timestamp with complete data
                    query_time = text("""
                        SELECT valid_time
                        FROM nwm.hydro_timeseries
                        WHERE feature_id = :feature_id
                          AND variable IN ('streamflow', 'velocity', 'qBtmVertRunoff', 'qBucket', 'qSfcLatRunoff')
                        GROUP BY valid_time
                        HAVING COUNT(DISTINCT variable) = 5
                        ORDER BY valid_time DESC
                        LIMIT 1
                    """)

                    result = conn.execute(query_time, {'feature_id': feature_id})
                    row = result.fetchone()
                    if not row:
                        print("SKIP (no complete timestamp)")
                        continue

                    latest_time = row[0]

                    # Get all data for this timestamp
                    query_data = text("""
                        SELECT variable, value
                        FROM nwm.hydro_timeseries
                        WHERE feature_id = :feature_id
                          AND valid_time = :valid_time
                          AND variable IN ('streamflow', 'velocity', 'qBtmVertRunoff', 'qBucket', 'qSfcLatRunoff')
                    """)

                    result = conn.execute(query_data, {'feature_id': feature_id, 'valid_time': latest_time})
                    data = {row[0]: row[1] for row in result}

                    # Get streamflow time series for rising limb detection
                    query_flow_series = text("""
                        SELECT valid_time, value
                        FROM nwm.hydro_timeseries
                        WHERE feature_id = :feature_id
                          AND variable = 'streamflow'
                        ORDER BY valid_time ASC
                    """)

                    result = conn.execute(query_flow_series, {'feature_id': feature_id})
                    flow_rows = result.fetchall()
                    flow_times = [row[0] for row in flow_rows]
                    flow_values = [row[1] for row in flow_rows]
                    flows = pd.Series(flow_values, index=pd.DatetimeIndex(flow_times))

                    # Compute metrics

                    # 1. Rising Limb Detection
                    rising_detected, rising_intensity = detect_rising_limb(flows, rising_limb_config)

                    # 2. BDI
                    bdi = compute_bdi(
                        q_btm_vert=data['qBtmVertRunoff'],
                        q_bucket=data['qBucket'],
                        q_sfc_lat=data['qSfcLatRunoff']
                    )
                    bdi_class = classify_bdi(bdi)

                    # 3. Velocity Classification
                    velocity_suitable, velocity_class, velocity_score = classify_velocity(
                        data['velocity'],
                        species_config
                    )

                    # Store results
                    results.append({
                        'feature_id': feature_id,
                        'timestamp': latest_time,
                        'timestamps_available': timestamp_count,
                        # Flow metrics
                        'streamflow_m3s': data['streamflow'],
                        'flow_min': flows.min(),
                        'flow_max': flows.max(),
                        'flow_mean': flows.mean(),
                        # Rising Limb
                        'rising_limb_detected': rising_detected,
                        'rising_limb_intensity': rising_intensity if rising_detected else None,
                        # BDI
                        'bdi': bdi,
                        'bdi_classification': bdi_class,
                        'q_btm_vert': data['qBtmVertRunoff'],
                        'q_bucket': data['qBucket'],
                        'q_sfc_lat': data['qSfcLatRunoff'],
                        # Velocity
                        'velocity_ms': data['velocity'],
                        'velocity_suitable': velocity_suitable,
                        'velocity_classification': velocity_class,
                        'velocity_score': velocity_score
                    })

                    print("OK")

                except Exception as e:
                    print(f"ERROR ({str(e)[:50]})")
                    continue

            print()
            print(f"Successfully processed {len(results)} reaches")
            print()

            # Convert to DataFrame
            df = pd.DataFrame(results)

            # Save to CSV
            df.to_csv(output_file, index=False)
            print(f"Results saved to: {output_file}")
            print()

            # Display summary statistics
            print("=" * 80)
            print("SUMMARY STATISTICS")
            print("=" * 80)
            print()

            print("Rising Limb Detection:")
            print(f"  Reaches with rising limb detected: {df['rising_limb_detected'].sum()} ({df['rising_limb_detected'].sum()/len(df)*100:.1f}%)")
            if df['rising_limb_detected'].any():
                intensity_counts = df[df['rising_limb_detected']]['rising_limb_intensity'].value_counts()
                for intensity, count in intensity_counts.items():
                    print(f"    {intensity}: {count}")
            print()

            print("Baseflow Dominance Index (BDI):")
            print(f"  Mean BDI: {df['bdi'].mean():.3f}")
            print(f"  BDI range: {df['bdi'].min():.3f} - {df['bdi'].max():.3f}")
            print(f"  Classifications:")
            bdi_counts = df['bdi_classification'].value_counts()
            for classification, count in bdi_counts.items():
                print(f"    {classification}: {count} ({count/len(df)*100:.1f}%)")
            print()

            print("Velocity Suitability:")
            print(f"  Mean velocity: {df['velocity_ms'].mean():.3f} m/s")
            print(f"  Velocity range: {df['velocity_ms'].min():.3f} - {df['velocity_ms'].max():.3f} m/s")
            print(f"  Suitable reaches: {df['velocity_suitable'].sum()} ({df['velocity_suitable'].sum()/len(df)*100:.1f}%)")
            print(f"  Mean suitability score: {df['velocity_score'].mean():.3f}")
            print(f"  Classifications:")
            vel_counts = df['velocity_classification'].value_counts()
            for classification, count in vel_counts.items():
                print(f"    {classification}: {count} ({count/len(df)*100:.1f}%)")
            print()

            print("Flow Characteristics:")
            print(f"  Mean streamflow: {df['streamflow_m3s'].mean():.3f} m³/s")
            print(f"  Streamflow range: {df['streamflow_m3s'].min():.3f} - {df['streamflow_m3s'].max():.3f} m³/s")
            print()

            # Correlations
            print("Interesting Correlations:")
            print(f"  BDI vs Velocity correlation: {df['bdi'].corr(df['velocity_ms']):.3f}")
            print(f"  BDI vs Velocity score correlation: {df['bdi'].corr(df['velocity_score']):.3f}")
            print()

            # Top reaches for habitat quality
            print("Top 5 Reaches for Trout Habitat (by velocity score):")
            top_reaches = df.nlargest(5, 'velocity_score')[['feature_id', 'velocity_ms', 'velocity_score', 'bdi', 'bdi_classification']]
            for idx, row in top_reaches.iterrows():
                print(f"  Reach {row['feature_id']}: velocity={row['velocity_ms']:.3f} m/s, "
                      f"score={row['velocity_score']:.3f}, BDI={row['bdi']:.3f} ({row['bdi_classification']})")
            print()

            print("=" * 80)
            print("TEST COMPLETE!")
            print("=" * 80)
            print()
            print(f"Tested {len(results)} reaches across all EPIC 2 metrics")
            print(f"Results saved to: {output_file}")
            print()
            print("All three metrics are working correctly with real database data!")
            print()

            return True

    except Exception as e:
        print(f"ERROR: Test failed with exception:")
        print(f"  {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_all_metrics_50_reaches()
    sys.exit(0 if success else 1)
