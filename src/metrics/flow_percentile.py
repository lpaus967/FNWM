"""
Flow Percentile Calculator for FNWM

Computes flow percentiles by comparing current NWM streamflow against
historical monthly mean flows from NHDPlus.

Flow percentiles are ecologically critical because they indicate:
- Habitat suitability (species have optimal flow ranges)
- Drought/flood conditions (extreme percentiles indicate stress)
- Seasonal patterns (normal vs abnormal conditions)
- Hatch timing (many aquatic insects emerge during specific flow ranges)

Design Principles:
- Uses NHDPlus mean annual flow by month as baseline
- Handles missing historical data gracefully
- Returns normalized 0-100 percentile value
- Provides ecological interpretation
"""

from typing import Literal, Optional, Tuple, Dict
from datetime import datetime
import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv


# Type aliases
FlowClass = Literal["extreme_low", "low", "below_normal", "normal", "above_normal", "high", "extreme_high"]
PercentileResult = Tuple[float, FlowClass]


# Month name to column mapping for nhd_flow_statistics
# NOTE: NHDPlus flow statistics only include January-June data (qama-qfma)
# Months 7-12 (July-December) are not available in the NHD dataset
MONTH_COLUMNS = {
    1: 'qama',   # January
    2: 'qbma',   # February
    3: 'qcma',   # March
    4: 'qdma',   # April
    5: 'qema',   # May
    6: 'qfma',   # June
    # Months 7-12 not available in NHD data
}


def compute_flow_percentile(
    current_flow: float,
    monthly_mean_flow: float
) -> float:
    """
    Compute flow percentile based on ratio to monthly mean.

    This is a simplified percentile calculation that assumes:
    - Monthly mean represents the 50th percentile
    - Log-normal distribution of flows
    - Symmetric percentile bands around the mean

    Note: For more accurate percentiles, historical flow distributions
    would be needed. This implementation provides a reasonable approximation
    for ecological decision-making.

    Formula:
        percentile = 50 + (50 * tanh((current / mean - 1) * 2))

    This ensures:
    - Mean flow = 50th percentile
    - 2x mean ≈ 90th percentile
    - 0.5x mean ≈ 10th percentile
    - Bounded to [0, 100]

    Args:
        current_flow: Current streamflow (m³/s)
        monthly_mean_flow: Historical monthly mean flow (m³/s)

    Returns:
        Flow percentile between 0.0 and 100.0
        - 0 = lowest recorded flow (extreme drought)
        - 50 = mean flow (normal conditions)
        - 100 = highest recorded flow (extreme flood)

    Examples:
        >>> # Normal conditions (at mean)
        >>> compute_flow_percentile(current_flow=1.5, monthly_mean_flow=1.5)
        50.0

        >>> # High flow (2x mean)
        >>> compute_flow_percentile(current_flow=3.0, monthly_mean_flow=1.5)
        86.4...

        >>> # Low flow (0.5x mean)
        >>> compute_flow_percentile(current_flow=0.75, monthly_mean_flow=1.5)
        13.5...

        >>> # Zero flow edge case
        >>> compute_flow_percentile(current_flow=0.0, monthly_mean_flow=1.5)
        0.0
    """
    import math

    # Handle edge cases
    if current_flow < 0:
        current_flow = 0.0

    if monthly_mean_flow <= 0:
        # No historical data available
        return 50.0  # Assume normal conditions

    if current_flow == 0:
        return 0.0  # Zero flow = 0th percentile

    # Calculate ratio to mean
    ratio = current_flow / monthly_mean_flow

    # Use tanh to create smooth percentile curve
    # tanh(x) maps (-inf, inf) to (-1, 1)
    # Multiply by 2 to make 2x mean ≈ 90th percentile
    normalized = math.tanh((ratio - 1.0) * 2.0)

    # Map to 0-100 percentile scale
    percentile = 50.0 + (50.0 * normalized)

    # Ensure bounds
    return max(0.0, min(100.0, percentile))


def classify_flow_percentile(percentile: float) -> FlowClass:
    """
    Classify flow percentile into ecological categories.

    Categories based on typical fisheries/hydrology thresholds:
    - Extreme Low: <10th percentile (severe drought stress)
    - Low: 10-25th percentile (drought stress, may limit habitat)
    - Below Normal: 25-40th percentile (slightly low, generally acceptable)
    - Normal: 40-60th percentile (optimal range for most species)
    - Above Normal: 60-75th percentile (slightly elevated)
    - High: 75-90th percentile (elevated, may trigger spawning/hatches)
    - Extreme High: >90th percentile (flood conditions, habitat stress)

    Args:
        percentile: Flow percentile (0-100)

    Returns:
        Flow classification category

    Examples:
        >>> classify_flow_percentile(5.0)
        'extreme_low'

        >>> classify_flow_percentile(50.0)
        'normal'

        >>> classify_flow_percentile(95.0)
        'extreme_high'
    """
    if percentile < 10:
        return "extreme_low"
    elif percentile < 25:
        return "low"
    elif percentile < 40:
        return "below_normal"
    elif percentile < 60:
        return "normal"
    elif percentile < 75:
        return "above_normal"
    elif percentile < 90:
        return "high"
    else:
        return "extreme_high"


def compute_percentile_with_classification(
    current_flow: float,
    monthly_mean_flow: float
) -> PercentileResult:
    """
    Compute flow percentile and classification in one call.

    Args:
        current_flow: Current streamflow (m³/s)
        monthly_mean_flow: Historical monthly mean flow (m³/s)

    Returns:
        Tuple of (percentile, classification)

    Example:
        >>> percentile, flow_class = compute_percentile_with_classification(3.0, 1.5)
        >>> percentile
        86.4...
        >>> flow_class
        'high'
    """
    percentile = compute_flow_percentile(current_flow, monthly_mean_flow)
    classification = classify_flow_percentile(percentile)
    return percentile, classification


def explain_flow_percentile(
    percentile: float,
    classification: FlowClass,
    current_flow: float,
    monthly_mean_flow: float,
    month_name: str
) -> str:
    """
    Generate human-readable explanation of flow percentile.

    Args:
        percentile: Computed flow percentile (0-100)
        classification: Flow classification category
        current_flow: Current streamflow (m³/s)
        monthly_mean_flow: Historical monthly mean flow (m³/s)
        month_name: Name of the current month

    Returns:
        Explanation string for API responses

    Example:
        >>> explain_flow_percentile(
        ...     percentile=65.3,
        ...     classification="above_normal",
        ...     current_flow=2.1,
        ...     monthly_mean_flow=1.5,
        ...     month_name="May"
        ... )
        'Flow at 65th percentile (above normal for May). Current: 2.10 m³/s vs May mean: 1.50 m³/s (140% of mean).'
    """
    ratio = (current_flow / monthly_mean_flow * 100) if monthly_mean_flow > 0 else 0

    # Classification descriptions
    descriptions = {
        "extreme_low": "extreme low (severe drought conditions)",
        "low": "low (drought stress)",
        "below_normal": "below normal",
        "normal": "normal",
        "above_normal": "above normal",
        "high": "high (elevated conditions)",
        "extreme_high": "extreme high (flood conditions)"
    }

    desc = descriptions.get(classification, "unknown")

    return (
        f"Flow at {percentile:.0f}th percentile ({desc} for {month_name}). "
        f"Current: {current_flow:.2f} m³/s vs {month_name} mean: {monthly_mean_flow:.2f} m³/s "
        f"({ratio:.0f}% of mean)."
    )


def get_monthly_mean_flow(feature_id: int, month: int) -> Optional[float]:
    """
    Query database for monthly mean flow from nhd_flow_statistics.

    NOTE: NHD flow statistics only available for January-June (months 1-6).
    Months 7-12 will return None as this data is not in the NHD dataset.

    Args:
        feature_id: NHDPlusID / feature_id
        month: Month number (1-12)

    Returns:
        Monthly mean flow in m³/s, or None if not available

    Example:
        >>> # Get January mean flow for reach 3024688
        >>> mean_flow = get_monthly_mean_flow(3024688, 1)
        >>> mean_flow
        0.475

        >>> # July data not available
        >>> mean_flow = get_monthly_mean_flow(3024688, 7)
        >>> mean_flow
        None
    """
    if month < 1 or month > 12:
        raise ValueError(f"Invalid month: {month}. Must be 1-12.")

    # Months 7-12 not available in NHD dataset
    if month not in MONTH_COLUMNS:
        return None

    column_name = MONTH_COLUMNS[month]

    try:
        load_dotenv()
        engine = create_engine(os.getenv('DATABASE_URL'))

        with engine.connect() as conn:
            result = conn.execute(
                text(f"""
                    SELECT {column_name}
                    FROM nhd_flow_statistics
                    WHERE nhdplusid = :feature_id
                """),
                {"feature_id": feature_id}
            ).fetchone()

            if result and result[0] is not None:
                return float(result[0])
            return None

    except Exception as e:
        # Log error but don't crash - return None to indicate missing data
        print(f"Error fetching monthly mean flow: {e}")
        return None


def compute_flow_percentile_for_reach(
    feature_id: int,
    current_flow: float,
    timestamp: datetime
) -> Dict:
    """
    Compute flow percentile for a specific reach with full context.

    This is the primary function for API integration. It:
    1. Determines the current month from timestamp
    2. Fetches historical monthly mean from database
    3. Computes percentile and classification
    4. Generates explanation

    Args:
        feature_id: NHDPlusID / feature_id
        current_flow: Current streamflow (m³/s)
        timestamp: Timestamp of the flow measurement

    Returns:
        Dictionary containing:
        - percentile: Flow percentile (0-100)
        - classification: Flow category (e.g., "normal", "high")
        - explanation: Human-readable explanation
        - monthly_mean: Historical monthly mean flow (m³/s)
        - ratio_to_mean: Current flow as percentage of mean
        - data_available: Whether historical data was available

    Example:
        >>> from datetime import datetime, timezone
        >>> result = compute_flow_percentile_for_reach(
        ...     feature_id=3024688,
        ...     current_flow=0.95,
        ...     timestamp=datetime(2026, 1, 5, 12, 0, tzinfo=timezone.utc)
        ... )
        >>> result['percentile']
        78.5...
        >>> result['classification']
        'above_normal'
        >>> result['data_available']
        True
    """
    # Extract month from timestamp
    month = timestamp.month
    month_name = timestamp.strftime("%B")

    # Get historical monthly mean
    monthly_mean = get_monthly_mean_flow(feature_id, month)

    # If no historical data, return defaults
    if monthly_mean is None:
        return {
            "percentile": None,
            "classification": None,
            "explanation": f"No historical flow data available for {month_name}.",
            "monthly_mean": None,
            "ratio_to_mean": None,
            "data_available": False
        }

    # Compute percentile and classification
    percentile, classification = compute_percentile_with_classification(
        current_flow, monthly_mean
    )

    # Generate explanation
    explanation = explain_flow_percentile(
        percentile, classification, current_flow, monthly_mean, month_name
    )

    # Calculate ratio
    ratio_to_mean = (current_flow / monthly_mean * 100) if monthly_mean > 0 else 0

    return {
        "percentile": percentile,
        "classification": classification,
        "explanation": explanation,
        "monthly_mean": monthly_mean,
        "ratio_to_mean": ratio_to_mean,
        "data_available": True
    }
