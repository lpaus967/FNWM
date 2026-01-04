"""
Baseflow Dominance Index (BDI) for FNWM

Computes the ratio of baseflow (groundwater-fed) to total streamflow.

BDI is ecologically critical because it indicates:
- Thermal stability (high BDI = thermal refuge potential)
- Flow stability (high BDI = less flashy, more predictable)
- Habitat quality (high BDI = preferred by many species, especially trout)
- Drought resilience (high BDI = maintains flow during dry periods)

Design Principles:
- Deterministic and reproducible
- Handles edge cases (zero flow, missing data)
- Returns normalized 0-1 value
- Provides ecological interpretation
"""

from typing import Literal, Optional, Tuple
import pandas as pd
import numpy as np
from datetime import datetime


# Type aliases
BDIClass = Literal["groundwater_fed", "mixed", "storm_dominated"]
BDIResult = Tuple[float, BDIClass]


def compute_bdi(
    q_btm_vert: float,
    q_bucket: float,
    q_sfc_lat: float
) -> float:
    """
    Compute Baseflow Dominance Index (BDI).

    BDI measures the fraction of streamflow derived from groundwater sources
    (deep aquifer + shallow subsurface) versus surface runoff.

    Formula:
        BDI = (q_btm_vert + q_bucket) / (q_btm_vert + q_bucket + q_sfc_lat)

    Args:
        q_btm_vert: Deep groundwater contribution (m3/s)
                    From NWM variable: qBtmVertRunoff
        q_bucket: Shallow subsurface contribution (m3/s)
                  From NWM variable: qBucket
        q_sfc_lat: Surface runoff contribution (m3/s)
                   From NWM variable: qSfcLatRunoff

    Returns:
        BDI value between 0.0 and 1.0:
        - 0.0 = 100% storm-dominated (all surface runoff)
        - 1.0 = 100% baseflow-dominated (all groundwater)
        - 0.5 = Equal mix of baseflow and surface runoff

    Examples:
        >>> # Spring creek (high baseflow)
        >>> compute_bdi(q_btm_vert=5.0, q_bucket=3.0, q_sfc_lat=0.5)
        0.941...

        >>> # Storm-dominated stream
        >>> compute_bdi(q_btm_vert=0.5, q_bucket=0.3, q_sfc_lat=10.0)
        0.074...

        >>> # Zero flow edge case
        >>> compute_bdi(q_btm_vert=0.0, q_bucket=0.0, q_sfc_lat=0.0)
        0.0
    """
    # Handle negative values (shouldn't occur, but be defensive)
    q_btm_vert = max(0.0, q_btm_vert)
    q_bucket = max(0.0, q_bucket)
    q_sfc_lat = max(0.0, q_sfc_lat)

    # Compute total flow
    total = q_btm_vert + q_bucket + q_sfc_lat

    # Edge case: zero total flow
    if total == 0.0 or np.isnan(total):
        return 0.0

    # Compute baseflow components
    baseflow = q_btm_vert + q_bucket

    # Return ratio (guaranteed to be between 0 and 1)
    bdi = baseflow / total

    return bdi


def classify_bdi(bdi: float) -> BDIClass:
    """
    Classify BDI into ecological categories.

    Classification thresholds based on hydrologic literature:
    - Groundwater-fed: BDI >= 0.65 (thermal refuge, stable flow)
    - Mixed: 0.35 <= BDI < 0.65 (variable conditions)
    - Storm-dominated: BDI < 0.35 (flashy, thermally variable)

    Args:
        bdi: Baseflow Dominance Index (0.0 to 1.0)

    Returns:
        Classification: "groundwater_fed", "mixed", or "storm_dominated"

    Examples:
        >>> classify_bdi(0.85)
        'groundwater_fed'
        >>> classify_bdi(0.50)
        'mixed'
        >>> classify_bdi(0.20)
        'storm_dominated'
    """
    if bdi >= 0.65:
        return "groundwater_fed"
    elif bdi >= 0.35:
        return "mixed"
    else:
        return "storm_dominated"


def compute_bdi_with_classification(
    q_btm_vert: float,
    q_bucket: float,
    q_sfc_lat: float
) -> BDIResult:
    """
    Compute BDI and classify into ecological category.

    Args:
        q_btm_vert: Deep groundwater contribution (m3/s)
        q_bucket: Shallow subsurface contribution (m3/s)
        q_sfc_lat: Surface runoff contribution (m3/s)

    Returns:
        Tuple of (bdi_value, classification)

    Examples:
        >>> bdi, classification = compute_bdi_with_classification(5.0, 3.0, 0.5)
        >>> bdi
        0.941...
        >>> classification
        'groundwater_fed'
    """
    bdi = compute_bdi(q_btm_vert, q_bucket, q_sfc_lat)
    classification = classify_bdi(bdi)
    return bdi, classification


def explain_bdi(bdi: float, classification: Optional[BDIClass] = None) -> str:
    """
    Generate human-readable explanation of BDI.

    Args:
        bdi: Baseflow Dominance Index (0.0 to 1.0)
        classification: Optional pre-computed classification

    Returns:
        Explanation string describing the BDI and its ecological implications

    Examples:
        >>> explain_bdi(0.85, "groundwater_fed")
        'BDI: 0.85 (groundwater-fed). This stream is dominated by groundwater sources, providing thermal stability and consistent flow. Excellent habitat for cold-water species.'
    """
    if classification is None:
        classification = classify_bdi(bdi)

    explanations = {
        "groundwater_fed": (
            f"BDI: {bdi:.2f} (groundwater-fed). This stream is dominated by groundwater sources, "
            "providing thermal stability and consistent flow. Excellent habitat for cold-water species."
        ),
        "mixed": (
            f"BDI: {bdi:.2f} (mixed sources). This stream receives moderate contributions from both "
            "groundwater and surface runoff. Flow and temperature conditions are moderately variable."
        ),
        "storm_dominated": (
            f"BDI: {bdi:.2f} (storm-dominated). This stream is primarily fed by surface runoff, "
            "resulting in flashy flows and greater thermal variability. Less stable habitat conditions."
        )
    }

    return explanations[classification]


def compute_bdi_timeseries(
    q_btm_vert_series: pd.Series,
    q_bucket_series: pd.Series,
    q_sfc_lat_series: pd.Series
) -> pd.Series:
    """
    Compute BDI for a time series of flow components.

    Args:
        q_btm_vert_series: Time series of deep groundwater (m3/s)
        q_bucket_series: Time series of shallow subsurface (m3/s)
        q_sfc_lat_series: Time series of surface runoff (m3/s)

    Returns:
        Time series of BDI values (0.0 to 1.0)

    Note:
        All series must have the same index (timestamps).
    """
    # Align series (in case of missing data)
    df = pd.DataFrame({
        'q_btm_vert': q_btm_vert_series,
        'q_bucket': q_bucket_series,
        'q_sfc_lat': q_sfc_lat_series
    })

    # Drop rows with any NaN values
    df = df.dropna()

    # Compute BDI for each timestep
    bdi_series = df.apply(
        lambda row: compute_bdi(row['q_btm_vert'], row['q_bucket'], row['q_sfc_lat']),
        axis=1
    )

    return bdi_series


def compute_bdi_statistics(bdi_series: pd.Series) -> dict:
    """
    Compute summary statistics for BDI time series.

    Args:
        bdi_series: Time series of BDI values

    Returns:
        Dictionary with statistical summary:
        - mean: Average BDI
        - median: Median BDI
        - std: Standard deviation
        - min/max: Range
        - dominant_class: Most common classification
        - stability: Coefficient of variation (lower = more stable)
    """
    if len(bdi_series) == 0:
        return {
            'mean': None,
            'median': None,
            'std': None,
            'min': None,
            'max': None,
            'dominant_class': None,
            'stability': None
        }

    mean_bdi = bdi_series.mean()
    dominant_class = classify_bdi(mean_bdi)

    # Coefficient of variation (measure of stability)
    # Lower CV = more stable BDI over time
    cv = bdi_series.std() / mean_bdi if mean_bdi > 0 else None

    return {
        'mean': mean_bdi,
        'median': bdi_series.median(),
        'std': bdi_series.std(),
        'min': bdi_series.min(),
        'max': bdi_series.max(),
        'dominant_class': dominant_class,
        'stability': 1.0 - min(cv, 1.0) if cv is not None else None  # 0=unstable, 1=stable
    }


def compute_bdi_for_reach(
    feature_id: int,
    valid_time: datetime,
    db_connection
) -> Optional[Tuple[float, BDIClass]]:
    """
    Compute BDI for a specific reach at a specific time from database.

    Args:
        feature_id: NHDPlus feature ID
        valid_time: Timestamp for BDI calculation (UTC timezone-aware)
        db_connection: SQLAlchemy connection or engine

    Returns:
        Tuple of (bdi_value, classification) or None if data not available

    Example:
        >>> from datetime import datetime, timezone
        >>> from sqlalchemy import create_engine
        >>> engine = create_engine(database_url)
        >>> with engine.begin() as conn:
        ...     bdi, classification = compute_bdi_for_reach(
        ...         feature_id=12345,
        ...         valid_time=datetime(2026, 1, 3, 12, 0, tzinfo=timezone.utc),
        ...         db_connection=conn
        ...     )
    """
    from sqlalchemy import text

    # Query flow components for the reach at the specified time
    query = text("""
        SELECT variable, value
        FROM hydro_timeseries
        WHERE feature_id = :feature_id
          AND valid_time = :valid_time
          AND variable IN ('qBtmVertRunoff', 'qBucket', 'qSfcLatRunoff')
    """)

    result = db_connection.execute(
        query,
        {
            'feature_id': feature_id,
            'valid_time': valid_time
        }
    )

    # Parse results
    components = {row[0]: row[1] for row in result}

    # Check if all required components are present
    required = ['qBtmVertRunoff', 'qBucket', 'qSfcLatRunoff']
    if not all(var in components for var in required):
        return None

    # Compute BDI
    bdi = compute_bdi(
        q_btm_vert=components['qBtmVertRunoff'],
        q_bucket=components['qBucket'],
        q_sfc_lat=components['qSfcLatRunoff']
    )

    classification = classify_bdi(bdi)

    return bdi, classification


def compute_bdi_timeseries_for_reach(
    feature_id: int,
    start_time: datetime,
    end_time: datetime,
    db_connection
) -> pd.DataFrame:
    """
    Compute BDI time series for a reach from database.

    Args:
        feature_id: NHDPlus feature ID
        start_time: Start of time window (UTC timezone-aware)
        end_time: End of time window (UTC timezone-aware)
        db_connection: SQLAlchemy connection or engine

    Returns:
        DataFrame with columns:
        - valid_time: Timestamp
        - bdi: BDI value
        - classification: BDI classification
        - q_btm_vert, q_bucket, q_sfc_lat: Flow components
    """
    from sqlalchemy import text

    # Query flow components
    query = text("""
        SELECT valid_time, variable, value
        FROM hydro_timeseries
        WHERE feature_id = :feature_id
          AND valid_time BETWEEN :start_time AND :end_time
          AND variable IN ('qBtmVertRunoff', 'qBucket', 'qSfcLatRunoff')
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

    # Parse into DataFrame
    rows = []
    for valid_time, variable, value in result:
        rows.append({
            'valid_time': valid_time,
            'variable': variable,
            'value': value
        })

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)

    # Pivot to get one row per timestamp with all variables as columns
    df_pivot = df.pivot(index='valid_time', columns='variable', values='value').reset_index()

    # Check if all required columns exist
    required_cols = ['qBtmVertRunoff', 'qBucket', 'qSfcLatRunoff']
    if not all(col in df_pivot.columns for col in required_cols):
        return pd.DataFrame()

    # Compute BDI for each timestamp
    df_pivot['bdi'] = df_pivot.apply(
        lambda row: compute_bdi(
            row['qBtmVertRunoff'],
            row['qBucket'],
            row['qSfcLatRunoff']
        ),
        axis=1
    )

    df_pivot['classification'] = df_pivot['bdi'].apply(classify_bdi)

    # Rename columns for clarity
    df_pivot = df_pivot.rename(columns={
        'qBtmVertRunoff': 'q_btm_vert',
        'qBucket': 'q_bucket',
        'qSfcLatRunoff': 'q_sfc_lat'
    })

    return df_pivot


# Example usage
if __name__ == "__main__":
    print("Baseflow Dominance Index (BDI) - Example Usage")
    print("=" * 70)
    print()

    # Example 1: Spring creek (high baseflow)
    print("Example 1: Spring Creek (Groundwater-Fed)")
    print("-" * 70)
    q_btm = 5.0
    q_bucket = 3.0
    q_sfc = 0.5
    print(f"Flow components:")
    print(f"  Deep groundwater (q_btm_vert): {q_btm} m3/s")
    print(f"  Shallow subsurface (q_bucket): {q_bucket} m3/s")
    print(f"  Surface runoff (q_sfc_lat): {q_sfc} m3/s")
    print()

    bdi, classification = compute_bdi_with_classification(q_btm, q_bucket, q_sfc)
    print(f"BDI: {bdi:.3f}")
    print(f"Classification: {classification}")
    print(f"Explanation: {explain_bdi(bdi, classification)}")
    print()

    # Example 2: Storm-dominated stream
    print("Example 2: Storm-Dominated Stream")
    print("-" * 70)
    q_btm = 0.5
    q_bucket = 0.3
    q_sfc = 10.0
    print(f"Flow components:")
    print(f"  Deep groundwater (q_btm_vert): {q_btm} m3/s")
    print(f"  Shallow subsurface (q_bucket): {q_bucket} m3/s")
    print(f"  Surface runoff (q_sfc_lat): {q_sfc} m3/s")
    print()

    bdi, classification = compute_bdi_with_classification(q_btm, q_bucket, q_sfc)
    print(f"BDI: {bdi:.3f}")
    print(f"Classification: {classification}")
    print(f"Explanation: {explain_bdi(bdi, classification)}")
    print()

    # Example 3: Mixed source stream
    print("Example 3: Mixed Source Stream")
    print("-" * 70)
    q_btm = 2.0
    q_bucket = 1.5
    q_sfc = 3.5
    print(f"Flow components:")
    print(f"  Deep groundwater (q_btm_vert): {q_btm} m3/s")
    print(f"  Shallow subsurface (q_bucket): {q_bucket} m3/s")
    print(f"  Surface runoff (q_sfc_lat): {q_sfc} m3/s")
    print()

    bdi, classification = compute_bdi_with_classification(q_btm, q_bucket, q_sfc)
    print(f"BDI: {bdi:.3f}")
    print(f"Classification: {classification}")
    print(f"Explanation: {explain_bdi(bdi, classification)}")
    print()

    # Example 4: Edge case - zero flow
    print("Example 4: Zero Flow (Edge Case)")
    print("-" * 70)
    bdi = compute_bdi(0.0, 0.0, 0.0)
    print(f"BDI: {bdi:.3f}")
    print(f"Classification: {classify_bdi(bdi)}")
    print()
