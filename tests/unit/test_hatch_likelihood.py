"""
Unit tests for Hatch Likelihood Engine (EPIC 4, Ticket 4.2)

Tests all hatch prediction functions with synthetic data.
"""

import pytest
from datetime import datetime
from src.hatches.likelihood import (
    load_hatch_config,
    check_seasonal_window,
    check_hydrologic_signature,
    compute_hatch_likelihood,
    get_all_hatch_predictions,
    HatchScore,
)


class TestLoadHatchConfig:
    """Test hatch configuration loading."""

    def test_load_green_drake_config(self):
        """Should load green drake config successfully."""
        config = load_hatch_config('green_drake')

        assert config['name'] == "Green Drake"
        assert config['species'] == "Ephemera guttulata"
        assert 'hydrologic_signature' in config
        assert 'temporal_window' in config

    def test_config_has_required_fields(self):
        """Config should have all required hydrologic signature fields."""
        config = load_hatch_config('green_drake')
        sig = config['hydrologic_signature']

        assert 'flow_percentile' in sig
        assert 'rising_limb' in sig
        assert 'velocity' in sig
        assert 'bdi_threshold' in sig

    def test_config_has_temporal_window(self):
        """Config should have temporal window."""
        config = load_hatch_config('green_drake')
        window = config['temporal_window']

        assert 'start_day_of_year' in window
        assert 'end_day_of_year' in window
        assert isinstance(window['start_day_of_year'], int)
        assert isinstance(window['end_day_of_year'], int)

    def test_nonexistent_hatch_raises_error(self):
        """Should raise FileNotFoundError for unknown hatch."""
        with pytest.raises(FileNotFoundError):
            load_hatch_config('unicorn_hatch')


class TestCheckSeasonalWindow:
    """Test seasonal window checking."""

    def setup_method(self):
        """Load config for tests."""
        self.config = load_hatch_config('green_drake')

    def test_in_season_mid_may(self):
        """Mid-May should be in Green Drake season."""
        # Green Drake: days 135-180 (roughly mid-May to late June)
        date = datetime(2025, 5, 20)  # Day 140
        assert check_seasonal_window(date, self.config) is True

    def test_in_season_early_june(self):
        """Early June should be in Green Drake season."""
        date = datetime(2025, 6, 10)  # Day 161
        assert check_seasonal_window(date, self.config) is True

    def test_in_season_late_june(self):
        """Late June should be in Green Drake season."""
        date = datetime(2025, 6, 25)  # Day 176
        assert check_seasonal_window(date, self.config) is True

    def test_out_of_season_winter(self):
        """Winter should be out of season."""
        date = datetime(2025, 12, 25)  # Day 359
        assert check_seasonal_window(date, self.config) is False

    def test_out_of_season_early_spring(self):
        """Early spring should be out of season."""
        date = datetime(2025, 3, 15)  # Day 74
        assert check_seasonal_window(date, self.config) is False

    def test_out_of_season_late_summer(self):
        """Late summer should be out of season."""
        date = datetime(2025, 8, 15)  # Day 227
        assert check_seasonal_window(date, self.config) is False

    def test_edge_case_start_day(self):
        """First day of season should be included."""
        # Day 135 = May 15
        date = datetime(2025, 5, 15)
        assert check_seasonal_window(date, self.config) is True

    def test_edge_case_end_day(self):
        """Last day of season should be included."""
        # Day 180 = June 29
        date = datetime(2025, 6, 29)
        assert check_seasonal_window(date, self.config) is True


class TestCheckHydrologicSignature:
    """Test hydrologic signature matching."""

    def setup_method(self):
        """Load config for tests."""
        self.config = load_hatch_config('green_drake')

    def test_all_conditions_match(self):
        """Perfect Green Drake conditions."""
        hydro_data = {
            'flow_percentile': 65,  # In range 55-80
            'rising_limb': False,  # Allowed: false, weak
            'velocity': 0.6,  # In range 0.4-0.9
            'bdi': 0.75,  # Above threshold 0.65
        }

        matches = check_hydrologic_signature(hydro_data, self.config)

        assert matches['flow_percentile'] is True
        assert matches['rising_limb'] is True
        assert matches['velocity'] is True
        assert matches['bdi'] is True

    def test_flow_too_low(self):
        """Flow below preferred range."""
        hydro_data = {
            'flow_percentile': 40,  # Below min 55
            'rising_limb': False,
            'velocity': 0.6,
            'bdi': 0.75,
        }

        matches = check_hydrologic_signature(hydro_data, self.config)

        assert matches['flow_percentile'] is False
        assert matches['rising_limb'] is True
        assert matches['velocity'] is True
        assert matches['bdi'] is True

    def test_flow_too_high(self):
        """Flow above preferred range."""
        hydro_data = {
            'flow_percentile': 90,  # Above max 80
            'rising_limb': False,
            'velocity': 0.6,
            'bdi': 0.75,
        }

        matches = check_hydrologic_signature(hydro_data, self.config)

        assert matches['flow_percentile'] is False

    def test_rising_limb_not_allowed(self):
        """Strong rising limb not suitable for Green Drake."""
        hydro_data = {
            'flow_percentile': 65,
            'rising_limb': "strong",  # Not in allowed list
            'velocity': 0.6,
            'bdi': 0.75,
        }

        matches = check_hydrologic_signature(hydro_data, self.config)

        assert matches['rising_limb'] is False

    def test_weak_rising_limb_allowed(self):
        """Weak rising limb is acceptable."""
        hydro_data = {
            'flow_percentile': 65,
            'rising_limb': "weak",  # In allowed list
            'velocity': 0.6,
            'bdi': 0.75,
        }

        matches = check_hydrologic_signature(hydro_data, self.config)

        assert matches['rising_limb'] is True

    def test_velocity_too_slow(self):
        """Velocity below preferred range."""
        hydro_data = {
            'flow_percentile': 65,
            'rising_limb': False,
            'velocity': 0.2,  # Below min 0.4
            'bdi': 0.75,
        }

        matches = check_hydrologic_signature(hydro_data, self.config)

        assert matches['velocity'] is False

    def test_velocity_too_fast(self):
        """Velocity above preferred range."""
        hydro_data = {
            'flow_percentile': 65,
            'rising_limb': False,
            'velocity': 1.5,  # Above max 0.9
            'bdi': 0.75,
        }

        matches = check_hydrologic_signature(hydro_data, self.config)

        assert matches['velocity'] is False

    def test_bdi_too_low(self):
        """BDI below threshold."""
        hydro_data = {
            'flow_percentile': 65,
            'rising_limb': False,
            'velocity': 0.6,
            'bdi': 0.5,  # Below threshold 0.65
        }

        matches = check_hydrologic_signature(hydro_data, self.config)

        assert matches['bdi'] is False

    def test_missing_data_uses_defaults(self):
        """Should handle missing data gracefully."""
        hydro_data = {}  # Empty data

        matches = check_hydrologic_signature(hydro_data, self.config)

        # Should not raise, uses defaults
        assert isinstance(matches, dict)
        assert len(matches) == 4


class TestComputeHatchLikelihood:
    """Test overall hatch likelihood computation."""

    def test_very_likely_in_season(self):
        """Perfect conditions in season = very likely."""
        hydro_data = {
            'flow_percentile': 65,
            'rising_limb': False,
            'velocity': 0.6,
            'bdi': 0.75,
        }

        date = datetime(2025, 5, 25)  # In season
        score = compute_hatch_likelihood(12345, 'green_drake', hydro_data, date)

        assert score.likelihood == 1.0  # 4/4 matches
        assert score.rating == "very_likely"
        assert score.in_season is True
        assert score.feature_id == 12345
        assert score.hatch_name == "Green Drake"
        assert score.scientific_name == "Ephemera guttulata"

    def test_likely_three_of_four(self):
        """3 out of 4 conditions = likely."""
        hydro_data = {
            'flow_percentile': 65,  # Match
            'rising_limb': False,  # Match
            'velocity': 0.6,  # Match
            'bdi': 0.5,  # No match (below 0.65)
        }

        date = datetime(2025, 5, 25)
        score = compute_hatch_likelihood(12345, 'green_drake', hydro_data, date)

        assert score.likelihood == 0.75  # 3/4 matches
        assert score.rating == "very_likely"  # >= 0.75

    def test_possible_two_of_four(self):
        """2 out of 4 conditions = possible."""
        hydro_data = {
            'flow_percentile': 65,  # Match
            'rising_limb': "strong",  # No match
            'velocity': 0.6,  # Match
            'bdi': 0.5,  # No match
        }

        date = datetime(2025, 5, 25)
        score = compute_hatch_likelihood(12345, 'green_drake', hydro_data, date)

        assert score.likelihood == 0.5  # 2/4 matches
        assert score.rating == "likely"  # >= 0.5

    def test_unlikely_one_of_four(self):
        """1 out of 4 conditions = unlikely."""
        hydro_data = {
            'flow_percentile': 30,  # No match
            'rising_limb': "strong",  # No match
            'velocity': 0.2,  # No match
            'bdi': 0.75,  # Match
        }

        date = datetime(2025, 5, 25)
        score = compute_hatch_likelihood(12345, 'green_drake', hydro_data, date)

        assert score.likelihood == 0.25  # 1/4 matches
        assert score.rating == "possible"  # >= 0.25

    def test_out_of_season_returns_unlikely(self):
        """Perfect conditions but out of season = unlikely."""
        hydro_data = {
            'flow_percentile': 65,
            'rising_limb': False,
            'velocity': 0.6,
            'bdi': 0.75,
        }

        date = datetime(2025, 12, 25)  # Winter, out of season
        score = compute_hatch_likelihood(12345, 'green_drake', hydro_data, date)

        assert score.likelihood == 0.0
        assert score.rating == "unlikely"
        assert score.in_season is False
        assert "outside" in score.explanation.lower()

    def test_explanation_generated(self):
        """Should generate human-readable explanation."""
        hydro_data = {
            'flow_percentile': 65,
            'rising_limb': False,
            'velocity': 0.6,
            'bdi': 0.75,
        }

        date = datetime(2025, 5, 25)
        score = compute_hatch_likelihood(12345, 'green_drake', hydro_data, date)

        assert len(score.explanation) > 0
        assert "Green Drake" in score.explanation

    def test_hydrologic_match_included(self):
        """Should include detailed condition matches."""
        hydro_data = {
            'flow_percentile': 65,
            'rising_limb': False,
            'velocity': 0.6,
            'bdi': 0.75,
        }

        date = datetime(2025, 5, 25)
        score = compute_hatch_likelihood(12345, 'green_drake', hydro_data, date)

        assert 'flow_percentile' in score.hydrologic_match
        assert 'rising_limb' in score.hydrologic_match
        assert 'velocity' in score.hydrologic_match
        assert 'bdi' in score.hydrologic_match

    def test_deterministic_output(self):
        """Same input should produce same output."""
        hydro_data = {
            'flow_percentile': 65,
            'rising_limb': False,
            'velocity': 0.6,
            'bdi': 0.75,
        }

        date = datetime(2025, 5, 25)
        score1 = compute_hatch_likelihood(12345, 'green_drake', hydro_data, date)
        score2 = compute_hatch_likelihood(12345, 'green_drake', hydro_data, date)

        assert score1.likelihood == score2.likelihood
        assert score1.rating == score2.rating
        assert score1.hydrologic_match == score2.hydrologic_match

    def test_defaults_to_current_date(self):
        """Should default to current date if not specified."""
        hydro_data = {
            'flow_percentile': 65,
            'rising_limb': False,
            'velocity': 0.6,
            'bdi': 0.75,
        }

        # Don't pass current_date
        score = compute_hatch_likelihood(12345, 'green_drake', hydro_data)

        # Should not raise, and date_checked should be set
        assert isinstance(score, HatchScore)
        assert score.date_checked is not None


class TestGetAllHatchPredictions:
    """Test batch hatch predictions."""

    def test_returns_list_of_scores(self):
        """Should return list of hatch scores."""
        hydro_data = {
            'flow_percentile': 65,
            'rising_limb': False,
            'velocity': 0.6,
            'bdi': 0.75,
        }

        date = datetime(2025, 5, 25)
        scores = get_all_hatch_predictions(12345, hydro_data, date)

        assert isinstance(scores, list)
        assert len(scores) > 0
        assert all(isinstance(s, HatchScore) for s in scores)

    def test_includes_green_drake(self):
        """Should include green drake in results."""
        hydro_data = {
            'flow_percentile': 65,
            'rising_limb': False,
            'velocity': 0.6,
            'bdi': 0.75,
        }

        date = datetime(2025, 5, 25)
        scores = get_all_hatch_predictions(12345, hydro_data, date)

        hatch_names = [s.hatch_name for s in scores]
        assert "Green Drake" in hatch_names

    def test_sorted_by_likelihood(self):
        """Results should be sorted by likelihood descending."""
        hydro_data = {
            'flow_percentile': 65,
            'rising_limb': False,
            'velocity': 0.6,
            'bdi': 0.75,
        }

        date = datetime(2025, 5, 25)
        scores = get_all_hatch_predictions(12345, hydro_data, date)

        # Check sorted descending
        likelihoods = [s.likelihood for s in scores]
        assert likelihoods == sorted(likelihoods, reverse=True)


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
