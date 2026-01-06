"""
Database Integration Test for Species Scoring Engine

Tests the species scoring engine against real database data.
Combines data from EPIC 2 metrics with species scoring logic.
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

from src.species.scoring import (
    compute_species_score,
    load_species_config,
    SpeciesScore
)
from src.metrics.baseflow import compute_bdi
from src.metrics.velocity import classify_velocity


def test_species_scoring_with_db():
    """Test species scoring with real database data"""

    print("=" * 70)
    print("Species Scoring Engine - Database Integration Test")
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
            print("[OK] CONNECTED to database")
            print()

            # Load species config to show what we're testing
            config = load_species_config('trout')
            print(f"Species: {config['name']}")
            print(f"   Scoring weights: {config['scoring_weights']}")
            print()

            # Get a sample reach with complete data
            print("Fetching reach data...")
            result = conn.execute(text("""
                SELECT
                    feature_id,
                    COUNT(DISTINCT variable) as var_count,
                    COUNT(*) as total_records
                FROM hydro_timeseries
                WHERE variable IN ('streamflow', 'velocity', 'qBtmVertRunoff', 'qBucket', 'qSfcLatRunoff')
                GROUP BY feature_id
                HAVING COUNT(DISTINCT variable) >= 5
                ORDER BY COUNT(*) DESC
                LIMIT 1
            """))

            row = result.fetchone()
            if not row:
                print("[ERROR] No reaches found with complete data")
                return False

            feature_id = row[0]
            print(f"   Selected reach: {feature_id}")
            print(f"   Variables available: {row[1]}")
            print(f"   Total records: {row[2]}")
            print()

            # Get latest time with all required variables
            result = conn.execute(text("""
                SELECT valid_time
                FROM hydro_timeseries
                WHERE feature_id = :feature_id
                  AND variable IN ('streamflow', 'velocity', 'qBtmVertRunoff', 'qBucket', 'qSfcLatRunoff')
                GROUP BY valid_time
                HAVING COUNT(DISTINCT variable) = 5
                ORDER BY valid_time DESC
                LIMIT 1
            """), {'feature_id': feature_id})

            time_row = result.fetchone()
            if not time_row:
                print("[ERROR] No timestep found with all required variables")
                return False

            valid_time = time_row[0]
            print(f"[TIME] Using timestep: {valid_time}")
            print()

            # Fetch all required data for this reach/time
            result = conn.execute(text("""
                SELECT variable, value
                FROM hydro_timeseries
                WHERE feature_id = :feature_id
                  AND valid_time = :valid_time
                  AND variable IN ('streamflow', 'velocity', 'qBtmVertRunoff', 'qBucket', 'qSfcLatRunoff')
            """), {'feature_id': feature_id, 'valid_time': valid_time})

            data = {row[0]: row[1] for row in result}

            print("📊 Raw Hydrologic Data:")
            print(f"   Streamflow: {data.get('streamflow', 0):.3f} m³/s")
            print(f"   Velocity: {data.get('velocity', 0):.3f} m/s")
            print(f"   qBtmVertRunoff: {data.get('qBtmVertRunoff', 0):.3f} m³/s")
            print(f"   qBucket: {data.get('qBucket', 0):.3f} m³/s")
            print(f"   qSfcLatRunoff: {data.get('qSfcLatRunoff', 0):.3f} m³/s")
            print()

            # Compute derived metrics (using EPIC 2 functions)
            print("🔬 Computing derived metrics...")

            # Compute BDI
            bdi = compute_bdi(
                q_btm_vert=data.get('qBtmVertRunoff', 0),
                q_bucket=data.get('qBucket', 0),
                q_sfc_lat=data.get('qSfcLatRunoff', 0)
            )

            # Compute flow percentile (simplified - using historical data from same reach)
            result = conn.execute(text("""
                SELECT
                    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY value) as p50,
                    :flow as current_flow
                FROM hydro_timeseries
                WHERE feature_id = :feature_id
                  AND variable = 'streamflow'
                  AND value > 0
            """), {'feature_id': feature_id, 'flow': data.get('streamflow', 0)})

            flow_stats = result.fetchone()
            median_flow = flow_stats[0] if flow_stats[0] else 1.0
            current_flow = data.get('streamflow', 0)

            # Estimate percentile (very simplified)
            if current_flow >= median_flow:
                flow_percentile = 50 + min(50, (current_flow / median_flow - 1) * 50)
            else:
                flow_percentile = 50 * (current_flow / median_flow) if median_flow > 0 else 50

            print(f"   BDI: {bdi:.3f}")
            print(f"   Flow percentile (est): {flow_percentile:.1f}")
            print()

            # Build hydro_data dict for species scoring
            hydro_data = {
                'flow_percentile': flow_percentile,
                'velocity': data.get('velocity', 0),
                'bdi': bdi,
                'flow_variability': None,  # Would need time series to compute
            }

            # Compute species score
            print("🐟 Computing species habitat score...")
            score = compute_species_score(
                feature_id=feature_id,
                species='trout',
                hydro_data=hydro_data,
                confidence='medium'
            )

            # Display results
            print()
            print("=" * 70)
            print("SPECIES HABITAT SCORE RESULTS")
            print("=" * 70)
            print()
            print(f"Overall Score: {score.overall_score:.3f}")
            print(f"Rating: {score.rating.upper()}")
            print()
            print("Component Scores:")
            for component, value in score.components.items():
                bar = "█" * int(value * 20)
                print(f"  {component:12} {value:.3f} {bar}")
            print()
            print(f"Explanation:")
            print(f"  {score.explanation}")
            print()
            print(f"Confidence: {score.confidence}")
            print(f"Timestamp: {score.timestamp}")
            print()

            # Interpretation
            print("=" * 70)
            print("INTERPRETATION")
            print("=" * 70)
            print()

            if score.overall_score >= 0.8:
                print("[OK] This reach shows EXCELLENT habitat conditions for coldwater trout.")
                print("   Anglers should expect strong fishing opportunities.")
            elif score.overall_score >= 0.6:
                print("[OK] This reach shows GOOD habitat conditions for coldwater trout.")
                print("   Conditions are favorable for trout populations.")
            elif score.overall_score >= 0.3:
                print("[WARN]  This reach shows FAIR habitat conditions for coldwater trout.")
                print("   Conditions are marginal but may still support some fish.")
            else:
                print("[ERROR] This reach shows POOR habitat conditions for coldwater trout.")
                print("   Conditions are not suitable for trout at this time.")

            print()

            # Key factors
            if score.components['flow'] < 0.3:
                print("[WARN]  Flow conditions are suboptimal")
            if score.components['velocity'] < 0.3:
                print("[WARN]  Velocity conditions are suboptimal")
            if score.components['stability'] < 0.3:
                print("[WARN]  Stream stability is low (flashy conditions)")
            if score.components['thermal'] == 0.0:
                print("[INFO]  Temperature data not yet integrated (EPIC 3 pending)")

            print()

            # Test multiple reaches
            print("=" * 70)
            print("TESTING MULTIPLE REACHES")
            print("=" * 70)
            print()

            result = conn.execute(text("""
                SELECT DISTINCT feature_id
                FROM hydro_timeseries
                WHERE variable IN ('streamflow', 'velocity', 'qBtmVertRunoff', 'qBucket', 'qSfcLatRunoff')
                GROUP BY feature_id
                HAVING COUNT(DISTINCT variable) = 5
                LIMIT 10
            """))

            reach_scores = []

            for row in result:
                test_feature_id = row[0]

                # Get data for this reach
                result2 = conn.execute(text("""
                    SELECT variable, AVG(value) as avg_value
                    FROM hydro_timeseries
                    WHERE feature_id = :feature_id
                      AND variable IN ('streamflow', 'velocity', 'qBtmVertRunoff', 'qBucket', 'qSfcLatRunoff')
                    GROUP BY variable
                """), {'feature_id': test_feature_id})

                reach_data = {row[0]: row[1] for row in result2}

                if len(reach_data) < 5:
                    continue

                # Compute BDI
                bdi = compute_bdi(
                    q_btm_vert=reach_data.get('qBtmVertRunoff', 0),
                    q_bucket=reach_data.get('qBucket', 0),
                    q_sfc_lat=reach_data.get('qSfcLatRunoff', 0)
                )

                # Simplified hydro data
                hydro_data = {
                    'flow_percentile': 50,  # Simplified
                    'velocity': reach_data.get('velocity', 0),
                    'bdi': bdi,
                }

                # Compute score
                test_score = compute_species_score(
                    feature_id=test_feature_id,
                    species='trout',
                    hydro_data=hydro_data
                )

                reach_scores.append({
                    'feature_id': test_feature_id,
                    'score': test_score.overall_score,
                    'rating': test_score.rating,
                    'velocity': reach_data.get('velocity', 0),
                    'bdi': bdi
                })

            # Display summary
            reach_df = pd.DataFrame(reach_scores)
            print(f"Tested {len(reach_scores)} reaches:")
            print()
            print(reach_df.to_string(index=False))
            print()

            # Statistics
            print("Summary Statistics:")
            print(f"  Mean score: {reach_df['score'].mean():.3f}")
            print(f"  Min score: {reach_df['score'].min():.3f}")
            print(f"  Max score: {reach_df['score'].max():.3f}")
            print()

            print("Rating Distribution:")
            print(reach_df['rating'].value_counts().to_string())
            print()

            print("=" * 70)
            print("[OK] SPECIES SCORING ENGINE TEST COMPLETE")
            print("=" * 70)

            return True

    except Exception as e:
        print(f"[ERROR] ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_species_scoring_with_db()
    sys.exit(0 if success else 1)
