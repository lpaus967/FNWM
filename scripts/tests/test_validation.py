"""
Test NWM-USGS Validation

Tests the validation module by comparing NWM predictions with USGS observations.
"""

import os
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv
from src.validation.nwm_usgs_validator import NWMUSGSValidator

# Configure stdout for UTF-8 on Windows
if sys.platform == 'win32':
    import codecs
    if sys.stdout.encoding != 'utf-8':
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    if sys.stderr.encoding != 'utf-8':
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')


def test_validation():
    """Test validation functionality."""

    load_dotenv()
    database_url = os.getenv('DATABASE_URL')

    print("=" * 80)
    print("NWM-USGS Validation Test")
    print("=" * 80)
    print()

    # Initialize validator
    validator = NWMUSGSValidator(database_url)

    # Get USGS-NHD mapping
    print("Step 1: Getting USGS-NHD mapping...")
    print("-" * 80)
    mapping = validator.get_usgs_nhdplus_mapping()

    if not mapping:
        print("No USGS sites mapped to NHD flowlines")
        print("Make sure both USGS_Flowsites and nhd_flowlines tables have data")
        return False

    print(f"Found {len(mapping)} USGS sites mapped to NHD flowlines:")
    for site_id, info in mapping.items():
        print(f"  {site_id} -> NHDPlus {info['nhdplusid']} ({info['site_name']})")
        print(f"    Distance: {info['distance_m']:.1f} meters")
    print()

    # Set validation period (last 7 days)
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=7)

    print("Step 2: Running validation...")
    print("-" * 80)
    print(f"Validation period: {start_time.strftime('%Y-%m-%d %H:%M')} to {end_time.strftime('%Y-%m-%d %H:%M')}")
    print(f"NWM product: analysis_assim")
    print()

    # Run validation
    results = validator.validate_all_sites(
        start_time=start_time,
        end_time=end_time,
        nwm_product='analysis_assim'
    )

    if not results:
        print("No validation results (insufficient paired data)")
        print()
        print("Possible reasons:")
        print("  1. No NWM data for this period")
        print("  2. No USGS data for this period")
        print("  3. Timestamps don't align between NWM and USGS")
        return False

    # Display results
    print("=" * 80)
    print("VALIDATION RESULTS")
    print("=" * 80)
    print()

    for metrics in results:
        print(str(metrics))
        print("-" * 80)

    # Summary statistics
    print("\n" + "=" * 80)
    print("SUMMARY STATISTICS")
    print("=" * 80)

    avg_corr = sum(m.correlation for m in results) / len(results)
    avg_rmse = sum(m.rmse for m in results) / len(results)
    avg_mae = sum(m.mae for m in results) / len(results)
    avg_nse = sum(m.nash_sutcliffe for m in results) / len(results)
    total_obs = sum(m.n_observations for m in results)

    print(f"Sites validated: {len(results)}")
    print(f"Total observations: {total_obs}")
    print(f"Average correlation: {avg_corr:.3f}")
    print(f"Average RMSE: {avg_rmse:.2f} cfs")
    print(f"Average MAE: {avg_mae:.2f} cfs")
    print(f"Average Nash-Sutcliffe: {avg_nse:.3f}")
    print()

    # Performance ratings
    excellent = sum(1 for m in results if m.nash_sutcliffe > 0.75)
    very_good = sum(1 for m in results if 0.65 < m.nash_sutcliffe <= 0.75)
    good = sum(1 for m in results if 0.50 < m.nash_sutcliffe <= 0.65)
    satisfactory = sum(1 for m in results if 0.40 < m.nash_sutcliffe <= 0.50)
    unsatisfactory = sum(1 for m in results if m.nash_sutcliffe <= 0.40)

    print("Performance Ratings:")
    print(f"  Excellent (NSE > 0.75): {excellent}")
    print(f"  Very Good (NSE 0.65-0.75): {very_good}")
    print(f"  Good (NSE 0.50-0.65): {good}")
    print(f"  Satisfactory (NSE 0.40-0.50): {satisfactory}")
    print(f"  Unsatisfactory (NSE < 0.40): {unsatisfactory}")
    print()

    # Store results
    print("Step 3: Storing validation results in database...")
    print("-" * 80)

    for metrics in results:
        validator.store_validation_results(
            metrics=metrics,
            validation_period_start=start_time,
            validation_period_end=end_time,
            nwm_product='analysis_assim'
        )

    print(f"Stored {len(results)} validation results")
    print()

    print("=" * 80)
    print("Validation test complete!")
    print("=" * 80)

    return True


if __name__ == "__main__":
    try:
        success = test_validation()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
