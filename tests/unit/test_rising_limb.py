"""
Unit Tests for Rising Limb Detector

Tests verify:
1. Detection of sustained rising limbs
2. Intensity classification (weak/moderate/strong)
3. Config-driven thresholds
4. Species-specific overrides
5. Edge case handling (missing data, short series, stable flow)
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
import sys
import pytz

# Add src to path
src_path = Path(__file__).parent.parent.parent / 'src'
sys.path.insert(0, str(src_path))

from metrics.rising_limb import (
    detect_rising_limb,
    RisingLimbConfig,
    explain_detection,
    load_default_config
)


# Fixtures
@pytest.fixture
def default_config():
    """Default configuration for testing"""
    return RisingLimbConfig(
        min_slope=0.5,
        min_duration=3,
        intensity_thresholds={
            'weak': 0.5,
            'moderate': 2.0,
            'strong': 5.0
        }
    )


@pytest.fixture
def strict_config():
    """Stricter configuration (e.g., for anadromous salmonids)"""
    return RisingLimbConfig(
        min_slope=2.0,
        min_duration=6,
        intensity_thresholds={
            'weak': 2.0,
            'moderate': 5.0,
            'strong': 10.0
        }
    )


@pytest.fixture
def time_index():
    """24-hour time series index (UTC)"""
    return pd.date_range('2025-01-01', periods=24, freq='H', tz=pytz.UTC)


# Test Cases: Basic Detection

def test_moderate_rising_limb(default_config, time_index):
    """Test detection of moderate rising limb"""
    # Create flow pattern: baseflow → moderate rise → stable
    flows = pd.Series(
        [10, 10, 11, 13, 16, 20, 25, 30, 32, 33] + [33]*14,
        index=time_index
    )

    detected, intensity = detect_rising_limb(flows, default_config)

    assert detected is True, "Should detect rising limb"
    assert intensity == "moderate", "Should classify as moderate intensity"


def test_strong_rising_limb(default_config, time_index):
    """Test detection of strong rising limb (flash flood scenario)"""
    # Rapid increase: 10 → 110 in 7 hours
    flows = pd.Series(
        [10, 10, 15, 25, 40, 60, 85, 110, 110, 110] + [110]*14,
        index=time_index
    )

    detected, intensity = detect_rising_limb(flows, default_config)

    assert detected is True, "Should detect rising limb"
    assert intensity == "strong", "Should classify as strong intensity"


def test_weak_rising_limb(default_config, time_index):
    """Test detection of weak/gradual rising limb"""
    # Slow, sustained increase
    flows = pd.Series(
        [10, 10, 10.5, 11.0, 11.6, 12.3, 13.0, 13.8] + [14]*16,
        index=time_index
    )

    detected, intensity = detect_rising_limb(flows, default_config)

    assert detected is True, "Should detect rising limb"
    assert intensity == "weak", "Should classify as weak intensity"


def test_no_rising_limb_stable(default_config, time_index):
    """Test that stable flow does not trigger detection"""
    flows = pd.Series([30]*24, index=time_index)

    detected, intensity = detect_rising_limb(flows, default_config)

    assert detected is False, "Should not detect rising limb in stable flow"
    assert intensity is None, "Intensity should be None when not detected"


def test_no_rising_limb_falling(default_config, time_index):
    """Test that falling limb does not trigger detection"""
    # Falling hydrograph
    flows = pd.Series(
        [100, 95, 88, 80, 70, 60, 50, 40, 35, 30] + [30]*14,
        index=time_index
    )

    detected, intensity = detect_rising_limb(flows, default_config)

    assert detected is False, "Should not detect rising limb when falling"
    assert intensity is None, "Intensity should be None when not detected"


def test_short_duration_rise_not_detected(default_config, time_index):
    """Test that brief rises shorter than min_duration are not detected"""
    # Only 2 hours of rising (min_duration = 3)
    flows = pd.Series(
        [10, 10, 12, 14] + [14]*20,
        index=time_index
    )

    detected, intensity = detect_rising_limb(flows, default_config)

    assert detected is False, "Should not detect rising limb with insufficient duration"
    assert intensity is None, "Intensity should be None when not detected"


# Test Cases: Config-Driven Behavior

def test_species_specific_config(strict_config, time_index):
    """Test that stricter config (anadromous salmonid) requires stronger signal"""
    # Moderate rise that would be detected with default config
    flows = pd.Series(
        [10, 10, 11, 13, 16, 20, 25, 30] + [30]*16,
        index=time_index
    )

    detected, intensity = detect_rising_limb(flows, strict_config)

    # With strict config (min_slope=2.0, min_duration=6), this should NOT be detected
    assert detected is False, "Stricter config should not detect moderate rises"
    assert intensity is None, "Intensity should be None when not detected"


def test_strong_rise_detected_with_strict_config(strict_config, time_index):
    """Test that strong rises are still detected with strict config"""
    # Strong, sustained rise
    flows = pd.Series(
        [10, 10, 15, 25, 40, 60, 85, 110, 120, 130] + [130]*14,
        index=time_index
    )

    detected, intensity = detect_rising_limb(flows, strict_config)

    assert detected is True, "Strong rise should be detected even with strict config"
    assert intensity in ["moderate", "strong"], "Should classify as moderate or strong"


# Test Cases: Edge Cases

def test_empty_series(default_config):
    """Test handling of empty flow series"""
    flows = pd.Series([], dtype=float, index=pd.DatetimeIndex([]))

    detected, intensity = detect_rising_limb(flows, default_config)

    assert detected is False, "Empty series should not detect rising limb"
    assert intensity is None, "Intensity should be None for empty series"


def test_all_nan_values(default_config, time_index):
    """Test handling of all NaN values"""
    flows = pd.Series([np.nan]*24, index=time_index)

    detected, intensity = detect_rising_limb(flows, default_config)

    assert detected is False, "All NaN series should not detect rising limb"
    assert intensity is None, "Intensity should be None for all NaN series"


def test_series_shorter_than_min_duration(default_config):
    """Test handling of series shorter than min_duration"""
    times = pd.date_range('2025-01-01', periods=2, freq='H', tz=pytz.UTC)
    flows = pd.Series([10, 20], index=times)

    detected, intensity = detect_rising_limb(flows, default_config)

    assert detected is False, "Series shorter than min_duration should not detect"
    assert intensity is None, "Intensity should be None for short series"


def test_missing_data_gaps(default_config):
    """Test handling of gaps in time series"""
    # Create irregular time series with gaps
    times = pd.DatetimeIndex([
        datetime(2025, 1, 1, i, 0, 0, tzinfo=pytz.UTC)
        for i in [0, 1, 2, 6, 7, 8, 9, 10, 11, 12]  # Gap between hour 2 and 6
    ])
    flows = pd.Series([10, 11, 13, 20, 25, 30, 32, 33, 33, 33], index=times)

    detected, intensity = detect_rising_limb(flows, default_config)

    # Should still detect rising limb despite gap
    assert isinstance(detected, bool), "Should return boolean despite gaps"
    assert isinstance(intensity, (str, type(None))), "Should return valid intensity or None"


def test_single_spike_not_sustained(default_config, time_index):
    """Test that single spike is not detected as sustained rise"""
    # Single hour spike, not sustained
    flows = pd.Series([10]*5 + [50] + [10]*18, index=time_index)

    detected, intensity = detect_rising_limb(flows, default_config)

    assert detected is False, "Single spike should not be detected as rising limb"
    assert intensity is None, "Intensity should be None for single spike"


# Test Cases: Realistic Hydrographs

def test_snowmelt_hydrograph(default_config):
    """Test detection in typical snowmelt hydrograph pattern"""
    # Gradual morning rise, afternoon peak, evening decline
    times = pd.date_range('2025-05-15 00:00', periods=24, freq='H', tz=pytz.UTC)

    # Baseflow at night, gradual rise during day, peak afternoon, decline evening
    flows = pd.Series([
        15, 15, 15, 15, 15, 15,  # midnight-6am: stable baseflow
        16, 17, 19, 22, 26, 31,  # 6am-12pm: morning rise
        37, 42, 45, 46, 45, 43,  # 12pm-6pm: afternoon peak and start decline
        40, 36, 32, 28, 24, 20   # 6pm-midnight: evening decline
    ], index=times)

    detected, intensity = detect_rising_limb(flows, default_config)

    assert detected is True, "Should detect morning snowmelt rise"
    assert intensity in ["weak", "moderate", "strong"], "Should classify intensity"


def test_stormflow_hydrograph(default_config):
    """Test detection in typical stormflow hydrograph"""
    times = pd.date_range('2025-06-10 00:00', periods=24, freq='H', tz=pytz.UTC)

    # Baseflow → rapid storm rise → peak → recession
    flows = pd.Series([
        20, 20, 20, 20,           # Pre-storm baseflow
        22, 28, 40, 65, 95, 110,  # Storm rising limb (strong)
        115, 112, 105, 95,        # Peak and early recession
        85, 75, 65, 55,           # Continued recession
        48, 42, 38, 35, 32, 30    # Late recession to new baseflow
    ], index=times)

    detected, intensity = detect_rising_limb(flows, default_config)

    assert detected is True, "Should detect storm rising limb"
    assert intensity == "strong", "Storm hydrograph should be strong intensity"


def test_baseflow_recession_no_detection(default_config):
    """Test that baseflow recession does not trigger detection"""
    times = pd.date_range('2025-07-20 00:00', periods=24, freq='H', tz=pytz.UTC)

    # Smooth exponential decay (typical baseflow recession)
    flows = pd.Series([
        50 * np.exp(-0.1 * i) for i in range(24)
    ], index=times)

    detected, intensity = detect_rising_limb(flows, default_config)

    assert detected is False, "Baseflow recession should not trigger detection"
    assert intensity is None, "Intensity should be None during recession"


# Test Cases: Configuration Loading

def test_load_default_config():
    """Test loading configuration from YAML file"""
    config = load_default_config()

    assert isinstance(config, RisingLimbConfig), "Should return RisingLimbConfig instance"
    assert config.min_slope > 0, "min_slope should be positive"
    assert config.min_duration > 0, "min_duration should be positive"
    assert 'weak' in config.intensity_thresholds, "Should have weak threshold"
    assert 'moderate' in config.intensity_thresholds, "Should have moderate threshold"
    assert 'strong' in config.intensity_thresholds, "Should have strong threshold"


def test_config_from_yaml():
    """Test loading configuration from YAML file with species override"""
    config_path = Path(__file__).parent.parent.parent / 'config' / 'thresholds' / 'rising_limb.yaml'

    if not config_path.exists():
        pytest.skip("Config file not found")

    # Load default
    config_default = RisingLimbConfig.from_yaml(config_path)
    assert config_default.min_slope == 0.5, "Should load default min_slope"

    # Load with species override
    config_salmonid = RisingLimbConfig.from_yaml(config_path, species='anadromous_salmonid')
    assert config_salmonid.min_slope == 2.0, "Should apply species override"
    assert config_salmonid.min_duration == 6, "Should apply species override"


# Test Cases: Explanation Generation

def test_explain_detection_detected():
    """Test explanation generation for detected rising limb"""
    explanation = explain_detection(
        detected=True,
        intensity="moderate",
        max_slope=3.5,
        config=RisingLimbConfig(
            min_slope=0.5,
            min_duration=3,
            intensity_thresholds={'weak': 0.5, 'moderate': 2.0, 'strong': 5.0}
        )
    )

    assert "Rising limb detected" in explanation, "Should mention detection"
    assert "moderate" in explanation, "Should mention intensity"
    assert "3.5" in explanation or "3.50" in explanation, "Should mention max slope"


def test_explain_detection_not_detected():
    """Test explanation generation for no detection"""
    config = RisingLimbConfig(
        min_slope=0.5,
        min_duration=3,
        intensity_thresholds={'weak': 0.5, 'moderate': 2.0, 'strong': 5.0}
    )

    explanation = explain_detection(
        detected=False,
        intensity=None,
        config=config
    )

    assert "No" in explanation or "not" in explanation.lower(), "Should indicate no detection"
    assert "0.5" in explanation, "Should mention threshold"
    assert "3" in explanation, "Should mention duration"


# Test Cases: Data Quality

def test_unsorted_time_index(default_config):
    """Test that function handles unsorted time index"""
    times = pd.DatetimeIndex([
        datetime(2025, 1, 1, i, 0, 0, tzinfo=pytz.UTC)
        for i in [0, 2, 1, 3, 4, 5, 6, 7]  # Unsorted: 0,2,1,3,4,5,6,7
    ])
    flows = pd.Series([10, 13, 11, 16, 20, 25, 30, 32], index=times)

    # Should handle unsorted data by sorting internally
    detected, intensity = detect_rising_limb(flows, default_config)

    assert isinstance(detected, bool), "Should return valid result despite unsorted data"


def test_non_datetime_index_raises_error(default_config):
    """Test that non-datetime index raises appropriate error"""
    flows = pd.Series([10, 11, 13, 16, 20, 25, 30], index=range(7))

    with pytest.raises(ValueError, match="DatetimeIndex"):
        detect_rising_limb(flows, default_config)


# Test Cases: Boundary Conditions

def test_exact_threshold_detection(default_config, time_index):
    """Test detection at exact threshold values"""
    # Create flow increase at exactly min_slope for exactly min_duration
    # min_slope = 0.5 m³/s per hour, min_duration = 3 hours
    flows = pd.Series(
        [10, 10, 10.5, 11.0, 11.5] + [11.5]*19,
        index=time_index
    )

    detected, intensity = detect_rising_limb(flows, default_config)

    assert detected is True, "Should detect at exact threshold"


def test_just_below_threshold(default_config, time_index):
    """Test non-detection just below threshold"""
    # Slope just below min_slope (0.4 instead of 0.5)
    flows = pd.Series(
        [10, 10, 10.4, 10.8, 11.2] + [11.2]*19,
        index=time_index
    )

    detected, intensity = detect_rising_limb(flows, default_config)

    assert detected is False, "Should not detect below threshold"


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "--tb=short"])
