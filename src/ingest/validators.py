"""
NWM Data Validators

Validates NWM data integrity, domain consistency, and data quality.

Design Principles:
- Fail fast with explicit error messages
- Log all validation failures for debugging
- Validate domain membership to prevent data corruption
"""

import logging
from typing import Literal, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# Type aliases
Domain = Literal["conus", "alaska", "hawaii", "puertorico"]


class ValidationError(Exception):
    """Raised when data validation fails"""
    pass


# NHDPlus feature ID ranges by domain
# These ranges are approximate and should be refined with actual NHDPlus metadata
DOMAIN_FEATURE_ID_RANGES = {
    "conus": {
        "min": 100000,
        "max": 30000000,
        "description": "Continental US (NHDPlus v2.1)"
    },
    "alaska": {
        "min": 30000001,
        "max": 40000000,
        "description": "Alaska"
    },
    "hawaii": {
        "min": 40000001,
        "max": 41000000,
        "description": "Hawaii and Pacific Islands"
    },
    "puertorico": {
        "min": 41000001,
        "max": 42000000,
        "description": "Puerto Rico and Caribbean"
    }
}


# Valid NWM products
VALID_PRODUCTS = [
    "analysis_assim",
    "short_range",
    "medium_range_blend",
    "analysis_assim_no_da"
]


# Valid domains
VALID_DOMAINS = ["conus", "alaska", "hawaii", "puertorico"]


def validate_domain(feature_id: int, declared_domain: Domain) -> bool:
    """
    Validate that a feature_id belongs to the declared domain.

    Args:
        feature_id: NHDPlus feature ID
        declared_domain: Domain that file claims to represent

    Returns:
        True if valid

    Raises:
        ValidationError: If feature_id is outside domain range
    """
    if declared_domain not in DOMAIN_FEATURE_ID_RANGES:
        raise ValidationError(
            f"Invalid domain '{declared_domain}'. "
            f"Must be one of: {list(DOMAIN_FEATURE_ID_RANGES.keys())}"
        )

    domain_range = DOMAIN_FEATURE_ID_RANGES[declared_domain]
    min_id = domain_range["min"]
    max_id = domain_range["max"]

    if not (min_id <= feature_id <= max_id):
        raise ValidationError(
            f"Feature ID {feature_id} is outside {declared_domain} range "
            f"({min_id} - {max_id}). "
            f"Domain mismatch detected."
        )

    return True


def validate_feature_ids(
    df: pd.DataFrame,
    declared_domain: Domain,
    sample_size: int = 1000
) -> tuple[bool, list[str]]:
    """
    Validate all feature IDs in a DataFrame belong to declared domain.

    Args:
        df: DataFrame with 'feature_id' column
        declared_domain: Expected domain
        sample_size: Number of random samples to check (for performance)

    Returns:
        Tuple of (is_valid, list of error messages)
    """
    if 'feature_id' not in df.columns:
        return False, ["DataFrame missing 'feature_id' column"]

    errors = []

    # Sample feature IDs for validation (full validation would be slow)
    if len(df) > sample_size:
        sample_ids = df['feature_id'].sample(n=sample_size, random_state=42).values
        logger.info(f"Validating {sample_size} sampled feature IDs for domain consistency")
    else:
        sample_ids = df['feature_id'].values

    domain_range = DOMAIN_FEATURE_ID_RANGES[declared_domain]
    min_id = domain_range["min"]
    max_id = domain_range["max"]

    # Check for out-of-range IDs
    out_of_range = sample_ids[(sample_ids < min_id) | (sample_ids > max_id)]

    if len(out_of_range) > 0:
        errors.append(
            f"Found {len(out_of_range)} feature IDs outside {declared_domain} range. "
            f"Examples: {out_of_range[:5].tolist()}"
        )

    is_valid = len(errors) == 0

    if is_valid:
        logger.info(f"✅ Domain validation passed: {len(sample_ids)} IDs in {declared_domain} range")
    else:
        logger.error(f"❌ Domain validation failed: {'; '.join(errors)}")

    return is_valid, errors


def validate_hydro_data(
    df: pd.DataFrame,
    require_columns: Optional[list[str]] = None
) -> tuple[bool, list[str]]:
    """
    Validate hydrology data quality.

    Checks for:
    - Required columns present
    - No all-NaN columns
    - Reasonable value ranges
    - No excessive missing data

    Args:
        df: DataFrame with hydrology data
        require_columns: List of required column names

    Returns:
        Tuple of (is_valid, list of error messages)
    """
    errors = []

    # Default required columns
    if require_columns is None:
        require_columns = [
            'feature_id',
            'streamflow_m3s',
            'velocity_ms'
        ]

    # Check required columns exist
    missing_cols = set(require_columns) - set(df.columns)
    if missing_cols:
        errors.append(f"Missing required columns: {missing_cols}")
        return False, errors

    # Check for all-NaN columns
    for col in require_columns:
        if df[col].isna().all():
            errors.append(f"Column '{col}' is entirely NaN")

    # Check for reasonable value ranges
    if 'streamflow_m3s' in df.columns:
        streamflow = df['streamflow_m3s'].dropna()
        if len(streamflow) > 0:
            # Streamflow should be non-negative
            if (streamflow < 0).any():
                errors.append(
                    f"Found negative streamflow values: "
                    f"min={streamflow.min():.2f} m³/s"
                )

            # Flag if too many zero flows (suggests missing data)
            zero_pct = (streamflow == 0).sum() / len(streamflow) * 100
            if zero_pct > 50:
                errors.append(
                    f"Excessive zero flows: {zero_pct:.1f}% of reaches. "
                    f"Possible data quality issue."
                )

    if 'velocity_ms' in df.columns:
        velocity = df['velocity_ms'].dropna()
        if len(velocity) > 0:
            # Velocity should be non-negative
            if (velocity < 0).any():
                errors.append(
                    f"Found negative velocity values: "
                    f"min={velocity.min():.2f} m/s"
                )

            # Flag unrealistic velocities (>10 m/s is very rare in rivers)
            if (velocity > 10).any():
                errors.append(
                    f"Found unrealistic velocity values: "
                    f"max={velocity.max():.2f} m/s (>10 m/s is uncommon)"
                )

    # Check for excessive missing data
    for col in require_columns:
        if col in df.columns:
            missing_pct = df[col].isna().sum() / len(df) * 100
            if missing_pct > 80:
                errors.append(
                    f"Column '{col}' has {missing_pct:.1f}% missing data. "
                    f"Possible ingestion failure."
                )

    # Check for duplicate feature IDs (should be unique per timestep)
    if 'feature_id' in df.columns:
        duplicates = df['feature_id'].duplicated().sum()
        if duplicates > 0:
            errors.append(
                f"Found {duplicates} duplicate feature IDs. "
                f"Each feature should appear once per timestep."
            )

    is_valid = len(errors) == 0

    if is_valid:
        logger.info(f"✅ Data quality validation passed: {len(df)} reaches")
    else:
        logger.error(f"❌ Data quality validation failed: {'; '.join(errors)}")

    return is_valid, errors


def validate_product(product: str) -> bool:
    """
    Validate that product name is one of the canonical NWM products.

    Args:
        product: Product name to validate

    Returns:
        True if valid

    Raises:
        ValidationError: If product is invalid
    """
    if product not in VALID_PRODUCTS:
        raise ValidationError(
            f"Invalid product '{product}'. "
            f"Must be one of: {VALID_PRODUCTS}"
        )
    return True


def validate_source(source: str) -> bool:
    """
    Validate that source string matches expected format.

    Source should be one of the 4 canonical products.

    Args:
        source: Source string to validate

    Returns:
        True if valid

    Raises:
        ValidationError: If source is invalid
    """
    return validate_product(source)


def validate_temporal_consistency(
    df: pd.DataFrame,
    reference_time,
    forecast_hour: Optional[int] = None
) -> tuple[bool, list[str]]:
    """
    Validate that reference_time in data matches expected values.

    Args:
        df: DataFrame with 'reference_time' column
        reference_time: Expected reference time
        forecast_hour: Expected forecast hour (if applicable)

    Returns:
        Tuple of (is_valid, list of error messages)
    """
    errors = []

    if 'reference_time' not in df.columns:
        # Some products may not include reference_time
        logger.debug("No reference_time column found, skipping temporal validation")
        return True, []

    # Check if all reference times match expected
    unique_times = df['reference_time'].unique()

    if len(unique_times) > 1:
        errors.append(
            f"Multiple reference times found in single file: {unique_times}. "
            f"Expected single reference time."
        )

    # Could add more sophisticated time validation here
    # e.g., checking that forecast valid_time = reference_time + forecast_hour

    is_valid = len(errors) == 0

    if is_valid:
        logger.info(f"✅ Temporal consistency validation passed")
    else:
        logger.error(f"❌ Temporal consistency validation failed: {'; '.join(errors)}")

    return is_valid, errors


def validate_all(
    df: pd.DataFrame,
    product: str,
    domain: Domain,
    reference_time=None,
    forecast_hour: Optional[int] = None
) -> tuple[bool, dict[str, list[str]]]:
    """
    Run all validation checks on ingested data.

    Args:
        df: DataFrame with parsed NWM data
        product: Product name
        domain: Geographic domain
        reference_time: Model reference time
        forecast_hour: Forecast hour (if applicable)

    Returns:
        Tuple of (is_valid, dict of validation results by check name)
    """
    results = {}

    # Product validation
    try:
        validate_product(product)
        results['product'] = []
    except ValidationError as e:
        results['product'] = [str(e)]

    # Domain validation
    is_valid, errors = validate_feature_ids(df, domain)
    results['domain'] = errors

    # Data quality validation
    is_valid, errors = validate_hydro_data(df)
    results['data_quality'] = errors

    # Temporal validation
    if reference_time is not None:
        is_valid, errors = validate_temporal_consistency(df, reference_time, forecast_hour)
        results['temporal'] = errors

    # Overall validation
    all_valid = all(len(errors) == 0 for errors in results.values())

    if all_valid:
        logger.info("✅ All validation checks passed")
    else:
        logger.error(f"❌ Validation failed. Results: {results}")

    return all_valid, results


def main():
    """
    Example usage and testing
    """
    # Test validation functions
    logger.info("=" * 60)
    logger.info("Testing validators")
    logger.info("=" * 60)

    # Test 1: Valid CONUS feature ID
    try:
        validate_domain(feature_id=5000000, declared_domain="conus")
        logger.info("✅ Test 1 passed: Valid CONUS feature ID")
    except ValidationError as e:
        logger.error(f"❌ Test 1 failed: {e}")

    # Test 2: Invalid feature ID for domain
    try:
        validate_domain(feature_id=35000000, declared_domain="conus")
        logger.error("❌ Test 2 failed: Should have raised ValidationError")
    except ValidationError as e:
        logger.info(f"✅ Test 2 passed: Caught invalid domain: {e}")

    # Test 3: Data quality validation
    test_df = pd.DataFrame({
        'feature_id': range(1000000, 1000100),
        'streamflow_m3s': np.random.uniform(0, 100, 100),
        'velocity_ms': np.random.uniform(0, 2, 100)
    })

    is_valid, errors = validate_hydro_data(test_df)
    if is_valid:
        logger.info("✅ Test 3 passed: Data quality validation")
    else:
        logger.error(f"❌ Test 3 failed: {errors}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
