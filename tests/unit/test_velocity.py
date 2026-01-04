"""
Unit Tests for Velocity Suitability Classifier

Tests verify:
1. Correct velocity classification (too_slow/optimal/fast/too_fast)
2. Gradient scoring for sub-optimal velocities
3. Species-aware thresholds
4. Configuration loading from YAML
5. Edge case handling
"""

import pytest
from pathlib import Path
import sys

# Add src to path
src_path = Path(__file__).parent.parent.parent / 'src'
sys.path.insert(0, str(src_path))

from metrics.velocity import (
    SpeciesVelocityConfig,
    classify_velocity,
    compute_gradient_score,
    explain_velocity_suitability,
    load_species_config
)


# Fixtures
@pytest.fixture
def trout_config():
    """Trout velocity configuration"""
    return SpeciesVelocityConfig(
        species_name="Coldwater Trout",
        min_tolerable=0.1,
        max_tolerable=1.5,
        min_optimal=0.3,
        max_optimal=0.8
    )


@pytest.fixture
def strict_config():
    """Stricter velocity requirements (e.g., fry or spawning)"""
    return SpeciesVelocityConfig(
        species_name="Trout Fry",
        min_tolerable=0.05,
        max_tolerable=0.5,
        min_optimal=0.1,
        max_optimal=0.3
    )


# Test Cases: Configuration

def test_config_creation(trout_config):
    """Test configuration object creation"""
    assert trout_config.species_name == "Coldwater Trout"
    assert trout_config.min_tolerable == 0.1
    assert trout_config.max_tolerable == 1.5
    assert trout_config.min_optimal == 0.3
    assert trout_config.max_optimal == 0.8


def test_config_validation_invalid_ranges():
    """Test that invalid range order raises error"""
    with pytest.raises(ValueError, match="must satisfy"):
        # min_optimal > max_optimal (invalid)
        SpeciesVelocityConfig(
            species_name="Invalid",
            min_tolerable=0.1,
            max_tolerable=1.5,
            min_optimal=0.8,
            max_optimal=0.3
        )


def test_load_trout_config():
    """Test loading trout configuration from YAML"""
    config = load_species_config("trout")

    assert config.species_name == "Coldwater Trout"
    assert config.min_tolerable == 0.1
    assert config.max_tolerable == 1.5
    assert config.min_optimal == 0.3
    assert config.max_optimal == 0.8


# Test Cases: Classification - Optimal

def test_classify_optimal_low_end(trout_config):
    """Test classification at low end of optimal range"""
    suitable, classification, score = classify_velocity(0.3, trout_config)

    assert suitable is True
    assert classification == "optimal"
    assert score == 1.0


def test_classify_optimal_mid_range(trout_config):
    """Test classification in middle of optimal range"""
    suitable, classification, score = classify_velocity(0.5, trout_config)

    assert suitable is True
    assert classification == "optimal"
    assert score == 1.0


def test_classify_optimal_high_end(trout_config):
    """Test classification at high end of optimal range"""
    suitable, classification, score = classify_velocity(0.8, trout_config)

    assert suitable is True
    assert classification == "optimal"
    assert score == 1.0


# Test Cases: Classification - Too Slow

def test_classify_too_slow_intolerable(trout_config):
    """Test classification below tolerable minimum"""
    suitable, classification, score = classify_velocity(0.05, trout_config)

    assert suitable is False
    assert classification == "too_slow"
    assert score == 0.0


def test_classify_too_slow_tolerable(trout_config):
    """Test classification slow but tolerable"""
    # 0.2 is between min_tolerable (0.1) and min_optimal (0.3)
    suitable, classification, score = classify_velocity(0.2, trout_config)

    assert suitable is True
    assert classification == "too_slow"
    assert 0.0 < score < 1.0  # Gradient score


def test_classify_zero_velocity(trout_config):
    """Test classification of zero velocity"""
    suitable, classification, score = classify_velocity(0.0, trout_config)

    assert suitable is False
    assert classification == "too_slow"
    assert score == 0.0


# Test Cases: Classification - Too Fast

def test_classify_too_fast_intolerable(trout_config):
    """Test classification above tolerable maximum"""
    suitable, classification, score = classify_velocity(2.0, trout_config)

    assert suitable is False
    assert classification == "too_fast"
    assert score == 0.0


def test_classify_fast_tolerable(trout_config):
    """Test classification fast but tolerable"""
    # 1.0 is between max_optimal (0.8) and max_tolerable (1.5)
    suitable, classification, score = classify_velocity(1.0, trout_config)

    assert suitable is True
    assert classification == "fast"
    assert 0.0 < score < 1.0  # Gradient score


# Test Cases: Gradient Scoring

def test_gradient_score_optimal(trout_config):
    """Test gradient score in optimal range"""
    score = compute_gradient_score(0.5, trout_config)
    assert score == 1.0


def test_gradient_score_slow_side(trout_config):
    """Test gradient score on slow side of optimal"""
    # 0.2 is halfway between min_tolerable (0.1) and min_optimal (0.3)
    score = compute_gradient_score(0.2, trout_config)
    assert abs(score - 0.5) < 0.001


def test_gradient_score_fast_side(trout_config):
    """Test gradient score on fast side of optimal"""
    # 1.15 is halfway between max_optimal (0.8) and max_tolerable (1.5)
    score = compute_gradient_score(1.15, trout_config)
    assert abs(score - 0.5) < 0.001


def test_gradient_score_edge_tolerable_slow(trout_config):
    """Test gradient score at minimum tolerable edge"""
    score = compute_gradient_score(0.1, trout_config)
    assert score == 0.0


def test_gradient_score_edge_tolerable_fast(trout_config):
    """Test gradient score at maximum tolerable edge"""
    score = compute_gradient_score(1.5, trout_config)
    assert score == 0.0


# Test Cases: Species Differences

def test_different_species_different_classification(trout_config, strict_config):
    """Test that same velocity gets different classification for different species"""
    velocity = 0.4

    # For adult trout (0.3-0.8 optimal), 0.4 is optimal
    suitable1, class1, score1 = classify_velocity(velocity, trout_config)
    assert class1 == "optimal"

    # For fry (0.1-0.3 optimal), 0.4 is fast
    suitable2, class2, score2 = classify_velocity(velocity, strict_config)
    assert class2 == "fast"


# Test Cases: Edge Cases

def test_negative_velocity(trout_config):
    """Test handling of negative velocity (shouldn't occur but be defensive)"""
    suitable, classification, score = classify_velocity(-0.5, trout_config)

    # Should be treated as zero
    assert suitable is False
    assert classification == "too_slow"
    assert score == 0.0


def test_very_high_velocity(trout_config):
    """Test handling of extreme velocities"""
    suitable, classification, score = classify_velocity(10.0, trout_config)

    assert suitable is False
    assert classification == "too_fast"
    assert score == 0.0


# Test Cases: Explanation Generation

def test_explain_optimal(trout_config):
    """Test explanation for optimal velocity"""
    explanation = explain_velocity_suitability(
        velocity_ms=0.5,
        suitable=True,
        classification="optimal",
        score=1.0,
        species_name=trout_config.species_name
    )

    assert "0.50 m/s" in explanation
    assert "optimal" in explanation.lower()
    assert "Coldwater Trout" in explanation


def test_explain_too_slow(trout_config):
    """Test explanation for too slow velocity"""
    explanation = explain_velocity_suitability(
        velocity_ms=0.05,
        suitable=False,
        classification="too_slow",
        score=0.0,
        species_name=trout_config.species_name
    )

    assert "0.05 m/s" in explanation
    assert "too slow" in explanation.lower()


def test_explain_too_fast(trout_config):
    """Test explanation for too fast velocity"""
    explanation = explain_velocity_suitability(
        velocity_ms=2.0,
        suitable=False,
        classification="too_fast",
        score=0.0,
        species_name=trout_config.species_name
    )

    assert "2.00 m/s" in explanation
    assert "too fast" in explanation.lower()


# Test Cases: Boundary Conditions

def test_exact_min_tolerable(trout_config):
    """Test at exact minimum tolerable boundary"""
    suitable, classification, score = classify_velocity(0.1, trout_config)

    assert suitable is True  # At boundary, should be tolerable
    assert classification == "too_slow"
    assert score == 0.0


def test_exact_max_tolerable(trout_config):
    """Test at exact maximum tolerable boundary"""
    suitable, classification, score = classify_velocity(1.5, trout_config)

    assert suitable is True  # At boundary, should be tolerable
    assert classification == "fast"
    assert score == 0.0


def test_exact_min_optimal(trout_config):
    """Test at exact minimum optimal boundary"""
    suitable, classification, score = classify_velocity(0.3, trout_config)

    assert suitable is True
    assert classification == "optimal"
    assert score == 1.0


def test_exact_max_optimal(trout_config):
    """Test at exact maximum optimal boundary"""
    suitable, classification, score = classify_velocity(0.8, trout_config)

    assert suitable is True
    assert classification == "optimal"
    assert score == 1.0


def test_just_below_min_optimal(trout_config):
    """Test just below minimum optimal"""
    suitable, classification, score = classify_velocity(0.29, trout_config)

    assert suitable is True
    assert classification == "too_slow"
    assert score > 0.9  # Very close to optimal


def test_just_above_max_optimal(trout_config):
    """Test just above maximum optimal"""
    suitable, classification, score = classify_velocity(0.81, trout_config)

    assert suitable is True
    assert classification == "fast"
    assert score > 0.9  # Very close to optimal


# Test Cases: Real-World Scenarios

def test_riffle_habitat(trout_config):
    """Test typical riffle velocity (0.5-0.7 m/s)"""
    velocities = [0.5, 0.6, 0.7]

    for v in velocities:
        suitable, classification, score = classify_velocity(v, trout_config)
        assert suitable is True
        assert classification == "optimal"
        assert score == 1.0


def test_pool_habitat(trout_config):
    """Test typical pool velocity (0.1-0.3 m/s)"""
    # Low end of range
    suitable, classification, score = classify_velocity(0.15, trout_config)
    assert suitable is True
    assert classification == "too_slow"

    # Upper end (optimal)
    suitable, classification, score = classify_velocity(0.3, trout_config)
    assert suitable is True
    assert classification == "optimal"


def test_high_flow_event(trout_config):
    """Test velocities during high flow event"""
    # Moderate high flow (tolerable)
    suitable, classification, score = classify_velocity(1.2, trout_config)
    assert suitable is True
    assert classification == "fast"

    # Extreme high flow (too fast)
    suitable, classification, score = classify_velocity(3.0, trout_config)
    assert suitable is False
    assert classification == "too_fast"


def test_stagnant_conditions(trout_config):
    """Test very low velocity (stagnant pool)"""
    suitable, classification, score = classify_velocity(0.02, trout_config)

    assert suitable is False
    assert classification == "too_slow"
    assert score == 0.0


# Test Cases: Score Monotonicity

def test_score_increases_toward_optimal_from_low():
    """Property: Score should increase as velocity approaches optimal from below"""
    config = SpeciesVelocityConfig("Test", 0.1, 1.5, 0.3, 0.8)

    velocities = [0.1, 0.15, 0.2, 0.25, 0.29, 0.3]
    scores = [classify_velocity(v, config)[2] for v in velocities]

    # Scores should be monotonically increasing
    for i in range(len(scores) - 1):
        assert scores[i] <= scores[i+1], f"Score should increase: {scores}"


def test_score_decreases_away_from_optimal_above():
    """Property: Score should decrease as velocity increases above optimal"""
    config = SpeciesVelocityConfig("Test", 0.1, 1.5, 0.3, 0.8)

    velocities = [0.8, 0.9, 1.0, 1.2, 1.5]
    scores = [classify_velocity(v, config)[2] for v in velocities]

    # Scores should be monotonically decreasing
    for i in range(len(scores) - 1):
        assert scores[i] >= scores[i+1], f"Score should decrease: {scores}"


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "--tb=short"])
