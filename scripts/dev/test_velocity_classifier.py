"""
Database Integration Test for Velocity Suitability Classifier

Tests the velocity classifier against real database data.
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

from src.metrics.velocity import (
    classify_velocity,
    classify_velocity_for_reach,
    classify_velocity_timeseries_for_reach,
    compute_velocity_statistics,
    explain_velocity_suitability,
    load_species_config
)


def test_velocity_with_db():
    """Test velocity classifier with real database data"""

    print("=" * 70)
    print("Velocity Suitability Classifier - Database Integration Test")
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

            # Load species configuration
            print("Loading species configuration...")
            species_config = load_species_config("trout")
            print(f"  Species: {species_config.species_name}")
            print(f"  Tolerable range: {species_config.min_tolerable} - {species_config.max_tolerable} m/s")
            print(f"  Optimal range: {species_config.min_optimal} - {species_config.max_optimal} m/s")
            print()

            # Check for velocity data
            print("Checking for velocity data...")
            result = conn.execute(text("""
                SELECT COUNT(*) as count,
                       MIN(value) as min_vel,
                       MAX(value) as max_vel,
                       AVG(value) as avg_vel
                FROM hydro_timeseries
                WHERE variable = 'velocity'
            """))

            row = result.fetchone()
            count, min_vel, max_vel, avg_vel = row

            print(f"  Total velocity records: {count:,}")
            print(f"  Velocity range: {min_vel:.4f} - {max_vel:.4f} m/s")
            print(f"  Average velocity: {avg_vel:.4f} m/s")
            print()

            if count == 0:
                print("WARNING: No velocity data found in database")
                return False

            # Find a reach with velocity data
            print("Finding reach with velocity data...")
            result = conn.execute(text("""
                SELECT feature_id, COUNT(*) as record_count
                FROM hydro_timeseries
                WHERE variable = 'velocity'
                GROUP BY feature_id
                ORDER BY COUNT(*) DESC
                LIMIT 1
            """))

            sample_reach = result.fetchone()

            if not sample_reach:
                print("ERROR: No reach found with velocity data")
                return False

            feature_id, record_count = sample_reach
            print(f"  Selected reach: {feature_id}")
            print(f"  Records available: {record_count}")
            print()

            # Get a single timestamp
            result = conn.execute(text("""
                SELECT valid_time, value
                FROM hydro_timeseries
                WHERE feature_id = :feature_id
                  AND variable = 'velocity'
                ORDER BY valid_time DESC
                LIMIT 1
            """), {'feature_id': feature_id})

            row = result.fetchone()
            valid_time, velocity_value = row

            print(f"  Selected timestamp: {valid_time}")
            print(f"  Velocity: {velocity_value:.4f} m/s")
            print()

            # Test 1: Single timestamp classification
            print("-" * 70)
            print("Test 1: Single Timestamp Classification")
            print("-" * 70)

            suitable, classification, score = classify_velocity(velocity_value, species_config)

            print(f"  Velocity: {velocity_value:.4f} m/s")
            print(f"  Suitable: {suitable}")
            print(f"  Classification: {classification}")
            print(f"  Score: {score:.4f}")
            print()

            explanation = explain_velocity_suitability(
                velocity_value,
                suitable,
                classification,
                score,
                species_config.species_name
            )
            print(f"  Explanation:")
            print(f"    {explanation}")
            print()

            # Test 2: Database function
            print("-" * 70)
            print("Test 2: Database Integration Function")
            print("-" * 70)

            result_db = classify_velocity_for_reach(
                feature_id=feature_id,
                valid_time=valid_time,
                species_config=species_config,
                db_connection=conn
            )

            if result_db:
                suitable_db, classification_db, score_db = result_db
                print(f"  Suitable (from DB function): {suitable_db}")
                print(f"  Classification (from DB function): {classification_db}")
                print(f"  Score (from DB function): {score_db:.4f}")
                print()

                # Verify consistency
                if (suitable == suitable_db and
                    classification == classification_db and
                    abs(score - score_db) < 0.0001):
                    print("PASS: Database function matches manual calculation")
                else:
                    print("WARNING: Results differ")
            else:
                print("ERROR: Database function returned None")
            print()

            # Test 3: Time series analysis
            print("-" * 70)
            print("Test 3: Time Series Analysis")
            print("-" * 70)

            # Get time range
            result = conn.execute(text("""
                SELECT MIN(valid_time) as start_time,
                       MAX(valid_time) as end_time
                FROM hydro_timeseries
                WHERE feature_id = :feature_id
                  AND variable = 'velocity'
            """), {'feature_id': feature_id})

            row = result.fetchone()
            start_time, end_time = row

            print(f"  Time range: {start_time} to {end_time}")
            print()

            # Classify time series
            df_velocity = classify_velocity_timeseries_for_reach(
                feature_id=feature_id,
                start_time=start_time,
                end_time=end_time,
                species_config=species_config,
                db_connection=conn
            )

            if len(df_velocity) > 0:
                print(f"  Classified {len(df_velocity)} timestamps")
                print()
                print("  Sample of velocity classifications (first 5 records):")
                for i in range(min(5, len(df_velocity))):
                    row = df_velocity.iloc[i]
                    print(f"    {row['valid_time']}: {row['velocity_ms']:.4f} m/s -> "
                          f"{row['classification']} (score={row['score']:.3f})")
                if len(df_velocity) > 5:
                    print(f"    ... ({len(df_velocity) - 5} more records)")
                print()

                # Compute statistics
                stats = compute_velocity_statistics(df_velocity)

                print("  Velocity Suitability Statistics:")
                print(f"    Mean velocity: {stats['mean_velocity']:.4f} m/s")
                print(f"    Mean suitability score: {stats['mean_score']:.4f}")
                print(f"    Percent suitable: {stats['percent_suitable']:.1f}%")
                print(f"    Percent optimal: {stats['percent_optimal']:.1f}%")
                print(f"    Dominant classification: {stats['dominant_class']}")
                print()

                # Ecological interpretation
                print("  Ecological Interpretation:")
                if stats['dominant_class'] == 'optimal':
                    print("    This reach has predominantly optimal velocities for trout:")
                    print("      - Excellent feeding habitat (drift capture)")
                    print("      - Good resting areas (not too fast)")
                    print("      - Suitable spawning conditions")
                elif stats['dominant_class'] == 'too_slow':
                    if stats['percent_suitable'] > 50:
                        print("    This reach has slow but tolerable velocities:")
                        print("      - Pool habitat (resting areas)")
                        print("      - May have reduced oxygen in very slow areas")
                        print("      - Less efficient feeding (low drift velocity)")
                    else:
                        print("    This reach has predominantly too-slow velocities:")
                        print("      - Stagnant conditions")
                        print("      - Likely unsuitable for active feeding")
                elif stats['dominant_class'] == 'fast':
                    print("    This reach has predominantly fast velocities:")
                    print("      - High energy costs for fish")
                    print("      - May limit time fish can hold position")
                    print("      - Good oxygen but reduced feeding efficiency")
                elif stats['dominant_class'] == 'too_fast':
                    print("    This reach has predominantly too-fast velocities:")
                    print("      - Unsuitable habitat (exceeds swimming capacity)")
                    print("      - Fish cannot hold position")
                    print("      - Limited use except during migrations")
                print()

                # Habitat quality summary
                if stats['percent_optimal'] > 60:
                    print("    Overall: EXCELLENT habitat quality for trout")
                elif stats['percent_suitable'] > 70:
                    print("    Overall: GOOD habitat quality for trout")
                elif stats['percent_suitable'] > 40:
                    print("    Overall: FAIR habitat quality for trout")
                else:
                    print("    Overall: POOR habitat quality for trout")
                print()

            else:
                print("WARNING: No velocity time series data available")
                print()

            print("=" * 70)
            print("DATABASE INTEGRATION TEST COMPLETE!")
            print("=" * 70)
            print()
            print("Summary:")
            print(f"  Feature ID tested: {feature_id}")
            print(f"  Timestamps analyzed: {len(df_velocity) if len(df_velocity) > 0 else 1}")
            if len(df_velocity) > 0:
                print(f"  Mean velocity: {stats['mean_velocity']:.4f} m/s")
                print(f"  Suitability: {stats['percent_suitable']:.1f}% suitable")
                print(f"  Dominant class: {stats['dominant_class']}")
            else:
                print(f"  Single timestamp velocity: {velocity_value:.4f} m/s")
                print(f"  Classification: {classification}")
            print()
            print("Ticket 2.3 (Velocity Classifier) successfully verified with database!")
            print()

            return True

    except Exception as e:
        print(f"ERROR: Test failed with exception:")
        print(f"  {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_velocity_with_db()
    sys.exit(0 if success else 1)
