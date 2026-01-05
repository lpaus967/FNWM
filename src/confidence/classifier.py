"""
Confidence Classification Service for FNWM

Translates multiple uncertainty signals into a single, interpretable confidence level.

Confidence signals include:
1. Data source (analysis vs. forecast)
2. Forecast lead time (near-term vs. long-range)
3. Ensemble spread (member agreement/disagreement)
4. Data assimilation strength (nudge magnitude)

The classifier follows a decision tree that prioritizes different signals based on
the forecast type and available data.

Design Principles:
- Deterministic (same inputs → same output)
- Transparent (clear rules, no black box)
- Conservative (when uncertain, default to lower confidence)
- Matches PRD framework exactly
"""

from typing import Literal, Optional, Dict, Any
from pydantic import BaseModel, Field

# Type aliases
ConfidenceLevel = Literal["high", "medium", "low"]
NWMSource = Literal["analysis_assim", "short_range", "medium_range_blend", "analysis_assim_no_da"]


class ConfidenceScore(BaseModel):
    """Confidence assessment for a prediction."""

    confidence: ConfidenceLevel = Field(..., description="Overall confidence level")
    reasoning: str = Field(..., description="Explanation of confidence level")
    signals: Dict[str, Any] = Field(..., description="Input signals used")


def classify_confidence(
    source: str,
    forecast_hour: Optional[int] = None,
    ensemble_spread: Optional[float] = None,
    nudge_magnitude: Optional[float] = None
) -> ConfidenceLevel:
    """
    Classify confidence level based on multiple uncertainty signals.

    Decision logic:
    1. Analysis data (no forecast) = HIGH confidence
    2. Short-range early hours (f001-f003) with low spread = HIGH
    3. Short-range mid hours (f004-f012) with high spread = LOW
    4. Medium-range with very high spread = LOW
    5. Everything else = MEDIUM (conservative default)

    Args:
        source: NWM data source
            - "analysis_assim": Current conditions (assimilated)
            - "short_range": 0-18 hour forecast
            - "medium_range_blend": 1-10 day forecast
            - "analysis_assim_no_da": Current conditions (no assimilation)
        forecast_hour: Forecast lead time (None for analysis)
        ensemble_spread: Coefficient of variation from ensemble members
        nudge_magnitude: Strength of data assimilation adjustment

    Returns:
        Confidence level: "high", "medium", or "low"

    Examples:
        >>> # Analysis data = high confidence
        >>> classify_confidence("analysis_assim")
        'high'

        >>> # Short-range early hours with low spread = high
        >>> classify_confidence("short_range", forecast_hour=2, ensemble_spread=0.10)
        'high'

        >>> # Short-range later hours with high spread = low
        >>> classify_confidence("short_range", forecast_hour=10, ensemble_spread=0.35)
        'low'

        >>> # Medium-range with high spread = low
        >>> classify_confidence("medium_range_blend", ensemble_spread=0.50)
        'low'
    """
    # Rule 1: Analysis data (current conditions) = HIGH confidence
    if source == "analysis_assim":
        return "high"

    # Rule 2: Short-range early hours (f001-f003)
    if source == "short_range" and forecast_hour is not None and forecast_hour <= 3:
        # If ensemble spread is low (members agree), confidence is high
        if ensemble_spread is None or ensemble_spread < 0.15:
            return "high"
        # If spread is moderate to high, confidence is medium
        else:
            return "medium"

    # Rule 3: Short-range mid hours (f004-f012)
    if source == "short_range" and forecast_hour is not None and 4 <= forecast_hour <= 12:
        # If spread is very high (members strongly disagree), confidence is low
        if ensemble_spread is not None and ensemble_spread > 0.30:
            return "low"
        # Otherwise medium
        else:
            return "medium"

    # Rule 4: Short-range late hours (f013-f018)
    if source == "short_range" and forecast_hour is not None and forecast_hour > 12:
        # Late short-range forecast with high spread = low confidence
        if ensemble_spread is not None and ensemble_spread > 0.25:
            return "low"
        # Otherwise medium
        else:
            return "medium"

    # Rule 5: Medium-range blend (1-10 day forecast)
    if source == "medium_range_blend":
        # Very high spread = low confidence
        if ensemble_spread is not None and ensemble_spread > 0.40:
            return "low"
        # Otherwise medium (long-range inherently less certain)
        else:
            return "medium"

    # Rule 6: Non-assimilated analysis (no data assimilation)
    if source == "analysis_assim_no_da":
        # Non-assimilated data is less reliable than assimilated
        # But still current conditions, so medium confidence
        return "medium"

    # Default: MEDIUM (conservative)
    return "medium"


def classify_confidence_with_reasoning(
    source: str,
    forecast_hour: Optional[int] = None,
    ensemble_spread: Optional[float] = None,
    nudge_magnitude: Optional[float] = None
) -> ConfidenceScore:
    """
    Classify confidence and provide reasoning.

    Args:
        source: NWM data source
        forecast_hour: Forecast lead time (hours)
        ensemble_spread: Coefficient of variation
        nudge_magnitude: Data assimilation strength

    Returns:
        ConfidenceScore with level and explanation

    Examples:
        >>> score = classify_confidence_with_reasoning("analysis_assim")
        >>> score.confidence
        'high'
        >>> "current conditions" in score.reasoning.lower()
        True
    """
    confidence = classify_confidence(source, forecast_hour, ensemble_spread, nudge_magnitude)

    # Generate reasoning
    reasoning = generate_confidence_reasoning(
        confidence=confidence,
        source=source,
        forecast_hour=forecast_hour,
        ensemble_spread=ensemble_spread,
        nudge_magnitude=nudge_magnitude
    )

    return ConfidenceScore(
        confidence=confidence,
        reasoning=reasoning,
        signals={
            'source': source,
            'forecast_hour': forecast_hour,
            'ensemble_spread': ensemble_spread,
            'nudge_magnitude': nudge_magnitude
        }
    )


def generate_confidence_reasoning(
    confidence: ConfidenceLevel,
    source: str,
    forecast_hour: Optional[int],
    ensemble_spread: Optional[float],
    nudge_magnitude: Optional[float]
) -> str:
    """
    Generate human-readable explanation of confidence level.

    Args:
        confidence: Classified confidence level
        source: Data source
        forecast_hour: Forecast lead time
        ensemble_spread: Ensemble spread metric
        nudge_magnitude: Data assimilation strength

    Returns:
        Explanation string
    """
    parts = []

    # Start with confidence level
    if confidence == "high":
        parts.append("High confidence:")
    elif confidence == "medium":
        parts.append("Medium confidence:")
    else:
        parts.append("Low confidence:")

    # Add source-specific reasoning
    if source == "analysis_assim":
        parts.append(" Using current conditions with data assimilation.")

    elif source == "analysis_assim_no_da":
        parts.append(" Using current conditions without data assimilation (model-only).")

    elif source == "short_range":
        if forecast_hour is not None:
            if forecast_hour <= 3:
                parts.append(f" Short-range forecast ({forecast_hour}h ahead), near-term timeframe.")
            elif forecast_hour <= 12:
                parts.append(f" Short-range forecast ({forecast_hour}h ahead), mid-range timeframe.")
            else:
                parts.append(f" Short-range forecast ({forecast_hour}h ahead), approaching limits of short-range skill.")
        else:
            parts.append(" Short-range forecast.")

    elif source == "medium_range_blend":
        parts.append(" Medium-range forecast (1-10 days), inherently less certain.")

    # Add ensemble spread reasoning
    if ensemble_spread is not None:
        if ensemble_spread < 0.15:
            parts.append(" Ensemble members show strong agreement.")
        elif ensemble_spread < 0.30:
            parts.append(" Ensemble members show moderate disagreement.")
        else:
            parts.append(f" Ensemble members show significant disagreement (spread={ensemble_spread:.2f}).")

    # Add nudge reasoning if available
    if nudge_magnitude is not None:
        if abs(nudge_magnitude) > 0.5:
            parts.append(f" Large data assimilation adjustment applied (nudge={nudge_magnitude:.1f} m³/s).")

    return "".join(parts)


def get_confidence_thresholds() -> Dict[str, Dict[str, float]]:
    """
    Get confidence classification thresholds.

    Returns thresholds used for ensemble spread classification.

    Returns:
        Dictionary of thresholds

    Examples:
        >>> thresholds = get_confidence_thresholds()
        >>> thresholds['ensemble_spread']['high_confidence_max']
        0.15
    """
    return {
        'ensemble_spread': {
            'high_confidence_max': 0.15,  # CV < 0.15 = high confidence
            'medium_confidence_max': 0.30,  # CV < 0.30 = medium confidence
            'low_confidence_min': 0.30  # CV >= 0.30 = low confidence (depends on context)
        },
        'forecast_hour': {
            'near_term_max': 3,  # f001-f003 = near-term
            'mid_range_max': 12,  # f004-f012 = mid-range
            'long_range_min': 13  # f013+ = long-range (within short_range product)
        }
    }


def interpret_confidence_for_user(confidence: ConfidenceLevel) -> str:
    """
    Generate user-friendly interpretation of confidence level.

    Args:
        confidence: Confidence level

    Returns:
        User-facing interpretation

    Examples:
        >>> interpret_confidence_for_user("high")
        'Trust this prediction - conditions are well-constrained.'
        >>> interpret_confidence_for_user("low")
        'Use caution - conditions are highly uncertain.'
    """
    if confidence == "high":
        return "Trust this prediction - conditions are well-constrained."
    elif confidence == "medium":
        return "Reasonable prediction - some uncertainty exists."
    else:
        return "Use caution - conditions are highly uncertain."


def should_show_prediction(
    confidence: ConfidenceLevel,
    min_confidence: ConfidenceLevel = "medium"
) -> bool:
    """
    Determine if prediction should be shown to user based on confidence.

    Some applications may want to hide low-confidence predictions.

    Args:
        confidence: Confidence level of prediction
        min_confidence: Minimum acceptable confidence

    Returns:
        True if prediction meets minimum confidence threshold

    Examples:
        >>> should_show_prediction("high", min_confidence="medium")
        True
        >>> should_show_prediction("low", min_confidence="medium")
        False
        >>> should_show_prediction("low", min_confidence="low")
        True
    """
    confidence_order = {"high": 3, "medium": 2, "low": 1}

    return confidence_order[confidence] >= confidence_order[min_confidence]
