"""
Velocity Suitability Classifier for FNWM

Classifies stream velocity suitability for different fish species.

Velocity is ecologically critical because it affects:
- Habitat availability (resting vs. feeding)
- Energy expenditure (swimming costs)
- Feeding efficiency (drift capture)
- Spawning success (gravel scour, egg burial)
- Life stage suitability (fry vs. adults have different preferences)

Design Principles:
- Species-aware thresholds (different species prefer different velocities)
- Returns both categorical and numeric scores
- Config-driven, no hardcoded values
- Gradient scoring for sub-optimal velocities
"""

from typing import Literal, Optional, Tuple
from enum import Enum
from pathlib import Path
import yaml
import pandas as pd
from datetime import datetime


# Type aliases
VelocityClass = Literal["too_slow", "optimal", "fast", "too_fast"]
VelocityResult = Tuple[bool, VelocityClass, float]


class SpeciesVelocityConfig:
    """
    Species-specific velocity configuration.

    Attributes:
        species_name: Common name of species
        min_tolerable: Minimum tolerable velocity (m/s)
        max_tolerable: Maximum tolerable velocity (m/s)
        min_optimal: Minimum optimal velocity (m/s)
        max_optimal: Maximum optimal velocity (m/s)
    """

    def __init__(
        self,
        species_name: str,
        min_tolerable: float,
        max_tolerable: float,
        min_optimal: float,
        max_optimal: float
    ):
        self.species_name = species_name
        self.min_tolerable = min_tolerable
        self.max_tolerable = max_tolerable
        self.min_optimal = min_optimal
        self.max_optimal = max_optimal

        # Validate ranges
        if not (min_tolerable <= min_optimal <= max_optimal <= max_tolerable):
            raise ValueError(
                "Velocity ranges must satisfy: "
                "min_tolerable <= min_optimal <= max_optimal <= max_tolerable"
            )

    @classmethod
    def from_yaml(cls, config_path: Path) -> 'SpeciesVelocityConfig':
        """
        Load species configuration from YAML file.

        Args:
            config_path: Path to species YAML file (e.g., config/species/trout.yaml)

        Returns:
            SpeciesVelocityConfig instance
        """
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)

        velocity_ranges = config['velocity_ranges']

        return cls(
            species_name=config['name'],
            min_tolerable=velocity_ranges['min_tolerable'],
            max_tolerable=velocity_ranges['max_tolerable'],
            min_optimal=velocity_ranges['min_optimal'],
            max_optimal=velocity_ranges['max_optimal']
        )


def compute_gradient_score(velocity_ms: float, config: SpeciesVelocityConfig) -> float:
    """
    Compute gradient score for sub-optimal velocities.

    For velocities between tolerable and optimal, compute a linear gradient score.

    Args:
        velocity_ms: Stream velocity (m/s)
        config: Species velocity configuration

    Returns:
        Score between 0.0 and 1.0
    """
    # If in optimal range, return 1.0
    if config.min_optimal <= velocity_ms <= config.max_optimal:
        return 1.0

    # Below optimal (slow)
    if velocity_ms < config.min_optimal:
        if velocity_ms < config.min_tolerable:
            return 0.0
        # Linear gradient from min_tolerable to min_optimal
        range_width = config.min_optimal - config.min_tolerable
        distance_from_min = velocity_ms - config.min_tolerable
        return distance_from_min / range_width

    # Above optimal (fast)
    if velocity_ms > config.max_optimal:
        if velocity_ms > config.max_tolerable:
            return 0.0
        # Linear gradient from max_optimal to max_tolerable
        range_width = config.max_tolerable - config.max_optimal
        distance_from_max = config.max_tolerable - velocity_ms
        return distance_from_max / range_width

    return 1.0  # Shouldn't reach here, but default to optimal


def classify_velocity(
    velocity_ms: float,
    config: SpeciesVelocityConfig
) -> VelocityResult:
    """
    Classify stream velocity suitability for a species.

    Returns both a categorical classification and a numeric score (0-1).

    Args:
        velocity_ms: Stream velocity (m/s)
        config: Species velocity configuration

    Returns:
        Tuple of (suitable: bool, classification: VelocityClass, score: 0-1)

    Examples:
        >>> config = SpeciesVelocityConfig("Trout", 0.1, 1.5, 0.3, 0.8)
        >>> classify_velocity(0.5, config)
        (True, 'optimal', 1.0)
        >>> classify_velocity(0.05, config)
        (False, 'too_slow', 0.0)
        >>> classify_velocity(2.0, config)
        (False, 'too_fast', 0.0)
    """
    # Handle edge cases
    if velocity_ms < 0:
        velocity_ms = 0.0

    # Too slow (below tolerable)
    if velocity_ms < config.min_tolerable:
        return False, "too_slow", 0.0

    # Too fast (above tolerable)
    if velocity_ms > config.max_tolerable:
        return False, "too_fast", 0.0

    # Optimal range
    if config.min_optimal <= velocity_ms <= config.max_optimal:
        return True, "optimal", 1.0

    # Sub-optimal but tolerable (slow side)
    if velocity_ms < config.min_optimal:
        score = compute_gradient_score(velocity_ms, config)
        return True, "too_slow", score  # Tolerable but slow

    # Sub-optimal but tolerable (fast side)
    if velocity_ms > config.max_optimal:
        score = compute_gradient_score(velocity_ms, config)
        return True, "fast", score

    # Default (shouldn't reach here)
    return True, "optimal", 1.0


def explain_velocity_suitability(
    velocity_ms: float,
    suitable: bool,
    classification: VelocityClass,
    score: float,
    species_name: str
) -> str:
    """
    Generate human-readable explanation of velocity suitability.

    Args:
        velocity_ms: Stream velocity (m/s)
        suitable: Whether velocity is suitable
        classification: Velocity classification
        score: Suitability score (0-1)
        species_name: Name of species

    Returns:
        Explanation string
    """
    explanations = {
        "optimal": (
            f"Velocity: {velocity_ms:.2f} m/s (optimal for {species_name}). "
            f"Ideal conditions for feeding, resting, and spawning. Score: {score:.2f}"
        ),
        "too_slow": (
            f"Velocity: {velocity_ms:.2f} m/s ({'tolerable but slow' if suitable else 'too slow'} for {species_name}). "
            f"{'May reduce feeding efficiency and oxygen availability.' if suitable else 'Insufficient flow for habitat requirements.'} "
            f"Score: {score:.2f}"
        ),
        "fast": (
            f"Velocity: {velocity_ms:.2f} m/s (fast for {species_name}). "
            f"Tolerable but may increase energy costs for holding position. Score: {score:.2f}"
        ),
        "too_fast": (
            f"Velocity: {velocity_ms:.2f} m/s (too fast for {species_name}). "
            f"Exceeds swimming capacity, unsuitable habitat. Score: {score:.2f}"
        )
    }

    return explanations[classification]


def classify_velocity_for_reach(
    feature_id: int,
    valid_time: datetime,
    species_config: SpeciesVelocityConfig,
    db_connection
) -> Optional[VelocityResult]:
    """
    Classify velocity suitability for a reach at a specific time from database.

    Args:
        feature_id: NHDPlus feature ID
        valid_time: Timestamp for velocity classification (UTC timezone-aware)
        species_config: Species velocity configuration
        db_connection: SQLAlchemy connection or engine

    Returns:
        Tuple of (suitable, classification, score) or None if data not available
    """
    from sqlalchemy import text

    # Query velocity for the reach at the specified time
    query = text("""
        SELECT value
        FROM hydro_timeseries
        WHERE feature_id = :feature_id
          AND valid_time = :valid_time
          AND variable = 'velocity'
    """)

    result = db_connection.execute(
        query,
        {
            'feature_id': feature_id,
            'valid_time': valid_time
        }
    )

    row = result.fetchone()

    if row is None:
        return None

    velocity_ms = row[0]

    # Classify velocity
    suitable, classification, score = classify_velocity(velocity_ms, species_config)

    return suitable, classification, score


def classify_velocity_timeseries_for_reach(
    feature_id: int,
    start_time: datetime,
    end_time: datetime,
    species_config: SpeciesVelocityConfig,
    db_connection
) -> pd.DataFrame:
    """
    Classify velocity suitability time series for a reach from database.

    Args:
        feature_id: NHDPlus feature ID
        start_time: Start of time window (UTC timezone-aware)
        end_time: End of time window (UTC timezone-aware)
        species_config: Species velocity configuration
        db_connection: SQLAlchemy connection or engine

    Returns:
        DataFrame with columns:
        - valid_time: Timestamp
        - velocity_ms: Velocity (m/s)
        - suitable: Boolean suitability
        - classification: Velocity class
        - score: Suitability score (0-1)
    """
    from sqlalchemy import text

    # Query velocity data
    query = text("""
        SELECT valid_time, value
        FROM hydro_timeseries
        WHERE feature_id = :feature_id
          AND valid_time BETWEEN :start_time AND :end_time
          AND variable = 'velocity'
        ORDER BY valid_time ASC
    """)

    result = db_connection.execute(
        query,
        {
            'feature_id': feature_id,
            'start_time': start_time,
            'end_time': end_time
        }
    )

    # Parse results
    rows = []
    for valid_time, velocity_ms in result:
        suitable, classification, score = classify_velocity(velocity_ms, species_config)

        rows.append({
            'valid_time': valid_time,
            'velocity_ms': velocity_ms,
            'suitable': suitable,
            'classification': classification,
            'score': score
        })

    return pd.DataFrame(rows)


def compute_velocity_statistics(df: pd.DataFrame) -> dict:
    """
    Compute summary statistics for velocity suitability time series.

    Args:
        df: DataFrame from classify_velocity_timeseries_for_reach()

    Returns:
        Dictionary with statistical summary
    """
    if len(df) == 0:
        return {
            'mean_velocity': None,
            'mean_score': None,
            'percent_suitable': None,
            'percent_optimal': None,
            'dominant_class': None
        }

    mean_velocity = df['velocity_ms'].mean()
    mean_score = df['score'].mean()
    percent_suitable = (df['suitable'].sum() / len(df)) * 100
    percent_optimal = (df['classification'] == 'optimal').sum() / len(df) * 100

    # Find most common classification
    dominant_class = df['classification'].mode()[0] if len(df) > 0 else None

    return {
        'mean_velocity': mean_velocity,
        'mean_score': mean_score,
        'percent_suitable': percent_suitable,
        'percent_optimal': percent_optimal,
        'dominant_class': dominant_class
    }


def load_species_config(species: str = "trout") -> SpeciesVelocityConfig:
    """
    Load species velocity configuration from YAML file.

    Args:
        species: Species name (default: "trout")

    Returns:
        SpeciesVelocityConfig instance
    """
    config_path = Path(__file__).parent.parent.parent / 'config' / 'species' / f'{species}.yaml'

    if not config_path.exists():
        raise FileNotFoundError(f"Species config not found: {config_path}")

    return SpeciesVelocityConfig.from_yaml(config_path)


# Example usage
if __name__ == "__main__":
    print("Velocity Suitability Classifier - Example Usage")
    print("=" * 70)
    print()

    # Load trout configuration
    config = load_species_config("trout")

    print(f"Species: {config.species_name}")
    print(f"Velocity ranges:")
    print(f"  Tolerable: {config.min_tolerable} - {config.max_tolerable} m/s")
    print(f"  Optimal: {config.min_optimal} - {config.max_optimal} m/s")
    print()

    # Test scenarios
    test_velocities = [
        (0.05, "Very slow (stagnant)"),
        (0.2, "Slow but tolerable"),
        (0.5, "Optimal"),
        (1.0, "Fast but tolerable"),
        (2.0, "Too fast (torrent)")
    ]

    for velocity, description in test_velocities:
        print(f"Scenario: {description}")
        print("-" * 70)
        print(f"Velocity: {velocity} m/s")

        suitable, classification, score = classify_velocity(velocity, config)

        print(f"  Suitable: {suitable}")
        print(f"  Classification: {classification}")
        print(f"  Score: {score:.3f}")
        print(f"  Explanation: {explain_velocity_suitability(velocity, suitable, classification, score, config.species_name)}")
        print()
