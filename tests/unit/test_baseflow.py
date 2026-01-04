"""
Unit Tests for Baseflow Dominance Index (BDI)

Tests verify:
1. Correct BDI calculation
2. Normalized 0-1 output
3. Edge case handling (zero flow, negative values, NaN)
4. Classification thresholds
5. Time series computation
6. Statistical summaries
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime
from pathlib import Path
import sys
import pytz

# Add src to path
src_path = Path(__file__).parent.parent.parent / 'src'
sys.path.insert(0, str(src_path))

from metrics.baseflow import (
    compute_bdi,
    classify_bdi,
    compute_bdi_with_classification,
    explain_bdi,
    compute_bdi_timeseries,
    compute_bdi_statistics
)


# Test Cases: Basic BDI Calculation

def test_bdi_pure_baseflow():
    """Test BDI with 100% baseflow (no surface runoff)"""
    bdi = compute_bdi(q_btm_vert=5.0, q_bucket=3.0, q_sfc_lat=0.0)

    assert bdi == 1.0, "Pure baseflow should return BDI = 1.0"


def test_bdi_pure_surface_runoff():
    """Test BDI with 100% surface runoff (no baseflow)"""
    bdi = compute_bdi(q_btm_vert=0.0, q_bucket=0.0, q_sfc_lat=10.0)

    assert bdi == 0.0, "Pure surface runoff should return BDI = 0.0"


def test_bdi_equal_mix():
    """Test BDI with equal baseflow and surface runoff"""
    bdi = compute_bdi(q_btm_vert=2.5, q_bucket=2.5, q_sfc_lat=5.0)

    assert bdi == 0.5, "Equal mix should return BDI = 0.5"


def test_bdi_spring_creek():
    """Test BDI for typical spring creek (high baseflow)"""
    # Spring creeks typically have >80% baseflow
    bdi = compute_bdi(q_btm_vert=5.0, q_bucket=3.0, q_sfc_lat=0.5)

    assert bdi > 0.8, "Spring creek should have BDI > 0.8"
    assert bdi < 1.0, "BDI should be less than 1.0 with some surface runoff"


def test_bdi_storm_dominated():
    """Test BDI for storm-dominated stream"""
    bdi = compute_bdi(q_btm_vert=0.5, q_bucket=0.3, q_sfc_lat=10.0)

    assert bdi < 0.2, "Storm-dominated stream should have BDI < 0.2"
    assert bdi >= 0.0, "BDI should be non-negative"


def test_bdi_mixed_source():
    """Test BDI for mixed-source stream"""
    bdi = compute_bdi(q_btm_vert=2.0, q_bucket=1.5, q_sfc_lat=3.5)

    assert 0.4 < bdi < 0.6, "Mixed source should have BDI around 0.5"


# Test Cases: Edge Cases

def test_bdi_zero_flow():
    """Test BDI with zero total flow"""
    bdi = compute_bdi(q_btm_vert=0.0, q_bucket=0.0, q_sfc_lat=0.0)

    assert bdi == 0.0, "Zero flow should return BDI = 0.0"


def test_bdi_negative_values():
    """Test that negative values are handled (shouldn't occur, but be defensive)"""
    bdi = compute_bdi(q_btm_vert=-1.0, q_bucket=5.0, q_sfc_lat=2.0)

    # Negative values should be treated as zero
    expected_bdi = 5.0 / (0.0 + 5.0 + 2.0)
    assert abs(bdi - expected_bdi) < 0.001, "Negative values should be treated as zero"


def test_bdi_very_small_values():
    """Test BDI with very small flow values"""
    bdi = compute_bdi(q_btm_vert=0.001, q_bucket=0.001, q_sfc_lat=0.001)

    assert 0.6 < bdi < 0.7, "Should handle very small values correctly"


def test_bdi_very_large_values():
    """Test BDI with very large flow values"""
    bdi = compute_bdi(q_btm_vert=10000.0, q_bucket=5000.0, q_sfc_lat=1000.0)

    expected_bdi = 15000.0 / 16000.0
    assert abs(bdi - expected_bdi) < 0.001, "Should handle large values correctly"


# Test Cases: Classification

def test_classify_groundwater_fed():
    """Test classification of groundwater-fed streams"""
    assert classify_bdi(0.85) == "groundwater_fed"
    assert classify_bdi(0.65) == "groundwater_fed"  # Boundary
    assert classify_bdi(1.0) == "groundwater_fed"


def test_classify_mixed():
    """Test classification of mixed-source streams"""
    assert classify_bdi(0.50) == "mixed"
    assert classify_bdi(0.35) == "mixed"  # Lower boundary
    assert classify_bdi(0.64) == "mixed"  # Upper boundary


def test_classify_storm_dominated():
    """Test classification of storm-dominated streams"""
    assert classify_bdi(0.20) == "storm_dominated"
    assert classify_bdi(0.34) == "storm_dominated"  # Boundary
    assert classify_bdi(0.0) == "storm_dominated"


# Test Cases: BDI with Classification

def test_bdi_with_classification_groundwater():
    """Test combined BDI calculation and classification for groundwater stream"""
    bdi, classification = compute_bdi_with_classification(
        q_btm_vert=8.0,
        q_bucket=4.0,
        q_sfc_lat=1.0
    )

    assert bdi > 0.9, "Should have high BDI"
    assert classification == "groundwater_fed", "Should classify as groundwater-fed"


def test_bdi_with_classification_storm():
    """Test combined BDI calculation and classification for storm-dominated stream"""
    bdi, classification = compute_bdi_with_classification(
        q_btm_vert=0.5,
        q_bucket=0.5,
        q_sfc_lat=15.0
    )

    assert bdi < 0.1, "Should have low BDI"
    assert classification == "storm_dominated", "Should classify as storm-dominated"


# Test Cases: Explanation Generation

def test_explain_bdi_groundwater():
    """Test explanation for groundwater-fed stream"""
    explanation = explain_bdi(0.85, "groundwater_fed")

    assert "0.85" in explanation, "Should include BDI value"
    assert "groundwater" in explanation.lower(), "Should mention groundwater"
    assert "thermal stability" in explanation.lower(), "Should mention thermal stability"


def test_explain_bdi_storm():
    """Test explanation for storm-dominated stream"""
    explanation = explain_bdi(0.15, "storm_dominated")

    assert "0.15" in explanation, "Should include BDI value"
    assert "storm" in explanation.lower() or "surface" in explanation.lower(), "Should mention storm/surface"
    assert "flashy" in explanation.lower() or "variable" in explanation.lower(), "Should mention variability"


def test_explain_bdi_auto_classify():
    """Test explanation with automatic classification"""
    explanation = explain_bdi(0.75)

    assert "0.75" in explanation, "Should include BDI value"
    assert "groundwater" in explanation.lower(), "Should auto-classify as groundwater-fed"


# Test Cases: Time Series

def test_bdi_timeseries_basic():
    """Test BDI time series computation"""
    times = pd.date_range('2025-01-01', periods=5, freq='H', tz=pytz.UTC)

    q_btm = pd.Series([5.0, 5.5, 6.0, 5.5, 5.0], index=times)
    q_bucket = pd.Series([3.0, 3.2, 3.5, 3.2, 3.0], index=times)
    q_sfc = pd.Series([0.5, 0.6, 0.8, 0.6, 0.5], index=times)

    bdi_series = compute_bdi_timeseries(q_btm, q_bucket, q_sfc)

    assert len(bdi_series) == 5, "Should have same length as input"
    assert all(0.0 <= bdi <= 1.0 for bdi in bdi_series), "All BDI values should be in [0, 1]"
    assert all(bdi > 0.8 for bdi in bdi_series), "All should be high BDI (groundwater-fed)"


def test_bdi_timeseries_with_missing_data():
    """Test BDI time series with missing data (NaN)"""
    times = pd.date_range('2025-01-01', periods=5, freq='H', tz=pytz.UTC)

    q_btm = pd.Series([5.0, np.nan, 6.0, 5.5, 5.0], index=times)
    q_bucket = pd.Series([3.0, 3.2, 3.5, 3.2, 3.0], index=times)
    q_sfc = pd.Series([0.5, 0.6, 0.8, 0.6, 0.5], index=times)

    bdi_series = compute_bdi_timeseries(q_btm, q_bucket, q_sfc)

    assert len(bdi_series) == 4, "Should drop NaN rows"
    assert all(0.0 <= bdi <= 1.0 for bdi in bdi_series), "All BDI values should be in [0, 1]"


def test_bdi_timeseries_variable_conditions():
    """Test BDI time series with changing conditions"""
    times = pd.date_range('2025-01-01', periods=10, freq='H', tz=pytz.UTC)

    # Simulate storm event: baseflow stable, surface runoff increases then decreases
    q_btm = pd.Series([5.0]*10, index=times)
    q_bucket = pd.Series([3.0]*10, index=times)
    q_sfc = pd.Series([0.5, 0.5, 2.0, 8.0, 15.0, 12.0, 6.0, 2.0, 0.5, 0.5], index=times)

    bdi_series = compute_bdi_timeseries(q_btm, q_bucket, q_sfc)

    # BDI should decrease during storm, then recover
    assert bdi_series.iloc[0] > 0.8, "Pre-storm should be high BDI"
    assert bdi_series.iloc[4] < 0.4, "Peak storm should be low BDI"
    assert bdi_series.iloc[-1] > 0.8, "Post-storm should recover to high BDI"


# Test Cases: Statistics

def test_bdi_statistics_stable_stream():
    """Test BDI statistics for stable groundwater-fed stream"""
    times = pd.date_range('2025-01-01', periods=24, freq='H', tz=pytz.UTC)

    # Very stable BDI (spring creek)
    bdi_series = pd.Series([0.92, 0.93, 0.91, 0.92, 0.93, 0.92]*4, index=times)

    stats = compute_bdi_statistics(bdi_series)

    assert stats['mean'] > 0.9, "Mean should be high"
    assert stats['dominant_class'] == "groundwater_fed", "Should classify as groundwater-fed"
    assert stats['stability'] > 0.9, "Should be very stable"
    assert stats['std'] < 0.02, "Should have low variability"


def test_bdi_statistics_variable_stream():
    """Test BDI statistics for variable stream"""
    times = pd.date_range('2025-01-01', periods=24, freq='H', tz=pytz.UTC)

    # Variable BDI (flashy stream)
    bdi_values = [0.8]*6 + [0.4]*6 + [0.2]*6 + [0.6]*6
    bdi_series = pd.Series(bdi_values, index=times)

    stats = compute_bdi_statistics(bdi_series)

    assert 0.4 < stats['mean'] < 0.6, "Mean should be moderate"
    assert stats['std'] > 0.1, "Should have high variability"
    assert stats['stability'] < 0.8, "Should be less stable"


def test_bdi_statistics_empty_series():
    """Test BDI statistics with empty series"""
    bdi_series = pd.Series([], dtype=float)

    stats = compute_bdi_statistics(bdi_series)

    assert stats['mean'] is None, "Should return None for empty series"
    assert stats['dominant_class'] is None, "Should return None for empty series"


# Test Cases: Bounds and Invariants

def test_bdi_always_bounded():
    """Property: BDI should always be between 0 and 1"""
    test_cases = [
        (0, 0, 0),
        (10, 10, 10),
        (100, 0, 0),
        (0, 100, 0),
        (0, 0, 100),
        (1, 2, 3),
        (0.001, 0.002, 0.003),
    ]

    for q_btm, q_bucket, q_sfc in test_cases:
        bdi = compute_bdi(q_btm, q_bucket, q_sfc)
        assert 0.0 <= bdi <= 1.0, f"BDI should be in [0, 1] for ({q_btm}, {q_bucket}, {q_sfc})"


def test_bdi_increases_with_baseflow():
    """Property: BDI should increase when baseflow increases (holding others constant)"""
    q_bucket = 2.0
    q_sfc = 5.0

    bdi_low = compute_bdi(q_btm_vert=1.0, q_bucket=q_bucket, q_sfc_lat=q_sfc)
    bdi_high = compute_bdi(q_btm_vert=10.0, q_bucket=q_bucket, q_sfc_lat=q_sfc)

    assert bdi_high > bdi_low, "BDI should increase with more baseflow"


def test_bdi_decreases_with_surface_runoff():
    """Property: BDI should decrease when surface runoff increases (holding others constant)"""
    q_btm = 5.0
    q_bucket = 3.0

    bdi_low_runoff = compute_bdi(q_btm_vert=q_btm, q_bucket=q_bucket, q_sfc_lat=1.0)
    bdi_high_runoff = compute_bdi(q_btm_vert=q_btm, q_bucket=q_bucket, q_sfc_lat=20.0)

    assert bdi_low_runoff > bdi_high_runoff, "BDI should decrease with more surface runoff"


def test_bdi_symmetric_baseflow_components():
    """Property: BDI should treat both baseflow components equally"""
    # Test 1: 5 deep + 3 shallow should equal 3 deep + 5 shallow
    bdi1 = compute_bdi(q_btm_vert=5.0, q_bucket=3.0, q_sfc_lat=2.0)
    bdi2 = compute_bdi(q_btm_vert=3.0, q_bucket=5.0, q_sfc_lat=2.0)

    assert abs(bdi1 - bdi2) < 0.001, "BDI should be same regardless of baseflow component distribution"


# Test Cases: Ecological Thresholds

def test_known_trout_stream_high_bdi():
    """Test that known trout streams have high BDI (>0.6)"""
    # Spring creek supporting wild trout population
    # Typical: 70-90% baseflow
    bdi = compute_bdi(q_btm_vert=6.0, q_bucket=3.0, q_sfc_lat=2.0)

    assert bdi > 0.6, "Trout streams should have BDI > 0.6"
    assert classify_bdi(bdi) in ["groundwater_fed", "mixed"], "Should be groundwater-fed or mixed"


def test_known_flashy_stream_low_bdi():
    """Test that known flashy streams have low BDI (<0.4)"""
    # Urban stream with high impervious surface
    # Typical: <30% baseflow
    bdi = compute_bdi(q_btm_vert=0.5, q_bucket=0.5, q_sfc_lat=9.0)

    assert bdi < 0.4, "Flashy streams should have BDI < 0.4"
    assert classify_bdi(bdi) in ["storm_dominated", "mixed"], "Should be storm-dominated or mixed"


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "--tb=short"])
