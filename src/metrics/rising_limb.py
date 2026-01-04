"""
Rising Limb Detection for FNWM

Detects sustained increases in streamflow (rising limbs) and classifies their intensity.

Rising limbs are ecologically important signals:
- Mayfly emergence triggers
- Fish feeding activity changes
- Habitat availability shifts

Design Principles:
- Config-driven thresholds (no hardcoded values)
- Species-aware detection (different species respond to different rates of change)
- Deterministic and testable
- Handles missing data gracefully
"""

from typing import Literal, Optional, Tuple
import yaml
from pathlib import Path
import pandas as pd
import numpy as np


# Type aliases for clarity
IntensityLevel = Optional[Literal["weak", "moderate", "strong"]]
RisingLimbResult = Tuple[bool, IntensityLevel]


class RisingLimbConfig:
    """
    Configuration for rising limb detection.

    Attributes:
        min_slope: Minimum flow increase rate (m³/s per hour) to consider rising
        min_duration: Minimum consecutive hours of rising to confirm detection
        intensity_thresholds: Thresholds for weak/moderate/strong classification
    """

    def __init__(
        self,
        min_slope: float,
        min_duration: int,
        intensity_thresholds: dict
    ):
        self.min_slope = min_slope
        self.min_duration = min_duration
        self.intensity_thresholds = intensity_thresholds

    @classmethod
    def from_yaml(cls, config_path: Path, species: Optional[str] = None) -> 'RisingLimbConfig':
        """
        Load configuration from YAML file.

        Args:
            config_path: Path to rising_limb.yaml
            species: Optional species name for species-specific overrides

        Returns:
            RisingLimbConfig instance
        """
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)

        # Start with default config
        params = config['default'].copy()

        # Apply species override if specified
        if species and 'species_overrides' in config:
            if species in config['species_overrides']:
                params.update(config['species_overrides'][species])

        return cls(
            min_slope=params['min_slope'],
            min_duration=params['min_duration'],
            intensity_thresholds=params['intensity_thresholds']
        )


def detect_rising_limb(
    flows: pd.Series,
    config: RisingLimbConfig
) -> RisingLimbResult:
    """
    Detect sustained rising limb in streamflow timeseries.

    Algorithm:
    1. Compute dQ/dt (rate of change in m³/s per hour)
    2. Identify consecutive hours where dQ/dt > min_slope
    3. Confirm if consecutive duration >= min_duration
    4. Classify intensity based on maximum slope

    Args:
        flows: Time-indexed streamflow series (m³/s)
               Index must be timezone-aware datetime
        config: RisingLimbConfig with detection thresholds

    Returns:
        Tuple of (detected: bool, intensity: "weak"|"moderate"|"strong"|None)

    Examples:
        >>> times = pd.date_range('2025-01-01', periods=24, freq='H', tz='UTC')
        >>> flows = pd.Series([10, 10, 11, 13, 16, 20, 25, 30] + [30]*16, index=times)
        >>> config = RisingLimbConfig(min_slope=0.5, min_duration=3,
        ...                          intensity_thresholds={'weak': 0.5, 'moderate': 2.0, 'strong': 5.0})
        >>> detected, intensity = detect_rising_limb(flows, config)
        >>> detected
        True
        >>> intensity
        'moderate'
    """
    # Handle edge cases
    if len(flows) < config.min_duration:
        return False, None

    if flows.isna().all():
        return False, None

    # Ensure index is datetime
    if not isinstance(flows.index, pd.DatetimeIndex):
        raise ValueError("flows must have a DatetimeIndex")

    # Sort by time to ensure proper derivative calculation
    flows = flows.sort_index()

    # Compute time differences in hours
    time_diff_hours = flows.index.to_series().diff().dt.total_seconds() / 3600

    # Compute dQ/dt (flow change per hour)
    flow_diff = flows.diff()
    dQdt = flow_diff / time_diff_hours

    # Identify rising periods (where dQ/dt exceeds minimum slope)
    is_rising = dQdt > config.min_slope

    # Check for consecutive rising periods
    # Use rolling window to count consecutive True values
    consecutive_rising = is_rising.rolling(window=config.min_duration, min_periods=config.min_duration).sum()

    # Detected if any window has all hours rising
    detected = (consecutive_rising >= config.min_duration).any()

    if not detected:
        return False, None

    # Classify intensity based on maximum slope during rising periods
    max_slope = dQdt[is_rising].max()

    if pd.isna(max_slope):
        return False, None

    # Apply intensity thresholds
    if max_slope >= config.intensity_thresholds['strong']:
        intensity = "strong"
    elif max_slope >= config.intensity_thresholds['moderate']:
        intensity = "moderate"
    else:
        intensity = "weak"

    return True, intensity


def detect_rising_limb_for_reach(
    feature_id: int,
    start_time: pd.Timestamp,
    end_time: pd.Timestamp,
    config: RisingLimbConfig,
    db_connection
) -> RisingLimbResult:
    """
    Detect rising limb for a specific reach from database.

    Args:
        feature_id: NHDPlus feature ID
        start_time: Start of time window (UTC timezone-aware)
        end_time: End of time window (UTC timezone-aware)
        config: RisingLimbConfig with detection thresholds
        db_connection: SQLAlchemy connection or engine

    Returns:
        Tuple of (detected: bool, intensity: "weak"|"moderate"|"strong"|None)
    """
    from sqlalchemy import text

    # Query streamflow data for the reach
    query = text("""
        SELECT valid_time, value
        FROM hydro_timeseries
        WHERE feature_id = :feature_id
          AND variable = 'streamflow'
          AND valid_time BETWEEN :start_time AND :end_time
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

    # Convert to pandas Series
    rows = result.fetchall()

    if not rows:
        return False, None

    times = [row[0] for row in rows]
    values = [row[1] for row in rows]

    flows = pd.Series(values, index=pd.DatetimeIndex(times))

    # Detect rising limb
    return detect_rising_limb(flows, config)


def load_default_config() -> RisingLimbConfig:
    """
    Load default rising limb configuration.

    Returns:
        RisingLimbConfig with default thresholds
    """
    # Default path relative to this file
    config_path = Path(__file__).parent.parent.parent / 'config' / 'thresholds' / 'rising_limb.yaml'

    if not config_path.exists():
        # Fallback to hardcoded defaults if config file not found
        return RisingLimbConfig(
            min_slope=0.5,
            min_duration=3,
            intensity_thresholds={
                'weak': 0.5,
                'moderate': 2.0,
                'strong': 5.0
            }
        )

    return RisingLimbConfig.from_yaml(config_path)


def explain_detection(
    detected: bool,
    intensity: IntensityLevel,
    max_slope: Optional[float] = None,
    config: Optional[RisingLimbConfig] = None
) -> str:
    """
    Generate human-readable explanation of detection result.

    Args:
        detected: Whether rising limb was detected
        intensity: Intensity level if detected
        max_slope: Maximum slope observed (optional, for detailed explanation)
        config: Configuration used (optional, for threshold context)

    Returns:
        Explanation string
    """
    if not detected:
        if config:
            return (f"No sustained rising limb detected. Flow must increase by at least "
                   f"{config.min_slope} m³/s per hour for {config.min_duration} consecutive hours.")
        else:
            return "No sustained rising limb detected."

    explanation = f"Rising limb detected with {intensity} intensity."

    if max_slope and config:
        explanation += (f" Maximum flow increase rate: {max_slope:.2f} m³/s per hour. "
                       f"Threshold for {intensity}: {config.intensity_thresholds[intensity]} m³/s per hour.")

    return explanation


# Example usage
if __name__ == "__main__":
    # Example: Synthetic hydrograph with rising limb
    import pytz

    print("Rising Limb Detector - Example Usage")
    print("=" * 60)

    # Create synthetic data
    times = pd.date_range('2025-01-01', periods=24, freq='H', tz=pytz.UTC)

    # Scenario 1: Moderate rising limb
    flows_moderate = pd.Series(
        [10, 10, 11, 13, 16, 20, 25, 30, 32, 33] + [33]*14,
        index=times
    )

    print("Scenario 1: Moderate rising limb")
    print(f"Flow values: {flows_moderate.values[:10].tolist()}...")

    config = load_default_config()
    detected, intensity = detect_rising_limb(flows_moderate, config)

    print(f"Detected: {detected}")
    print(f"Intensity: {intensity}")
    print(f"Explanation: {explain_detection(detected, intensity, config=config)}")
    print()

    # Scenario 2: No rising limb (stable flow)
    flows_stable = pd.Series([30]*24, index=times)

    print("Scenario 2: Stable flow (no rising limb)")
    print(f"Flow values: {flows_stable.values[:10].tolist()}...")

    detected, intensity = detect_rising_limb(flows_stable, config)

    print(f"Detected: {detected}")
    print(f"Intensity: {intensity}")
    print(f"Explanation: {explain_detection(detected, intensity, config=config)}")
    print()

    # Scenario 3: Strong rising limb
    flows_strong = pd.Series(
        [10, 10, 15, 25, 40, 60, 85, 110] + [110]*16,
        index=times
    )

    print("Scenario 3: Strong rising limb")
    print(f"Flow values: {flows_strong.values[:10].tolist()}...")

    detected, intensity = detect_rising_limb(flows_strong, config)

    print(f"Detected: {detected}")
    print(f"Intensity: {intensity}")
    print(f"Explanation: {explain_detection(detected, intensity, config=config)}")
