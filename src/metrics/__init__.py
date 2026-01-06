"""
Derived Hydrology Metrics for FNWM

This module contains algorithms for computing derived metrics from raw NWM data.

Available metrics:
- Rising Limb Detection (Ticket 2.1) ✅
- Baseflow Dominance Index - BDI (Ticket 2.2) ✅
- Velocity Suitability Classifier (Ticket 2.3) ✅
- Flow Percentile Calculator (Epic 7) ✅
- Thermal Suitability Index - TSI (Ticket 3.2) ✅
"""

from .rising_limb import (
    detect_rising_limb,
    detect_rising_limb_for_reach,
    RisingLimbConfig,
    load_default_config,
    explain_detection
)

from .baseflow import (
    compute_bdi,
    classify_bdi,
    compute_bdi_with_classification,
    explain_bdi as explain_bdi_result,
    compute_bdi_for_reach,
    compute_bdi_timeseries_for_reach,
    compute_bdi_statistics
)

from .velocity import (
    SpeciesVelocityConfig,
    classify_velocity,
    explain_velocity_suitability,
    classify_velocity_for_reach,
    classify_velocity_timeseries_for_reach,
    compute_velocity_statistics,
    load_species_config
)

from .flow_percentile import (
    compute_flow_percentile,
    classify_flow_percentile,
    compute_percentile_with_classification,
    explain_flow_percentile,
    get_monthly_mean_flow,
    compute_flow_percentile_for_reach,
    FlowClass,
    PercentileResult
)

from .thermal_suitability import (
    ThermalSuitabilityCalculator,
    compute_thermal_suitability
)

__all__ = [
    # Rising Limb Detection
    'detect_rising_limb',
    'detect_rising_limb_for_reach',
    'RisingLimbConfig',
    'load_default_config',
    'explain_detection',
    # Baseflow Dominance Index
    'compute_bdi',
    'classify_bdi',
    'compute_bdi_with_classification',
    'explain_bdi_result',
    'compute_bdi_for_reach',
    'compute_bdi_timeseries_for_reach',
    'compute_bdi_statistics',
    # Velocity Suitability
    'SpeciesVelocityConfig',
    'classify_velocity',
    'explain_velocity_suitability',
    'classify_velocity_for_reach',
    'classify_velocity_timeseries_for_reach',
    'compute_velocity_statistics',
    'load_species_config',
    # Flow Percentile
    'compute_flow_percentile',
    'classify_flow_percentile',
    'compute_percentile_with_classification',
    'explain_flow_percentile',
    'get_monthly_mean_flow',
    'compute_flow_percentile_for_reach',
    'FlowClass',
    'PercentileResult',
    # Thermal Suitability
    'ThermalSuitabilityCalculator',
    'compute_thermal_suitability'
]
