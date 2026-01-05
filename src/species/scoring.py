"""
Species Scoring Engine for FNWM

Computes species-specific habitat suitability scores based on hydrologic conditions.

The scoring engine combines multiple habitat components:
- Flow suitability (flow percentile relative to optimal range)
- Velocity suitability (from EPIC 2 velocity classifier)
- Thermal suitability (from EPIC 3 TSI - currently disabled, see TODO)
- Stability (based on BDI and flow variability)

Design Principles:
- Config-driven (no hardcoded thresholds)
- Deterministic and reproducible
- Explainable (generates human-readable explanations)
- Auditable (component breakdown provided)

IMPORTANT: Temperature integration pending EPIC 3
See docs/development/epic-4-thermal-workaround.md for details
"""

from typing import Literal, Optional, Dict, Any
from pathlib import Path
from datetime import datetime
import yaml
from pydantic import BaseModel, Field

# Type aliases
Rating = Literal["poor", "fair", "good", "excellent"]


class SpeciesScore(BaseModel):
    """Species habitat suitability score."""

    overall_score: float = Field(..., ge=0.0, le=1.0, description="Overall habitat score (0-1)")
    rating: Rating = Field(..., description="Qualitative rating")
    components: Dict[str, float] = Field(..., description="Individual component scores")
    explanation: str = Field(..., description="Human-readable explanation")
    confidence: str = Field(..., description="Confidence level (high/medium/low)")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="When score was computed")
    species: str = Field(..., description="Species name")
    feature_id: int = Field(..., description="NHD reach feature_id")


def load_species_config(species: str) -> Dict[str, Any]:
    """
    Load species configuration from YAML file.

    Args:
        species: Species identifier (e.g., 'trout', 'bass', 'salmon')

    Returns:
        Configuration dictionary with scoring parameters

    Raises:
        FileNotFoundError: If species config file doesn't exist
        ValueError: If config is invalid

    Examples:
        >>> config = load_species_config('trout')
        >>> config['name']
        'Coldwater Trout'
    """
    config_path = Path(__file__).parent.parent.parent / "config" / "species" / f"{species}.yaml"

    if not config_path.exists():
        raise FileNotFoundError(
            f"Species config not found: {config_path}\n"
            f"Available species: trout"
        )

    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)

    # Validate required fields
    required = ['name', 'scoring_weights', 'flow_percentile_optimal', 'velocity_ranges', 'bdi_threshold']
    missing = [field for field in required if field not in config]
    if missing:
        raise ValueError(f"Invalid config for {species}: missing fields {missing}")

    # Validate weights sum to 1.0 (within tolerance)
    weights = config['scoring_weights']
    total = sum(weights.values())
    if abs(total - 1.0) > 0.01:
        raise ValueError(f"Scoring weights must sum to 1.0, got {total}")

    return config


def score_flow_suitability(flow_percentile: float, config: Dict[str, Any]) -> float:
    """
    Score flow suitability based on flow percentile.

    Uses trapezoidal membership function:
    - 0.0 for very low or very high flow
    - 1.0 for flow in optimal range
    - Linear gradient in between

    Args:
        flow_percentile: Flow percentile (0-100)
        config: Species configuration dict

    Returns:
        Flow suitability score (0-1)

    Examples:
        >>> config = {'flow_percentile_optimal': {'min': 40, 'max': 70}}
        >>> score_flow_suitability(55, config)  # Mid-optimal range
        1.0
        >>> score_flow_suitability(25, config)  # Below optimal
        0.625
        >>> score_flow_suitability(5, config)   # Very low flow
        0.125
    """
    optimal = config['flow_percentile_optimal']
    min_opt = optimal['min']
    max_opt = optimal['max']

    # Handle edge cases
    if flow_percentile < 0 or flow_percentile > 100:
        return 0.0

    # Optimal range: score = 1.0
    if min_opt <= flow_percentile <= max_opt:
        return 1.0

    # Below optimal: linear gradient from 0 to min_opt
    if flow_percentile < min_opt:
        # Score decreases as we get further from optimal
        # At 0th percentile, score is min_opt/100 (e.g., 40/100 = 0.4)
        # At min_opt, score is 1.0
        return flow_percentile / min_opt

    # Above optimal: linear gradient from max_opt to 100
    if flow_percentile > max_opt:
        # Score decreases as we get further from optimal
        # At 100th percentile, score is (100-max_opt)/100 (e.g., (100-70)/100 = 0.3)
        # At max_opt, score is 1.0
        return (100 - flow_percentile) / (100 - max_opt)

    return 0.0  # Fallback


def score_velocity_suitability(velocity_ms: float, config: Dict[str, Any]) -> float:
    """
    Score velocity suitability for species.

    Uses trapezoidal membership function based on species velocity ranges.

    Args:
        velocity_ms: Velocity in m/s
        config: Species configuration dict

    Returns:
        Velocity suitability score (0-1)

    Examples:
        >>> config = {
        ...     'velocity_ranges': {
        ...         'min_optimal': 0.3,
        ...         'max_optimal': 0.8,
        ...         'min_tolerable': 0.1,
        ...         'max_tolerable': 1.5
        ...     }
        ... }
        >>> score_velocity_suitability(0.5, config)  # Optimal
        1.0
        >>> score_velocity_suitability(0.2, config)  # Slow but tolerable
        0.5
        >>> score_velocity_suitability(0.05, config) # Too slow
        0.0
    """
    ranges = config['velocity_ranges']
    min_tol = ranges['min_tolerable']
    max_tol = ranges['max_tolerable']
    min_opt = ranges['min_optimal']
    max_opt = ranges['max_optimal']

    # Handle negative velocities
    if velocity_ms < 0:
        return 0.0

    # Below tolerable range: unsuitable
    if velocity_ms < min_tol:
        return 0.0

    # Above tolerable range: unsuitable
    if velocity_ms > max_tol:
        return 0.0

    # Optimal range: perfect score
    if min_opt <= velocity_ms <= max_opt:
        return 1.0

    # Between min_tolerable and min_optimal: gradient
    if min_tol <= velocity_ms < min_opt:
        return (velocity_ms - min_tol) / (min_opt - min_tol)

    # Between max_optimal and max_tolerable: gradient
    if max_opt < velocity_ms <= max_tol:
        return (max_tol - velocity_ms) / (max_tol - max_opt)

    return 0.0  # Fallback


def score_stability(bdi: float, flow_variability: Optional[float] = None) -> float:
    """
    Score habitat stability based on BDI and flow variability.

    High BDI indicates groundwater-fed streams with stable flow and temperature.
    Low flow variability indicates predictable conditions.

    Args:
        bdi: Baseflow Dominance Index (0-1)
        flow_variability: Optional coefficient of variation of flow

    Returns:
        Stability score (0-1)

    Examples:
        >>> score_stability(0.8)  # High BDI, stable
        0.8
        >>> score_stability(0.3)  # Low BDI, flashy
        0.3
        >>> score_stability(0.7, flow_variability=0.5)  # Moderate stability
        0.6
    """
    # BDI is primary stability indicator
    base_score = bdi

    # If flow variability available, penalize high variability
    if flow_variability is not None:
        # CV > 1.0 is very flashy, CV < 0.3 is stable
        # Normalize CV to penalty (0 = no penalty, 1 = max penalty)
        variability_penalty = min(1.0, max(0.0, (flow_variability - 0.3) / 0.7))
        # Apply up to 20% penalty based on variability
        base_score *= (1.0 - 0.2 * variability_penalty)

    return base_score


def compute_species_score(
    feature_id: int,
    species: str,
    hydro_data: Dict[str, Any],
    confidence: str = "medium"
) -> SpeciesScore:
    """
    Compute overall habitat suitability score for a species.

    Combines multiple habitat components using weighted average.

    Args:
        feature_id: NHD reach feature_id
        species: Species identifier (e.g., 'trout')
        hydro_data: Dictionary containing:
            - flow_percentile: Flow percentile (0-100)
            - velocity: Velocity in m/s
            - bdi: Baseflow Dominance Index (0-1)
            - flow_variability: Optional CV of flow
            - tsi: Optional Thermal Suitability Index (0-1) [EPIC 3]
        confidence: Confidence level for the score

    Returns:
        SpeciesScore with overall score, rating, and explanation

    Examples:
        >>> hydro_data = {
        ...     'flow_percentile': 55,
        ...     'velocity': 0.6,
        ...     'bdi': 0.75,
        ...     'flow_variability': 0.4
        ... }
        >>> score = compute_species_score(12345, 'trout', hydro_data)
        >>> score.rating
        'good'
    """
    # Load species config
    config = load_species_config(species)
    weights = config['scoring_weights']

    # Compute component scores
    flow_score = score_flow_suitability(
        hydro_data.get('flow_percentile', 50),
        config
    )

    velocity_score = score_velocity_suitability(
        hydro_data.get('velocity', 0.0),
        config
    )

    # TODO EPIC-3: Replace with actual TSI when temperature data available
    # thermal_score = hydro_data.get('tsi', 0.0)
    thermal_score = 0.0  # TEMPORARY: Disabled until EPIC 3 complete

    stability_score = score_stability(
        hydro_data.get('bdi', 0.5),
        hydro_data.get('flow_variability')
    )

    # Compute weighted overall score
    overall = (
        weights['flow_suitability'] * flow_score +
        weights['velocity_suitability'] * velocity_score +
        weights['thermal_suitability'] * thermal_score +
        weights['stability'] * stability_score
    )

    # Classify into rating
    if overall >= 0.8:
        rating = "excellent"
    elif overall >= 0.6:
        rating = "good"
    elif overall >= 0.3:
        rating = "fair"
    else:
        rating = "poor"

    # Generate explanation
    components = {
        'flow': flow_score,
        'velocity': velocity_score,
        'thermal': thermal_score,
        'stability': stability_score
    }

    explanation = generate_explanation(
        overall,
        components,
        config,
        hydro_data
    )

    return SpeciesScore(
        overall_score=overall,
        rating=rating,
        components=components,
        explanation=explanation,
        confidence=confidence,
        species=config['name'],
        feature_id=feature_id
    )


def generate_explanation(
    overall_score: float,
    components: Dict[str, float],
    config: Dict[str, Any],
    hydro_data: Dict[str, Any]
) -> str:
    """
    Generate human-readable explanation of species score.

    Explains which factors contribute to or detract from habitat quality.

    Args:
        overall_score: Overall habitat score (0-1)
        components: Individual component scores
        config: Species configuration
        hydro_data: Raw hydrologic data

    Returns:
        Explanation string
    """
    species_name = config['name']

    # Start with overall assessment
    if overall_score >= 0.8:
        assessment = f"Excellent habitat for {species_name}."
    elif overall_score >= 0.6:
        assessment = f"Good habitat for {species_name}."
    elif overall_score >= 0.3:
        assessment = f"Fair habitat for {species_name}."
    else:
        assessment = f"Poor habitat for {species_name}."

    # Identify strengths and weaknesses
    strengths = []
    weaknesses = []

    # Flow
    flow_score = components['flow']
    flow_pct = hydro_data.get('flow_percentile', 50)
    if flow_score >= 0.7:
        strengths.append(f"flow at {flow_pct:.0f}th percentile (optimal range)")
    elif flow_score < 0.3:
        if flow_pct < config['flow_percentile_optimal']['min']:
            weaknesses.append(f"low flow ({flow_pct:.0f}th percentile)")
        else:
            weaknesses.append(f"high flow ({flow_pct:.0f}th percentile)")

    # Velocity
    vel_score = components['velocity']
    velocity = hydro_data.get('velocity', 0.0)
    if vel_score >= 0.7:
        strengths.append(f"suitable velocity ({velocity:.2f} m/s)")
    elif vel_score < 0.3:
        vel_ranges = config['velocity_ranges']
        if velocity < vel_ranges['min_optimal']:
            weaknesses.append(f"slow velocity ({velocity:.2f} m/s)")
        else:
            weaknesses.append(f"fast velocity ({velocity:.2f} m/s)")

    # Stability (BDI)
    stab_score = components['stability']
    bdi = hydro_data.get('bdi', 0.5)
    if stab_score >= 0.7:
        strengths.append(f"stable groundwater-fed conditions (BDI={bdi:.2f})")
    elif stab_score < 0.3:
        weaknesses.append(f"flashy storm-dominated conditions (BDI={bdi:.2f})")

    # Thermal (currently disabled)
    # TODO EPIC-3: Add thermal explanation when available

    # Build explanation
    parts = [assessment]

    if strengths:
        parts.append(" Strengths: " + ", ".join(strengths) + ".")

    if weaknesses:
        parts.append(" Concerns: " + ", ".join(weaknesses) + ".")

    # Note about missing thermal data
    if components['thermal'] == 0.0 and config['scoring_weights']['thermal_suitability'] == 0.0:
        parts.append(" (Temperature data not yet integrated - see EPIC 3)")

    return "".join(parts)


def classify_rating(score: float) -> Rating:
    """
    Convert numeric score to qualitative rating.

    Args:
        score: Overall score (0-1)

    Returns:
        Rating classification
    """
    if score >= 0.8:
        return "excellent"
    elif score >= 0.6:
        return "good"
    elif score >= 0.3:
        return "fair"
    else:
        return "poor"
