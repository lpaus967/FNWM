"""
Unit tests for Confidence Classifier (EPIC 5, Ticket 5.2)

Tests all confidence classification functions.
"""

import pytest
from src.confidence.classifier import (
    classify_confidence,
    classify_confidence_with_reasoning,
    get_confidence_thresholds,
    interpret_confidence_for_user,
    should_show_prediction,
    ConfidenceScore,
)


class TestClassifyConfidence:
    """Test confidence classification logic."""

    def test_analysis_assim_high_confidence(self):
        """Analysis data should always be high confidence."""
        assert classify_confidence("analysis_assim") == "high"
        assert classify_confidence("analysis_assim", ensemble_spread=0.50) == "high"

    def test_short_range_early_low_spread(self):
        """Short-range f001-f003 with low spread = high."""
        assert classify_confidence("short_range", forecast_hour=1, ensemble_spread=0.10) == "high"
        assert classify_confidence("short_range", forecast_hour=2, ensemble_spread=0.12) == "high"
        assert classify_confidence("short_range", forecast_hour=3, ensemble_spread=0.14) == "high"

    def test_short_range_early_high_spread(self):
        """Short-range f001-f003 with high spread = medium."""
        assert classify_confidence("short_range", forecast_hour=1, ensemble_spread=0.25) == "medium"
        assert classify_confidence("short_range", forecast_hour=3, ensemble_spread=0.30) == "medium"

    def test_short_range_early_no_spread(self):
        """Short-range f001-f003 with no spread data = high."""
        assert classify_confidence("short_range", forecast_hour=2, ensemble_spread=None) == "high"

    def test_short_range_mid_high_spread(self):
        """Short-range f004-f012 with high spread = low."""
        assert classify_confidence("short_range", forecast_hour=6, ensemble_spread=0.35) == "low"
        assert classify_confidence("short_range", forecast_hour=10, ensemble_spread=0.40) == "low"

    def test_short_range_mid_moderate_spread(self):
        """Short-range f004-f012 with moderate spread = medium."""
        assert classify_confidence("short_range", forecast_hour=6, ensemble_spread=0.20) == "medium"
        assert classify_confidence("short_range", forecast_hour=10, ensemble_spread=0.25) == "medium"

    def test_short_range_mid_no_spread(self):
        """Short-range f004-f012 with no spread data = medium."""
        assert classify_confidence("short_range", forecast_hour=8, ensemble_spread=None) == "medium"

    def test_short_range_late_high_spread(self):
        """Short-range f013+ with high spread = low."""
        assert classify_confidence("short_range", forecast_hour=15, ensemble_spread=0.28) == "low"
        assert classify_confidence("short_range", forecast_hour=18, ensemble_spread=0.30) == "low"

    def test_short_range_late_moderate_spread(self):
        """Short-range f013+ with moderate spread = medium."""
        assert classify_confidence("short_range", forecast_hour=15, ensemble_spread=0.20) == "medium"

    def test_medium_range_very_high_spread(self):
        """Medium-range with very high spread = low."""
        assert classify_confidence("medium_range_blend", ensemble_spread=0.45) == "low"
        assert classify_confidence("medium_range_blend", ensemble_spread=0.60) == "low"

    def test_medium_range_moderate_spread(self):
        """Medium-range with moderate spread = medium."""
        assert classify_confidence("medium_range_blend", ensemble_spread=0.30) == "medium"
        assert classify_confidence("medium_range_blend", ensemble_spread=0.35) == "medium"

    def test_medium_range_no_spread(self):
        """Medium-range with no spread data = medium."""
        assert classify_confidence("medium_range_blend", ensemble_spread=None) == "medium"

    def test_no_da_analysis(self):
        """Non-assimilated analysis = medium."""
        assert classify_confidence("analysis_assim_no_da") == "medium"

    def test_default_medium(self):
        """Unknown source defaults to medium."""
        assert classify_confidence("unknown_source") == "medium"

    def test_edge_case_thresholds(self):
        """Test boundary values for spread thresholds."""
        # f001-f003: 0.15 is threshold
        assert classify_confidence("short_range", forecast_hour=2, ensemble_spread=0.149) == "high"
        assert classify_confidence("short_range", forecast_hour=2, ensemble_spread=0.150) == "medium"

        # f004-f012: 0.30 is threshold
        assert classify_confidence("short_range", forecast_hour=6, ensemble_spread=0.299) == "medium"
        assert classify_confidence("short_range", forecast_hour=6, ensemble_spread=0.301) == "low"

        # medium_range: 0.40 is threshold
        assert classify_confidence("medium_range_blend", ensemble_spread=0.399) == "medium"
        assert classify_confidence("medium_range_blend", ensemble_spread=0.401) == "low"


class TestClassifyConfidenceWithReasoning:
    """Test confidence classification with reasoning."""

    def test_returns_confidence_score(self):
        """Should return ConfidenceScore object."""
        score = classify_confidence_with_reasoning("analysis_assim")

        assert isinstance(score, ConfidenceScore)
        assert score.confidence == "high"
        assert len(score.reasoning) > 0
        assert 'source' in score.signals

    def test_reasoning_mentions_source(self):
        """Reasoning should mention data source."""
        score = classify_confidence_with_reasoning("analysis_assim")
        assert "current conditions" in score.reasoning.lower() or "analysis" in score.reasoning.lower()

        score = classify_confidence_with_reasoning("short_range", forecast_hour=2)
        assert "short-range" in score.reasoning.lower() or "forecast" in score.reasoning.lower()

    def test_reasoning_mentions_ensemble_spread(self):
        """Reasoning should mention ensemble agreement/disagreement."""
        score = classify_confidence_with_reasoning("short_range", forecast_hour=2, ensemble_spread=0.10)
        assert "agreement" in score.reasoning.lower() or "agree" in score.reasoning.lower()

        score = classify_confidence_with_reasoning("short_range", forecast_hour=2, ensemble_spread=0.35)
        assert "disagreement" in score.reasoning.lower() or "disagree" in score.reasoning.lower()

    def test_signals_captured(self):
        """All input signals should be captured."""
        score = classify_confidence_with_reasoning(
            source="short_range",
            forecast_hour=6,
            ensemble_spread=0.25,
            nudge_magnitude=1.5
        )

        assert score.signals['source'] == "short_range"
        assert score.signals['forecast_hour'] == 6
        assert score.signals['ensemble_spread'] == 0.25
        assert score.signals['nudge_magnitude'] == 1.5

    def test_reasoning_mentions_forecast_hour(self):
        """Reasoning should mention forecast lead time."""
        score = classify_confidence_with_reasoning("short_range", forecast_hour=15)
        assert "15" in score.reasoning or "hour" in score.reasoning.lower()


class TestGetConfidenceThresholds:
    """Test confidence threshold retrieval."""

    def test_returns_dict(self):
        """Should return dictionary of thresholds."""
        thresholds = get_confidence_thresholds()

        assert isinstance(thresholds, dict)
        assert 'ensemble_spread' in thresholds
        assert 'forecast_hour' in thresholds

    def test_ensemble_spread_thresholds(self):
        """Should have correct ensemble spread thresholds."""
        thresholds = get_confidence_thresholds()
        spread = thresholds['ensemble_spread']

        assert spread['high_confidence_max'] == 0.15
        assert spread['medium_confidence_max'] == 0.30
        assert spread['low_confidence_min'] == 0.30

    def test_forecast_hour_thresholds(self):
        """Should have correct forecast hour thresholds."""
        thresholds = get_confidence_thresholds()
        hours = thresholds['forecast_hour']

        assert hours['near_term_max'] == 3
        assert hours['mid_range_max'] == 12
        assert hours['long_range_min'] == 13


class TestInterpretConfidenceForUser:
    """Test user-facing confidence interpretation."""

    def test_high_confidence_message(self):
        """High confidence should encourage trust."""
        message = interpret_confidence_for_user("high")

        assert "trust" in message.lower() or "confident" in message.lower()

    def test_medium_confidence_message(self):
        """Medium confidence should be balanced."""
        message = interpret_confidence_for_user("medium")

        assert "reasonable" in message.lower() or "some" in message.lower()

    def test_low_confidence_message(self):
        """Low confidence should warn user."""
        message = interpret_confidence_for_user("low")

        assert "caution" in message.lower() or "uncertain" in message.lower()

    def test_returns_string(self):
        """All outputs should be strings."""
        assert isinstance(interpret_confidence_for_user("high"), str)
        assert isinstance(interpret_confidence_for_user("medium"), str)
        assert isinstance(interpret_confidence_for_user("low"), str)


class TestShouldShowPrediction:
    """Test prediction filtering by confidence."""

    def test_high_meets_all_thresholds(self):
        """High confidence should meet all thresholds."""
        assert should_show_prediction("high", min_confidence="high") is True
        assert should_show_prediction("high", min_confidence="medium") is True
        assert should_show_prediction("high", min_confidence="low") is True

    def test_medium_meets_medium_and_low(self):
        """Medium confidence should meet medium and low thresholds."""
        assert should_show_prediction("medium", min_confidence="high") is False
        assert should_show_prediction("medium", min_confidence="medium") is True
        assert should_show_prediction("medium", min_confidence="low") is True

    def test_low_only_meets_low(self):
        """Low confidence should only meet low threshold."""
        assert should_show_prediction("low", min_confidence="high") is False
        assert should_show_prediction("low", min_confidence="medium") is False
        assert should_show_prediction("low", min_confidence="low") is True

    def test_filtering_use_case(self):
        """Real-world filtering scenario."""
        # Conservative app: only show high confidence
        assert should_show_prediction("high", min_confidence="high") is True
        assert should_show_prediction("medium", min_confidence="high") is False

        # Standard app: show high and medium
        assert should_show_prediction("high", min_confidence="medium") is True
        assert should_show_prediction("medium", min_confidence="medium") is True
        assert should_show_prediction("low", min_confidence="medium") is False

        # Permissive app: show all predictions
        assert should_show_prediction("high", min_confidence="low") is True
        assert should_show_prediction("medium", min_confidence="low") is True
        assert should_show_prediction("low", min_confidence="low") is True


class TestDeterminism:
    """Test that confidence classification is deterministic."""

    def test_same_input_same_output(self):
        """Same inputs should always produce same outputs."""
        result1 = classify_confidence("short_range", forecast_hour=6, ensemble_spread=0.25)
        result2 = classify_confidence("short_range", forecast_hour=6, ensemble_spread=0.25)

        assert result1 == result2

    def test_deterministic_with_reasoning(self):
        """Reasoning should also be deterministic."""
        score1 = classify_confidence_with_reasoning("short_range", forecast_hour=6, ensemble_spread=0.25)
        score2 = classify_confidence_with_reasoning("short_range", forecast_hour=6, ensemble_spread=0.25)

        assert score1.confidence == score2.confidence
        assert score1.reasoning == score2.reasoning


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
