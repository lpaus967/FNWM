"""
Ensemble Spread Calculator for FNWM

Quantifies forecast disagreement among ensemble members to assess prediction uncertainty.

The National Water Model provides ensemble forecasts (multiple realizations) for
medium-range predictions. When ensemble members agree, confidence is high. When they
disagree (high spread), confidence is low.

Key Metrics:
- Coefficient of Variation (CV): std/mean - normalized measure of spread
- Range: max - min - absolute spread magnitude
- Standard deviation: variability across members

Design Principles:
- Handles edge cases (zero flow, single member, missing data)
- Normalized metrics for comparability across reaches
- Efficient computation for real-time use
- Clear interpretation for confidence classification
"""

from typing import List, Dict, Any, Optional
import numpy as np
from pydantic import BaseModel, Field


class EnsembleSpread(BaseModel):
    """Ensemble forecast spread statistics."""

    spread_metric: float = Field(..., ge=0.0, description="Coefficient of variation (std/mean)")
    mean_flow: float = Field(..., ge=0.0, description="Mean flow across ensemble (m³/s)")
    std_flow: float = Field(..., ge=0.0, description="Standard deviation (m³/s)")
    min_flow: float = Field(..., ge=0.0, description="Minimum ensemble member flow (m³/s)")
    max_flow: float = Field(..., ge=0.0, description="Maximum ensemble member flow (m³/s)")
    range_flow: float = Field(..., ge=0.0, description="Range (max - min) (m³/s)")
    num_members: int = Field(..., ge=1, description="Number of ensemble members")


def compute_ensemble_spread(
    member_flows: List[float]
) -> EnsembleSpread:
    """
    Compute ensemble spread statistics from member flows.

    The spread metric (coefficient of variation) normalizes variability by the mean,
    allowing comparison across different flow magnitudes:
    - CV < 0.15: Low disagreement (high confidence)
    - CV 0.15-0.30: Moderate disagreement (medium confidence)
    - CV > 0.30: High disagreement (low confidence)

    Args:
        member_flows: List of streamflow values from ensemble members (m³/s)

    Returns:
        EnsembleSpread object with spread statistics

    Raises:
        ValueError: If member_flows is empty

    Examples:
        >>> # Low spread (members agree)
        >>> flows = [10.0, 10.2, 9.8, 10.1, 9.9, 10.0]
        >>> spread = compute_ensemble_spread(flows)
        >>> spread.spread_metric < 0.15
        True

        >>> # High spread (members disagree)
        >>> flows = [5.0, 10.0, 15.0, 8.0, 12.0, 20.0]
        >>> spread = compute_ensemble_spread(flows)
        >>> spread.spread_metric > 0.30
        True
    """
    if not member_flows:
        raise ValueError("member_flows cannot be empty")

    # Filter out negative values (shouldn't occur, but be defensive)
    valid_flows = [max(0.0, f) for f in member_flows]

    # Handle case where all flows are zero
    if all(f == 0.0 for f in valid_flows):
        return EnsembleSpread(
            spread_metric=0.0,
            mean_flow=0.0,
            std_flow=0.0,
            min_flow=0.0,
            max_flow=0.0,
            range_flow=0.0,
            num_members=len(valid_flows)
        )

    # Compute statistics
    mean_flow = float(np.mean(valid_flows))
    std_flow = float(np.std(valid_flows, ddof=0))  # Population std
    min_flow = float(np.min(valid_flows))
    max_flow = float(np.max(valid_flows))
    range_flow = max_flow - min_flow

    # Compute coefficient of variation (normalized spread)
    # CV = std / mean (only if mean > 0)
    if mean_flow > 0:
        spread_metric = std_flow / mean_flow
    else:
        # Edge case: mean is zero but some members might be non-zero
        # Use range as fallback
        spread_metric = 1.0 if range_flow > 0 else 0.0

    return EnsembleSpread(
        spread_metric=spread_metric,
        mean_flow=mean_flow,
        std_flow=std_flow,
        min_flow=min_flow,
        max_flow=max_flow,
        range_flow=range_flow,
        num_members=len(valid_flows)
    )


def compute_ensemble_spread_timeseries(
    member_timeseries: Dict[str, List[float]]
) -> Dict[int, EnsembleSpread]:
    """
    Compute ensemble spread for each timestep in a forecast.

    Args:
        member_timeseries: Dictionary mapping member names to flow timeseries
            Example: {
                'mem1': [10.0, 10.5, 11.0],
                'mem2': [9.8, 10.2, 10.8],
                ...
            }

    Returns:
        Dictionary mapping timestep index to EnsembleSpread object

    Examples:
        >>> timeseries = {
        ...     'mem1': [10.0, 10.5, 11.0],
        ...     'mem2': [9.8, 10.2, 10.8],
        ...     'mem3': [10.2, 10.7, 11.2]
        ... }
        >>> spreads = compute_ensemble_spread_timeseries(timeseries)
        >>> len(spreads)
        3
    """
    if not member_timeseries:
        return {}

    # Get number of timesteps from first member
    first_member = list(member_timeseries.values())[0]
    num_timesteps = len(first_member)

    # Validate all members have same length
    for member_name, values in member_timeseries.items():
        if len(values) != num_timesteps:
            raise ValueError(
                f"All ensemble members must have same length. "
                f"{member_name} has {len(values)}, expected {num_timesteps}"
            )

    # Compute spread for each timestep
    spreads = {}
    for t in range(num_timesteps):
        # Gather all member values at timestep t
        flows_at_t = [values[t] for values in member_timeseries.values()]
        spreads[t] = compute_ensemble_spread(flows_at_t)

    return spreads


def classify_spread_level(spread_metric: float) -> str:
    """
    Classify ensemble spread into categorical levels.

    Args:
        spread_metric: Coefficient of variation (CV)

    Returns:
        Spread level: "low", "moderate", or "high"

    Examples:
        >>> classify_spread_level(0.10)
        'low'
        >>> classify_spread_level(0.25)
        'moderate'
        >>> classify_spread_level(0.50)
        'high'
    """
    if spread_metric < 0.15:
        return "low"
    elif spread_metric < 0.30:
        return "moderate"
    else:
        return "high"


def interpret_ensemble_spread(spread: EnsembleSpread) -> str:
    """
    Generate human-readable interpretation of ensemble spread.

    Args:
        spread: EnsembleSpread object

    Returns:
        Interpretation string

    Examples:
        >>> spread = EnsembleSpread(
        ...     spread_metric=0.10,
        ...     mean_flow=10.0,
        ...     std_flow=1.0,
        ...     min_flow=9.0,
        ...     max_flow=11.0,
        ...     range_flow=2.0,
        ...     num_members=6
        ... )
        >>> interp = interpret_ensemble_spread(spread)
        >>> "agree" in interp.lower()
        True
    """
    level = classify_spread_level(spread.spread_metric)

    if level == "low":
        intro = "Ensemble members show strong agreement"
    elif level == "moderate":
        intro = "Ensemble members show moderate disagreement"
    else:
        intro = "Ensemble members show significant disagreement"

    # Add details
    details = (
        f" (mean: {spread.mean_flow:.1f} m³/s, "
        f"range: {spread.min_flow:.1f}-{spread.max_flow:.1f} m³/s, "
        f"CV: {spread.spread_metric:.2f})"
    )

    # Recommendation
    if level == "low":
        recommendation = "High confidence in forecast."
    elif level == "moderate":
        recommendation = "Moderate confidence in forecast."
    else:
        recommendation = "Low confidence in forecast - conditions uncertain."

    return intro + details + ". " + recommendation


def compute_spread_statistics(
    spreads: Dict[int, EnsembleSpread]
) -> Dict[str, float]:
    """
    Compute summary statistics across multiple timesteps.

    Useful for assessing overall forecast quality.

    Args:
        spreads: Dictionary mapping timesteps to EnsembleSpread objects

    Returns:
        Dictionary with summary statistics

    Examples:
        >>> spread1 = EnsembleSpread(
        ...     spread_metric=0.10, mean_flow=10.0, std_flow=1.0,
        ...     min_flow=9.0, max_flow=11.0, range_flow=2.0, num_members=3
        ... )
        >>> spread2 = EnsembleSpread(
        ...     spread_metric=0.20, mean_flow=12.0, std_flow=2.4,
        ...     min_flow=10.0, max_flow=14.0, range_flow=4.0, num_members=3
        ... )
        >>> stats = compute_spread_statistics({0: spread1, 1: spread2})
        >>> stats['mean_spread']
        0.15
    """
    if not spreads:
        return {
            'mean_spread': 0.0,
            'max_spread': 0.0,
            'min_spread': 0.0,
            'std_spread': 0.0
        }

    spread_values = [s.spread_metric for s in spreads.values()]

    return {
        'mean_spread': float(np.mean(spread_values)),
        'max_spread': float(np.max(spread_values)),
        'min_spread': float(np.min(spread_values)),
        'std_spread': float(np.std(spread_values))
    }
