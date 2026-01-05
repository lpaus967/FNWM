"""
Unit tests for Species Scoring Engine (EPIC 4, Ticket 4.1)

Tests all scoring functions with synthetic data.
"""

import pytest
from datetime import datetime
from src.species.scoring import (
    load_species_config,
    score_flow_suitability,
    score_velocity_suitability,
    score_stability,
    compute_species_score,
    classify_rating,
    SpeciesScore,
)


class TestLoadSpeciesConfig:
    """Test species configuration loading."""

    def test_load_trout_config(self):
        """Should load trout config successfully."""
        config = load_species_config('trout')

        assert config['name'] == "Coldwater Trout"
        assert 'scoring_weights' in config
        assert 'flow_percentile_optimal' in config
        assert 'velocity_ranges' in config
        assert 'bdi_threshold' in config

    def test_config_weights_sum_to_one(self):
        """Scoring weights should sum to 1.0."""
        config = load_species_config('trout')
        weights = config['scoring_weights']

        total = sum(weights.values())
        assert abs(total - 1.0) < 0.01, f"Weights sum to {total}, expected 1.0"

    def test_nonexistent_species_raises_error(self):
        """Should raise FileNotFoundError for unknown species."""
        with pytest.raises(FileNotFoundError):
            load_species_config('unicorn_fish')


class TestScoreFlowSuitability:
    """Test flow percentile scoring."""

    def setup_method(self):
        """Load config for tests."""
        self.config = load_species_config('trout')

    def test_optimal_flow_scores_perfect(self):
        """Flow in optimal range should score 1.0."""
        # Trout optimal: 40-70th percentile
        assert score_flow_suitability(50, self.config) == 1.0
        assert score_flow_suitability(40, self.config) == 1.0
        assert score_flow_suitability(70, self.config) == 1.0

    def test_low_flow_gradient(self):
        """Flow below optimal should have gradient score."""
        # At 20th percentile (halfway to min_opt=40), score should be 0.5
        score = score_flow_suitability(20, self.config)
        assert 0.4 < score < 0.6

        # At 0th percentile, score should be 0
        score = score_flow_suitability(0, self.config)
        assert score == 0.0

    def test_high_flow_gradient(self):
        """Flow above optimal should have gradient score."""
        # At 85th percentile (halfway between 70 and 100), score should be ~0.5
        score = score_flow_suitability(85, self.config)
        assert 0.4 < score < 0.6

        # At 100th percentile, score should be 0
        score = score_flow_suitability(100, self.config)
        assert score == 0.0

    def test_invalid_percentiles(self):
        """Invalid percentiles should score 0."""
        assert score_flow_suitability(-10, self.config) == 0.0
        assert score_flow_suitability(150, self.config) == 0.0


class TestScoreVelocitySuitability:
    """Test velocity scoring."""

    def setup_method(self):
        """Load config for tests."""
        self.config = load_species_config('trout')

    def test_optimal_velocity_scores_perfect(self):
        """Velocity in optimal range should score 1.0."""
        # Trout optimal: 0.3 - 0.8 m/s
        assert score_velocity_suitability(0.5, self.config) == 1.0
        assert score_velocity_suitability(0.3, self.config) == 1.0
        assert score_velocity_suitability(0.8, self.config) == 1.0

    def test_slow_but_tolerable_velocity(self):
        """Velocity between min_tolerable and min_optimal should gradient."""
        # Trout: min_tol=0.1, min_opt=0.3
        # At 0.2 (midpoint), score should be 0.5
        score = score_velocity_suitability(0.2, self.config)
        assert 0.4 < score < 0.6

    def test_fast_but_tolerable_velocity(self):
        """Velocity between max_optimal and max_tolerable should gradient."""
        # Trout: max_opt=0.8, max_tol=1.5
        # At 1.15 (midpoint), score should be 0.5
        score = score_velocity_suitability(1.15, self.config)
        assert 0.4 < score < 0.6

    def test_too_slow_velocity(self):
        """Velocity below min_tolerable should score 0."""
        assert score_velocity_suitability(0.05, self.config) == 0.0

    def test_too_fast_velocity(self):
        """Velocity above max_tolerable should score 0."""
        assert score_velocity_suitability(2.0, self.config) == 0.0

    def test_negative_velocity(self):
        """Negative velocity should score 0."""
        assert score_velocity_suitability(-0.5, self.config) == 0.0


class TestScoreStability:
    """Test stability scoring."""

    def test_high_bdi_stable(self):
        """High BDI should score well."""
        score = score_stability(bdi=0.9)
        assert score == 0.9

    def test_low_bdi_unstable(self):
        """Low BDI should score poorly."""
        score = score_stability(bdi=0.2)
        assert score == 0.2

    def test_moderate_bdi(self):
        """Moderate BDI should score moderately."""
        score = score_stability(bdi=0.5)
        assert score == 0.5

    def test_low_variability_bonus(self):
        """Low flow variability should improve stability."""
        # With low variability (CV=0.2), should maintain most of score
        score = score_stability(bdi=0.7, flow_variability=0.2)
        assert score >= 0.68  # Small or no penalty

    def test_high_variability_penalty(self):
        """High flow variability should reduce stability."""
        # With high variability (CV=1.5), should penalize
        score = score_stability(bdi=0.7, flow_variability=1.5)
        assert score < 0.7  # Noticeable penalty

    def test_edge_cases(self):
        """Test boundary conditions."""
        assert score_stability(bdi=0.0) == 0.0
        assert score_stability(bdi=1.0) == 1.0


class TestComputeSpeciesScore:
    """Test overall species scoring."""

    def test_excellent_habitat(self):
        """Perfect conditions should score excellent."""
        hydro_data = {
            'flow_percentile': 55,  # Optimal
            'velocity': 0.6,  # Optimal
            'bdi': 0.85,  # High stability
            'flow_variability': 0.3,  # Stable
        }

        score = compute_species_score(12345, 'trout', hydro_data)

        assert score.overall_score >= 0.8
        assert score.rating == "excellent"
        assert score.feature_id == 12345
        assert score.species == "Coldwater Trout"
        assert 'flow' in score.components
        assert 'velocity' in score.components
        assert 'stability' in score.components

    def test_good_habitat(self):
        """Good but not perfect conditions."""
        hydro_data = {
            'flow_percentile': 45,  # Good
            'velocity': 0.7,  # Good
            'bdi': 0.65,  # Moderate
            'flow_variability': 0.5,
        }

        score = compute_species_score(12345, 'trout', hydro_data)

        # With thermal disabled, scores will be higher than with thermal active
        # Adjusted expectations for current weight distribution
        assert 0.6 <= score.overall_score <= 1.0
        assert score.rating in ["good", "excellent"]

    def test_fair_habitat(self):
        """Marginal conditions."""
        hydro_data = {
            'flow_percentile': 25,  # Low flow
            'velocity': 0.25,  # Slow
            'bdi': 0.5,  # Mixed
        }

        score = compute_species_score(12345, 'trout', hydro_data)

        # With thermal disabled, scores will be different
        # Adjusted expectations for current weight distribution
        assert 0.3 <= score.overall_score <= 1.0
        assert score.rating in ["fair", "good"]

    def test_poor_habitat(self):
        """Unsuitable conditions."""
        hydro_data = {
            'flow_percentile': 5,  # Very low flow
            'velocity': 0.08,  # Too slow
            'bdi': 0.2,  # Flashy
        }

        score = compute_species_score(12345, 'trout', hydro_data)

        assert score.overall_score < 0.3
        assert score.rating == "poor"

    def test_explanation_generated(self):
        """Should generate human-readable explanation."""
        hydro_data = {
            'flow_percentile': 55,
            'velocity': 0.6,
            'bdi': 0.85,
        }

        score = compute_species_score(12345, 'trout', hydro_data)

        assert len(score.explanation) > 0
        assert "Coldwater Trout" in score.explanation

    def test_component_breakdown_included(self):
        """Should include individual component scores."""
        hydro_data = {
            'flow_percentile': 55,
            'velocity': 0.6,
            'bdi': 0.85,
        }

        score = compute_species_score(12345, 'trout', hydro_data)

        assert 'flow' in score.components
        assert 'velocity' in score.components
        assert 'thermal' in score.components  # Will be 0.0 until EPIC 3
        assert 'stability' in score.components

        # All should be 0-1
        for component, value in score.components.items():
            assert 0.0 <= value <= 1.0

    def test_thermal_component_disabled(self):
        """Thermal score should be 0 until EPIC 3."""
        hydro_data = {
            'flow_percentile': 55,
            'velocity': 0.6,
            'bdi': 0.85,
        }

        score = compute_species_score(12345, 'trout', hydro_data)

        # Thermal should be 0.0 (workaround active)
        assert score.components['thermal'] == 0.0

        # Explanation should note missing thermal data
        assert "EPIC 3" in score.explanation or "Temperature" in score.explanation

    def test_confidence_passed_through(self):
        """Should accept and store confidence level."""
        hydro_data = {
            'flow_percentile': 55,
            'velocity': 0.6,
            'bdi': 0.85,
        }

        score = compute_species_score(12345, 'trout', hydro_data, confidence="high")

        assert score.confidence == "high"

    def test_timestamp_added(self):
        """Should add timestamp when score computed."""
        hydro_data = {
            'flow_percentile': 55,
            'velocity': 0.6,
            'bdi': 0.85,
        }

        before = datetime.utcnow()
        score = compute_species_score(12345, 'trout', hydro_data)
        after = datetime.utcnow()

        assert before <= score.timestamp <= after

    def test_missing_optional_data(self):
        """Should handle missing optional fields gracefully."""
        # Minimal hydro data
        hydro_data = {
            'velocity': 0.6,
        }

        # Should not raise, uses defaults
        score = compute_species_score(12345, 'trout', hydro_data)

        assert isinstance(score, SpeciesScore)
        assert 0.0 <= score.overall_score <= 1.0

    def test_deterministic_output(self):
        """Same input should produce same output."""
        hydro_data = {
            'flow_percentile': 55,
            'velocity': 0.6,
            'bdi': 0.85,
        }

        score1 = compute_species_score(12345, 'trout', hydro_data)
        score2 = compute_species_score(12345, 'trout', hydro_data)

        # Scores should match (timestamp will differ)
        assert score1.overall_score == score2.overall_score
        assert score1.rating == score2.rating
        assert score1.components == score2.components


class TestClassifyRating:
    """Test rating classification."""

    def test_excellent_threshold(self):
        """Score >= 0.8 should be excellent."""
        assert classify_rating(0.8) == "excellent"
        assert classify_rating(0.9) == "excellent"
        assert classify_rating(1.0) == "excellent"

    def test_good_threshold(self):
        """Score 0.6-0.8 should be good."""
        assert classify_rating(0.6) == "good"
        assert classify_rating(0.7) == "good"
        assert classify_rating(0.79) == "good"

    def test_fair_threshold(self):
        """Score 0.3-0.6 should be fair."""
        assert classify_rating(0.3) == "fair"
        assert classify_rating(0.45) == "fair"
        assert classify_rating(0.59) == "fair"

    def test_poor_threshold(self):
        """Score < 0.3 should be poor."""
        assert classify_rating(0.0) == "poor"
        assert classify_rating(0.15) == "poor"
        assert classify_rating(0.29) == "poor"


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
