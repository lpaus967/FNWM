"""Confidence and uncertainty quantification module for FNWM."""

from .ensemble import (
    EnsembleSpread,
    compute_ensemble_spread,
    compute_ensemble_spread_timeseries,
    classify_spread_level,
    interpret_ensemble_spread,
    compute_spread_statistics,
)

from .classifier import (
    ConfidenceScore,
    classify_confidence,
    classify_confidence_with_reasoning,
    get_confidence_thresholds,
    interpret_confidence_for_user,
    should_show_prediction,
)

__all__ = [
    # Ensemble spread
    'EnsembleSpread',
    'compute_ensemble_spread',
    'compute_ensemble_spread_timeseries',
    'classify_spread_level',
    'interpret_ensemble_spread',
    'compute_spread_statistics',
    # Confidence classification
    'ConfidenceScore',
    'classify_confidence',
    'classify_confidence_with_reasoning',
    'get_confidence_thresholds',
    'interpret_confidence_for_user',
    'should_show_prediction',
]
