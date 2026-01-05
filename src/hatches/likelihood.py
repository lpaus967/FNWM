"""
Hatch Likelihood Engine for FNWM

Predicts the likelihood of insect hatches based on hydrologic signatures.

Different insect species have distinct hydrologic preferences:
- Some hatches prefer stable, clear water (high BDI, no rising limbs)
- Others are triggered by flow pulses (rising limbs, specific velocities)
- All hatches have seasonal windows when they can occur

Design Principles:
- Config-driven (hatch signatures in YAML files)
- Deterministic and reproducible
- Explainable (shows which conditions match/don't match)
- Seasonal gating (won't predict winter hatches in summer)

Example Hatches:
- Green Drake: Stable, high-flow conditions in late spring
- Pale Morning Dun: Moderate flow, stable conditions, summer
- Caddis: Adaptable, various flow conditions
"""

from typing import Literal, Dict, Any, List
from pathlib import Path
from datetime import datetime
import yaml
from pydantic import BaseModel, Field

# Type aliases
HatchRating = Literal["unlikely", "possible", "likely", "very_likely"]


class HatchScore(BaseModel):
    """Hatch likelihood prediction."""

    hatch_name: str = Field(..., description="Common name of hatch")
    scientific_name: str = Field(..., description="Scientific name (genus species)")
    likelihood: float = Field(..., ge=0.0, le=1.0, description="Likelihood score (0-1)")
    rating: HatchRating = Field(..., description="Qualitative rating")
    hydrologic_match: Dict[str, bool] = Field(..., description="Which conditions match")
    explanation: str = Field(..., description="Human-readable explanation")
    in_season: bool = Field(..., description="Whether currently in seasonal window")
    feature_id: int = Field(..., description="NHD reach feature_id")
    date_checked: datetime = Field(default_factory=datetime.utcnow, description="When prediction was made")


def load_hatch_config(hatch: str) -> Dict[str, Any]:
    """
    Load hatch configuration from YAML file.

    Args:
        hatch: Hatch identifier (e.g., 'green_drake', 'pmd', 'caddis')

    Returns:
        Configuration dictionary with hydrologic signature and temporal window

    Raises:
        FileNotFoundError: If hatch config file doesn't exist
        ValueError: If config is invalid

    Examples:
        >>> config = load_hatch_config('green_drake')
        >>> config['name']
        'Green Drake'
    """
    config_path = Path(__file__).parent.parent.parent / "config" / "hatches" / f"{hatch}.yaml"

    if not config_path.exists():
        raise FileNotFoundError(
            f"Hatch config not found: {config_path}\n"
            f"Available hatches: green_drake"
        )

    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)

    # Validate required fields
    required = ['name', 'species', 'hydrologic_signature', 'temporal_window']
    missing = [field for field in required if field not in config]
    if missing:
        raise ValueError(f"Invalid config for {hatch}: missing fields {missing}")

    # Validate hydrologic signature
    sig_required = ['flow_percentile', 'rising_limb', 'velocity', 'bdi_threshold']
    sig = config['hydrologic_signature']
    sig_missing = [field for field in sig_required if field not in sig]
    if sig_missing:
        raise ValueError(f"Invalid hydrologic_signature: missing fields {sig_missing}")

    # Validate temporal window
    window = config['temporal_window']
    if 'start_day_of_year' not in window or 'end_day_of_year' not in window:
        raise ValueError("temporal_window must have start_day_of_year and end_day_of_year")

    return config


def check_seasonal_window(current_date: datetime, config: Dict[str, Any]) -> bool:
    """
    Check if current date falls within hatch's seasonal window.

    Args:
        current_date: Date to check
        config: Hatch configuration

    Returns:
        True if in season, False otherwise

    Examples:
        >>> from datetime import datetime
        >>> config = {'temporal_window': {'start_day_of_year': 135, 'end_day_of_year': 180}}
        >>> check_seasonal_window(datetime(2025, 5, 20), config)  # May 20 = day 140
        True
        >>> check_seasonal_window(datetime(2025, 12, 25), config)  # Dec 25 = day 359
        False
    """
    window = config['temporal_window']
    day_of_year = current_date.timetuple().tm_yday

    start = window['start_day_of_year']
    end = window['end_day_of_year']

    # Handle wrap-around (e.g., winter hatch from Dec to Feb)
    if start <= end:
        # Normal case: May to June
        return start <= day_of_year <= end
    else:
        # Wrap-around case: Dec to Feb
        return day_of_year >= start or day_of_year <= end


def check_hydrologic_signature(
    hydro_data: Dict[str, Any],
    config: Dict[str, Any]
) -> Dict[str, bool]:
    """
    Check if hydrologic conditions match hatch signature.

    Args:
        hydro_data: Dictionary with:
            - flow_percentile: Flow percentile (0-100)
            - rising_limb: Rising limb status (False, "weak", "moderate", "strong")
            - velocity: Velocity in m/s
            - bdi: Baseflow Dominance Index (0-1)
        config: Hatch configuration

    Returns:
        Dictionary of condition matches (True/False for each criterion)

    Examples:
        >>> hydro_data = {
        ...     'flow_percentile': 60,
        ...     'rising_limb': False,
        ...     'velocity': 0.6,
        ...     'bdi': 0.7
        ... }
        >>> config = load_hatch_config('green_drake')
        >>> matches = check_hydrologic_signature(hydro_data, config)
        >>> matches['bdi']
        True
    """
    signature = config['hydrologic_signature']
    matches = {}

    # Check flow percentile range
    flow_pct = hydro_data.get('flow_percentile', 50)
    flow_range = signature['flow_percentile']
    matches['flow_percentile'] = (
        flow_range['min'] <= flow_pct <= flow_range['max']
    )

    # Check rising limb (allowed values)
    rising_limb = hydro_data.get('rising_limb', False)
    # Convert False to string "false" for comparison
    rising_limb_str = str(rising_limb).lower() if isinstance(rising_limb, bool) else rising_limb
    allowed_limbs = [str(val).lower() for val in signature['rising_limb']['allowed']]
    matches['rising_limb'] = rising_limb_str in allowed_limbs

    # Check velocity range
    velocity = hydro_data.get('velocity', 0.0)
    vel_range = signature['velocity']
    matches['velocity'] = (
        vel_range['min'] <= velocity <= vel_range['max']
    )

    # Check BDI threshold
    bdi = hydro_data.get('bdi', 0.5)
    matches['bdi'] = bdi >= signature['bdi_threshold']

    return matches


def compute_hatch_likelihood(
    feature_id: int,
    hatch: str,
    hydro_data: Dict[str, Any],
    current_date: datetime = None
) -> HatchScore:
    """
    Compute hatch likelihood based on hydrologic signature and seasonality.

    Args:
        feature_id: NHD reach feature_id
        hatch: Hatch identifier (e.g., 'green_drake')
        hydro_data: Dictionary containing:
            - flow_percentile: Flow percentile (0-100)
            - rising_limb: Rising limb status
            - velocity: Velocity in m/s
            - bdi: Baseflow Dominance Index (0-1)
        current_date: Date to check (defaults to now)

    Returns:
        HatchScore with likelihood, rating, and explanation

    Examples:
        >>> hydro_data = {
        ...     'flow_percentile': 65,
        ...     'rising_limb': False,
        ...     'velocity': 0.6,
        ...     'bdi': 0.75
        ... }
        >>> score = compute_hatch_likelihood(
        ...     12345,
        ...     'green_drake',
        ...     hydro_data,
        ...     datetime(2025, 5, 25)
        ... )
        >>> score.rating
        'very_likely'
    """
    if current_date is None:
        current_date = datetime.utcnow()

    # Load hatch config
    config = load_hatch_config(hatch)

    # Check seasonal window first
    in_season = check_seasonal_window(current_date, config)

    if not in_season:
        return HatchScore(
            hatch_name=config['name'],
            scientific_name=config['species'],
            likelihood=0.0,
            rating="unlikely",
            hydrologic_match={},
            explanation=generate_out_of_season_explanation(current_date, config),
            in_season=False,
            feature_id=feature_id,
            date_checked=current_date
        )

    # Check hydrologic conditions
    matches = check_hydrologic_signature(hydro_data, config)

    # Compute likelihood score based on match quality
    match_count = sum(matches.values())
    total_conditions = len(matches)
    likelihood = match_count / total_conditions if total_conditions > 0 else 0.0

    # Classify into rating
    if likelihood >= 0.75:
        rating = "very_likely"
    elif likelihood >= 0.5:
        rating = "likely"
    elif likelihood >= 0.25:
        rating = "possible"
    else:
        rating = "unlikely"

    # Generate explanation
    explanation = generate_hatch_explanation(matches, config, hydro_data)

    return HatchScore(
        hatch_name=config['name'],
        scientific_name=config['species'],
        likelihood=likelihood,
        rating=rating,
        hydrologic_match=matches,
        explanation=explanation,
        in_season=True,
        feature_id=feature_id,
        date_checked=current_date
    )


def generate_hatch_explanation(
    matches: Dict[str, bool],
    config: Dict[str, Any],
    hydro_data: Dict[str, Any]
) -> str:
    """
    Generate human-readable explanation of hatch likelihood.

    Args:
        matches: Dictionary of condition matches
        config: Hatch configuration
        hydro_data: Raw hydrologic data

    Returns:
        Explanation string
    """
    hatch_name = config['name']
    match_count = sum(matches.values())
    total = len(matches)

    # Start with overall assessment
    if match_count == total:
        intro = f"All hydrologic conditions favor {hatch_name} emergence."
    elif match_count >= total * 0.75:
        intro = f"Most conditions favor {hatch_name} emergence."
    elif match_count >= total * 0.5:
        intro = f"Some conditions favor {hatch_name} emergence."
    else:
        intro = f"Few conditions favor {hatch_name} emergence."

    # List matching conditions
    matching = []
    not_matching = []

    if matches.get('flow_percentile'):
        flow_pct = hydro_data.get('flow_percentile', 50)
        matching.append(f"flow at {flow_pct:.0f}th percentile (in preferred range)")
    else:
        flow_pct = hydro_data.get('flow_percentile', 50)
        flow_range = config['hydrologic_signature']['flow_percentile']
        not_matching.append(f"flow at {flow_pct:.0f}th percentile (prefers {flow_range['min']}-{flow_range['max']})")

    if matches.get('rising_limb'):
        matching.append("flow stability suitable")
    else:
        not_matching.append("flow conditions not stable enough")

    if matches.get('velocity'):
        velocity = hydro_data.get('velocity', 0.0)
        matching.append(f"velocity {velocity:.2f} m/s (in preferred range)")
    else:
        velocity = hydro_data.get('velocity', 0.0)
        vel_range = config['hydrologic_signature']['velocity']
        not_matching.append(f"velocity {velocity:.2f} m/s (prefers {vel_range['min']}-{vel_range['max']} m/s)")

    if matches.get('bdi'):
        bdi = hydro_data.get('bdi', 0.5)
        matching.append(f"groundwater influence adequate (BDI={bdi:.2f})")
    else:
        bdi = hydro_data.get('bdi', 0.5)
        threshold = config['hydrologic_signature']['bdi_threshold']
        not_matching.append(f"insufficient groundwater influence (BDI={bdi:.2f}, needs >={threshold:.2f})")

    # Build explanation
    parts = [intro]

    if matching:
        parts.append(" Favorable: " + ", ".join(matching) + ".")

    if not_matching:
        parts.append(" Unfavorable: " + ", ".join(not_matching) + ".")

    return "".join(parts)


def generate_out_of_season_explanation(
    current_date: datetime,
    config: Dict[str, Any]
) -> str:
    """
    Generate explanation for out-of-season prediction.

    Args:
        current_date: Date checked
        config: Hatch configuration

    Returns:
        Explanation string
    """
    hatch_name = config['name']
    window = config['temporal_window']

    # Convert day of year to approximate month/day
    start_day = window['start_day_of_year']
    end_day = window['end_day_of_year']

    # Simple month approximation (30 days per month)
    start_month = (start_day - 1) // 30 + 1
    end_month = (end_day - 1) // 30 + 1

    month_names = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
                   "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

    start_month_name = month_names[min(start_month, 12)]
    end_month_name = month_names[min(end_month, 12)]

    current_day = current_date.timetuple().tm_yday
    current_month_name = month_names[min((current_day - 1) // 30 + 1, 12)]

    return (
        f"{hatch_name} hatches typically occur from {start_month_name} to {end_month_name} "
        f"(days {start_day}-{end_day}). Current date ({current_month_name}, day {current_day}) "
        f"is outside this window."
    )


def get_all_hatch_predictions(
    feature_id: int,
    hydro_data: Dict[str, Any],
    current_date: datetime = None
) -> List[HatchScore]:
    """
    Get hatch predictions for all configured hatches.

    Args:
        feature_id: NHD reach feature_id
        hydro_data: Hydrologic data dictionary
        current_date: Date to check (defaults to now)

    Returns:
        List of HatchScore objects, sorted by likelihood (descending)

    Examples:
        >>> hydro_data = {'flow_percentile': 60, 'velocity': 0.6, 'bdi': 0.7, 'rising_limb': False}
        >>> scores = get_all_hatch_predictions(12345, hydro_data)
        >>> len(scores) > 0
        True
    """
    if current_date is None:
        current_date = datetime.utcnow()

    # Find all hatch config files
    config_dir = Path(__file__).parent.parent.parent / "config" / "hatches"
    hatch_files = list(config_dir.glob("*.yaml"))

    scores = []
    for hatch_file in hatch_files:
        hatch_name = hatch_file.stem  # Filename without extension
        try:
            score = compute_hatch_likelihood(
                feature_id=feature_id,
                hatch=hatch_name,
                hydro_data=hydro_data,
                current_date=current_date
            )
            scores.append(score)
        except Exception as e:
            # Skip invalid configs
            print(f"Warning: Could not load hatch {hatch_name}: {e}")
            continue

    # Sort by likelihood (descending)
    scores.sort(key=lambda x: x.likelihood, reverse=True)

    return scores
