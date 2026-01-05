"""
Unit tests for Ensemble Spread Calculator (EPIC 5, Ticket 5.1)

Tests all ensemble spread functions with synthetic data.
"""

import pytest
import numpy as np
from src.confidence.ensemble import (
    compute_ensemble_spread,
    compute_ensemble_spread_timeseries,
    classify_spread_level,
    interpret_ensemble_spread,
    compute_spread_statistics,
    EnsembleSpread,
)


class TestComputeEnsembleSpread:
    """Test ensemble spread calculation."""

    def test_low_spread_agreement(self):
        """Members in strong agreement should have low spread."""
        flows = [10.0, 10.2, 9.8, 10.1, 9.9, 10.0]
        spread = compute_ensemble_spread(flows)

        assert spread.spread_metric < 0.15
        assert 9.5 < spread.mean_flow < 10.5
        assert spread.num_members == 6

    def test_high_spread_disagreement(self):
        """Members in disagreement should have high spread."""
        flows = [5.0, 10.0, 15.0, 8.0, 12.0, 20.0]
        spread = compute_ensemble_spread(flows)

        assert spread.spread_metric > 0.30
        assert spread.num_members == 6

    def test_moderate_spread(self):
        """Moderate disagreement."""
        flows = [7.0, 10.0, 13.0, 9.0, 11.0, 10.0]  # Wider spread
        spread = compute_ensemble_spread(flows)

        assert 0.15 <= spread.spread_metric <= 0.30

    def test_zero_spread_perfect_agreement(self):
        """All members identical should have zero spread."""
        flows = [10.0, 10.0, 10.0, 10.0, 10.0]
        spread = compute_ensemble_spread(flows)

        assert spread.spread_metric == 0.0
        assert spread.std_flow == 0.0
        assert spread.range_flow == 0.0

    def test_all_zero_flows(self):
        """All zero flows should be handled gracefully."""
        flows = [0.0, 0.0, 0.0, 0.0]
        spread = compute_ensemble_spread(flows)

        assert spread.spread_metric == 0.0
        assert spread.mean_flow == 0.0
        assert spread.min_flow == 0.0
        assert spread.max_flow == 0.0

    def test_single_member(self):
        """Single member should work (spread = 0)."""
        flows = [10.0]
        spread = compute_ensemble_spread(flows)

        assert spread.spread_metric == 0.0
        assert spread.mean_flow == 10.0
        assert spread.num_members == 1

    def test_two_members(self):
        """Two members should compute spread correctly."""
        flows = [8.0, 12.0]
        spread = compute_ensemble_spread(flows)

        assert spread.mean_flow == 10.0
        assert spread.range_flow == 4.0
        assert spread.num_members == 2

    def test_negative_flows_handled(self):
        """Negative flows should be filtered to zero."""
        flows = [10.0, -5.0, 12.0, -2.0]
        spread = compute_ensemble_spread(flows)

        # Negative values treated as 0
        assert spread.min_flow == 0.0
        assert spread.num_members == 4

    def test_empty_list_raises_error(self):
        """Empty member list should raise ValueError."""
        with pytest.raises(ValueError):
            compute_ensemble_spread([])

    def test_statistics_computed_correctly(self):
        """Verify statistical calculations."""
        flows = [8.0, 10.0, 12.0]
        spread = compute_ensemble_spread(flows)

        assert spread.mean_flow == 10.0
        assert spread.min_flow == 8.0
        assert spread.max_flow == 12.0
        assert spread.range_flow == 4.0
        assert spread.std_flow == pytest.approx(1.633, abs=0.01)

    def test_coefficient_of_variation(self):
        """CV should be std/mean."""
        flows = [10.0, 15.0, 20.0]
        spread = compute_ensemble_spread(flows)

        expected_cv = spread.std_flow / spread.mean_flow
        assert spread.spread_metric == pytest.approx(expected_cv, abs=0.001)

    def test_large_ensemble(self):
        """Should handle large ensembles."""
        np.random.seed(42)
        flows = np.random.normal(loc=10.0, scale=2.0, size=100).tolist()
        spread = compute_ensemble_spread(flows)

        assert spread.num_members == 100
        assert 9.0 < spread.mean_flow < 11.0
        assert 0.15 < spread.spread_metric < 0.25


class TestComputeEnsembleSpreadTimeseries:
    """Test timeseries ensemble spread computation."""

    def test_simple_timeseries(self):
        """Should compute spread for each timestep."""
        timeseries = {
            'mem1': [10.0, 10.5, 11.0],
            'mem2': [9.8, 10.2, 10.8],
            'mem3': [10.2, 10.7, 11.2]
        }

        spreads = compute_ensemble_spread_timeseries(timeseries)

        assert len(spreads) == 3
        assert all(isinstance(s, EnsembleSpread) for s in spreads.values())

    def test_timestep_independence(self):
        """Each timestep should be computed independently."""
        timeseries = {
            'mem1': [10.0, 20.0],  # Low at t=0, high at t=1
            'mem2': [10.1, 5.0],   # Low at t=0, low at t=1
        }

        spreads = compute_ensemble_spread_timeseries(timeseries)

        # t=0: both near 10, low spread
        assert spreads[0].spread_metric < 0.15

        # t=1: 20 vs 5, high spread
        assert spreads[1].spread_metric > 0.50

    def test_empty_timeseries(self):
        """Empty timeseries should return empty dict."""
        spreads = compute_ensemble_spread_timeseries({})
        assert spreads == {}

    def test_mismatched_lengths_raises_error(self):
        """Members with different lengths should raise error."""
        timeseries = {
            'mem1': [10.0, 10.5, 11.0],
            'mem2': [9.8, 10.2]  # Missing third value
        }

        with pytest.raises(ValueError):
            compute_ensemble_spread_timeseries(timeseries)

    def test_single_timestep(self):
        """Single timestep should work."""
        timeseries = {
            'mem1': [10.0],
            'mem2': [9.8],
            'mem3': [10.2]
        }

        spreads = compute_ensemble_spread_timeseries(timeseries)

        assert len(spreads) == 1
        assert 0 in spreads


class TestClassifySpreadLevel:
    """Test spread level classification."""

    def test_low_spread_threshold(self):
        """CV < 0.15 should be low."""
        assert classify_spread_level(0.10) == "low"
        assert classify_spread_level(0.05) == "low"
        assert classify_spread_level(0.14) == "low"

    def test_moderate_spread_threshold(self):
        """CV 0.15-0.30 should be moderate."""
        assert classify_spread_level(0.15) == "moderate"
        assert classify_spread_level(0.20) == "moderate"
        assert classify_spread_level(0.29) == "moderate"

    def test_high_spread_threshold(self):
        """CV >= 0.30 should be high."""
        assert classify_spread_level(0.30) == "high"
        assert classify_spread_level(0.50) == "high"
        assert classify_spread_level(1.00) == "high"

    def test_zero_spread(self):
        """Zero spread should be low."""
        assert classify_spread_level(0.0) == "low"

    def test_edge_cases(self):
        """Test boundary values."""
        assert classify_spread_level(0.149) == "low"
        assert classify_spread_level(0.150) == "moderate"
        assert classify_spread_level(0.299) == "moderate"
        assert classify_spread_level(0.300) == "high"


class TestInterpretEnsembleSpread:
    """Test spread interpretation."""

    def test_low_spread_interpretation(self):
        """Low spread should mention agreement."""
        spread = EnsembleSpread(
            spread_metric=0.10,
            mean_flow=10.0,
            std_flow=1.0,
            min_flow=9.0,
            max_flow=11.0,
            range_flow=2.0,
            num_members=6
        )

        interp = interpret_ensemble_spread(spread)

        assert "agreement" in interp.lower() or "agree" in interp.lower()
        assert "high confidence" in interp.lower()

    def test_high_spread_interpretation(self):
        """High spread should mention disagreement."""
        spread = EnsembleSpread(
            spread_metric=0.50,
            mean_flow=10.0,
            std_flow=5.0,
            min_flow=5.0,
            max_flow=15.0,
            range_flow=10.0,
            num_members=6
        )

        interp = interpret_ensemble_spread(spread)

        assert "disagreement" in interp.lower() or "disagree" in interp.lower()
        assert "low confidence" in interp.lower() or "uncertain" in interp.lower()

    def test_interpretation_includes_values(self):
        """Interpretation should include numeric values."""
        spread = EnsembleSpread(
            spread_metric=0.20,
            mean_flow=12.5,
            std_flow=2.5,
            min_flow=10.0,
            max_flow=15.0,
            range_flow=5.0,
            num_members=6
        )

        interp = interpret_ensemble_spread(spread)

        assert "12.5" in interp or "mean" in interp.lower()
        assert "10.0" in interp or "15.0" in interp


class TestComputeSpreadStatistics:
    """Test spread statistics computation."""

    def test_statistics_across_timesteps(self):
        """Should compute mean, max, min, std of spread values."""
        spread1 = EnsembleSpread(
            spread_metric=0.10, mean_flow=10.0, std_flow=1.0,
            min_flow=9.0, max_flow=11.0, range_flow=2.0, num_members=3
        )
        spread2 = EnsembleSpread(
            spread_metric=0.20, mean_flow=12.0, std_flow=2.4,
            min_flow=10.0, max_flow=14.0, range_flow=4.0, num_members=3
        )
        spread3 = EnsembleSpread(
            spread_metric=0.30, mean_flow=15.0, std_flow=4.5,
            min_flow=12.0, max_flow=18.0, range_flow=6.0, num_members=3
        )

        stats = compute_spread_statistics({0: spread1, 1: spread2, 2: spread3})

        assert stats['mean_spread'] == pytest.approx(0.20, abs=0.001)
        assert stats['min_spread'] == 0.10
        assert stats['max_spread'] == 0.30
        assert stats['std_spread'] == pytest.approx(0.0816, abs=0.01)

    def test_empty_spreads(self):
        """Empty spreads should return zeros."""
        stats = compute_spread_statistics({})

        assert stats['mean_spread'] == 0.0
        assert stats['max_spread'] == 0.0
        assert stats['min_spread'] == 0.0
        assert stats['std_spread'] == 0.0

    def test_single_spread(self):
        """Single spread should work."""
        spread = EnsembleSpread(
            spread_metric=0.15, mean_flow=10.0, std_flow=1.5,
            min_flow=9.0, max_flow=11.0, range_flow=2.0, num_members=3
        )

        stats = compute_spread_statistics({0: spread})

        assert stats['mean_spread'] == 0.15
        assert stats['max_spread'] == 0.15
        assert stats['min_spread'] == 0.15
        assert stats['std_spread'] == 0.0  # No variation


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
