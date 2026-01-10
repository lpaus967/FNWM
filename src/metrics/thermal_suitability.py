"""
Thermal Suitability Index (TSI) Calculator

Computes thermal habitat suitability for fish species based on air temperature data
from Open-Meteo API, with enhanced water temperature prediction models.

Design Principles:
- Uses Mohseni S-curve model for nonlinear air-water relationship
- Incorporates groundwater thermal buffering (BDI-based)
- Accounts for elevation and reach-specific characteristics
- Species-specific optimal temperature ranges from config
- Gradient scoring for sub-optimal conditions
- Returns normalized 0-1 score (1 = optimal, 0 = unsuitable)
"""

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from sqlalchemy import Engine, text
import numpy as np

logger = logging.getLogger(__name__)

# Import enhanced prediction model (lazy import to avoid circular dependencies)
def _get_predictor(engine):
    """Lazy import of WaterTemperaturePredictor."""
    from temperature.prediction import WaterTemperaturePredictor
    return WaterTemperaturePredictor(engine)


# Legacy simple model offset (kept for comparison/fallback)
# Stream water is typically 2-5°C cooler than air temperature
AIR_TO_WATER_OFFSET_LEGACY = 3.0


class ThermalSuitabilityCalculator:
    """Calculate thermal suitability scores for fish habitat."""

    def __init__(self, engine: Engine, use_enhanced_model: bool = True):
        """
        Initialize TSI calculator.

        Args:
            engine: SQLAlchemy database engine
            use_enhanced_model: If True, use Mohseni+BDI model; if False, use legacy linear model
        """
        self.engine = engine
        self.use_enhanced_model = use_enhanced_model
        self.temp_predictor = None
        if use_enhanced_model:
            self.temp_predictor = _get_predictor(engine)

    def _air_to_water_temp_legacy(self, air_temp: float) -> float:
        """
        Legacy simple linear conversion (kept for comparison).

        Uses conservative offset to estimate stream water temperature.

        Args:
            air_temp: Air temperature in Celsius

        Returns:
            Estimated water temperature in Celsius
        """
        return air_temp - AIR_TO_WATER_OFFSET_LEGACY

    def _predict_water_temp_enhanced(
        self,
        nhdplusid: int,
        air_temp: float,
        timeframe: str = "now",
        cloud_cover: Optional[float] = None
    ) -> Tuple[float, Dict]:
        """
        Predict water temperature using enhanced Mohseni + BDI model.

        Args:
            nhdplusid: NHD reach identifier
            air_temp: Air temperature in Celsius
            timeframe: Time period ('now', 'today', 'outlook')
            cloud_cover: Cloud cover percentage (0-100), optional

        Returns:
            Tuple of (water_temp, metadata_dict)
        """
        try:
            return self.temp_predictor.predict_for_reach(
                nhdplusid=nhdplusid,
                air_temp=air_temp,
                timeframe=timeframe,
                cloud_cover_pct=cloud_cover
            )
        except Exception as e:
            logger.warning(
                f"Enhanced prediction failed for reach {nhdplusid}: {e}. "
                "Falling back to legacy model."
            )
            # Fallback to legacy model
            legacy_temp = self._air_to_water_temp_legacy(air_temp)
            return legacy_temp, {
                'predicted_water_temp': round(legacy_temp, 1),
                'model': 'legacy_fallback',
                'error': str(e)
            }

    def _score_temperature(
        self,
        water_temp: float,
        optimal_min: float,
        optimal_max: float,
        stress_threshold: float,
        critical_threshold: float,
    ) -> Tuple[float, str, str]:
        """
        Score a single temperature value against species thresholds.

        Scoring logic:
        - Optimal range (optimal_min to optimal_max): score = 1.0
        - Acceptable range (below optimal or up to stress): score = 0.5-1.0
        - Stress range (stress to critical): score = 0.1-0.5
        - Critical range (above critical or well below optimal): score = 0.0

        Args:
            water_temp: Water temperature (°C)
            optimal_min: Lower bound of optimal range (°C)
            optimal_max: Upper bound of optimal range (°C)
            stress_threshold: Temperature causing thermal stress (°C)
            critical_threshold: Critical/lethal temperature (°C)

        Returns:
            Tuple of (score, classification, explanation)
        """
        # Perfect range
        if optimal_min <= water_temp <= optimal_max:
            return (
                1.0,
                "optimal",
                f"Water temperature ({water_temp:.1f}°C) is in optimal range "
                f"({optimal_min}-{optimal_max}°C)",
            )

        # Too warm - stress zone
        elif optimal_max < water_temp <= stress_threshold:
            # Linear gradient from 1.0 to 0.5
            score = 1.0 - 0.5 * (
                (water_temp - optimal_max) / (stress_threshold - optimal_max)
            )
            return (
                score,
                "warm",
                f"Water temperature ({water_temp:.1f}°C) is warm but acceptable "
                f"(optimal max: {optimal_max}°C)",
            )

        # Too warm - critical zone
        elif stress_threshold < water_temp <= critical_threshold:
            # Linear gradient from 0.5 to 0.1
            score = 0.5 - 0.4 * (
                (water_temp - stress_threshold) / (critical_threshold - stress_threshold)
            )
            return (
                score,
                "stress",
                f"Water temperature ({water_temp:.1f}°C) is causing thermal stress "
                f"(stress threshold: {stress_threshold}°C)",
            )

        # Too warm - lethal zone
        elif water_temp > critical_threshold:
            return (
                0.0,
                "critical_high",
                f"Water temperature ({water_temp:.1f}°C) exceeds critical threshold "
                f"({critical_threshold}°C) - unsuitable",
            )

        # Too cold - below optimal
        elif water_temp < optimal_min:
            # Cold water is less critical than warm for most species
            # But very cold can be problematic
            cold_tolerance = optimal_min - 10  # Species can tolerate 10°C below optimal

            if water_temp >= cold_tolerance:
                # Linear gradient from 1.0 to 0.3
                score = 1.0 - 0.7 * (
                    (optimal_min - water_temp) / (optimal_min - cold_tolerance)
                )
                return (
                    score,
                    "cool",
                    f"Water temperature ({water_temp:.1f}°C) is cool but acceptable "
                    f"(optimal min: {optimal_min}°C)",
                )
            else:
                return (
                    0.1,
                    "critical_low",
                    f"Water temperature ({water_temp:.1f}°C) is too cold "
                    f"(optimal min: {optimal_min}°C) - marginal habitat",
                )

        # Shouldn't reach here, but default to poor
        return (0.1, "unknown", "Unable to classify temperature")

    def fetch_temperature_for_reach(
        self,
        nhdplusid: int,
        timeframe: str = "now",
    ) -> Optional[Tuple[float, Optional[float]]]:
        """
        Fetch air temperature and cloud cover data for a reach from database.

        Args:
            nhdplusid: NHD reach identifier
            timeframe: Time period ('now', 'today', 'outlook')

        Returns:
            Tuple of (air_temperature, cloud_cover) in Celsius and %, or None if no data
        """
        with self.engine.begin() as conn:
            if timeframe == "now":
                # Get most recent current temperature (forecast_hour = 0)
                result = conn.execute(
                    text("""
                        SELECT temperature_2m, cloud_cover
                        FROM observations.temperature_timeseries
                        WHERE nhdplusid = :nhdplusid
                          AND forecast_hour = 0
                          AND temperature_2m IS NOT NULL
                        ORDER BY valid_time DESC
                        LIMIT 1
                    """),
                    {"nhdplusid": nhdplusid},
                )

                row = result.fetchone()
                return (row[0], row[1]) if row else None

            elif timeframe == "today":
                # Average temperature for next 6-12 hours
                result = conn.execute(
                    text("""
                        SELECT AVG(temperature_2m) as avg_temp, AVG(cloud_cover) as avg_cloud
                        FROM observations.temperature_timeseries
                        WHERE nhdplusid = :nhdplusid
                          AND forecast_hour BETWEEN 1 AND 12
                          AND temperature_2m IS NOT NULL
                          AND valid_time >= NOW()
                    """),
                    {"nhdplusid": nhdplusid},
                )

                row = result.fetchone()
                if row and row[0] is not None:
                    return (row[0], row[1])
                return None

            elif timeframe == "outlook":
                # Average temperature for 24-72 hour forecast
                result = conn.execute(
                    text("""
                        SELECT AVG(temperature_2m) as avg_temp, AVG(cloud_cover) as avg_cloud
                        FROM observations.temperature_timeseries
                        WHERE nhdplusid = :nhdplusid
                          AND forecast_hour BETWEEN 24 AND 72
                          AND temperature_2m IS NOT NULL
                          AND valid_time >= NOW()
                    """),
                    {"nhdplusid": nhdplusid},
                )

                row = result.fetchone()
                if row and row[0] is not None:
                    return (row[0], row[1])
                return None

        return None

    def compute_tsi(
        self,
        nhdplusid: int,
        species_config: Dict,
        timeframe: str = "now",
    ) -> Dict:
        """
        Compute Thermal Suitability Index for a reach.

        Args:
            nhdplusid: NHD reach identifier
            species_config: Species configuration with temperature thresholds
            timeframe: Time period ('now', 'today', 'outlook')

        Returns:
            Dict with score, classification, explanation, and metadata
        """
        # Extract temperature thresholds from species config
        temp_config = species_config.get("temperature", {})
        optimal_min = temp_config.get("optimal_min", 10)
        optimal_max = temp_config.get("optimal_max", 16)
        stress_threshold = temp_config.get("stress_threshold", 18)
        critical_threshold = temp_config.get("critical_threshold", 20)

        # Fetch temperature data
        temp_data = self.fetch_temperature_for_reach(nhdplusid, timeframe)

        if temp_data is None:
            logger.warning(
                f"No temperature data available for reach {nhdplusid} ({timeframe})"
            )
            return {
                "score": None,
                "classification": "no_data",
                "explanation": f"No temperature data available for {timeframe} timeframe",
                "air_temperature": None,
                "water_temperature_est": None,
                "thresholds": {
                    "optimal_min": optimal_min,
                    "optimal_max": optimal_max,
                    "stress": stress_threshold,
                    "critical": critical_threshold,
                },
            }

        air_temp, cloud_cover = temp_data

        # Predict water temperature
        if self.use_enhanced_model:
            water_temp_est, metadata = self._predict_water_temp_enhanced(
                nhdplusid=nhdplusid,
                air_temp=air_temp,
                timeframe=timeframe,
                cloud_cover=cloud_cover
            )
            model_info = metadata
        else:
            water_temp_est = self._air_to_water_temp_legacy(air_temp)
            model_info = {
                'model': 'legacy_linear',
                'predicted_water_temp': round(water_temp_est, 1),
                'conversion_note': f"Water temp estimated as air temp - {AIR_TO_WATER_OFFSET_LEGACY}°C"
            }

        # Score the temperature
        score, classification, explanation = self._score_temperature(
            water_temp=water_temp_est,
            optimal_min=optimal_min,
            optimal_max=optimal_max,
            stress_threshold=stress_threshold,
            critical_threshold=critical_threshold,
        )

        return {
            "score": round(score, 3),
            "classification": classification,
            "explanation": explanation,
            "air_temperature": round(air_temp, 1),
            "water_temperature_est": round(water_temp_est, 1),
            "cloud_cover": round(cloud_cover, 0) if cloud_cover is not None else None,
            "model_info": model_info,
            "thresholds": {
                "optimal_min": optimal_min,
                "optimal_max": optimal_max,
                "stress": stress_threshold,
                "critical": critical_threshold,
            },
        }


def compute_thermal_suitability(
    engine: Engine,
    nhdplusid: int,
    species_config: Dict,
    timeframe: str = "now",
) -> Dict:
    """
    Convenience function to compute thermal suitability.

    Args:
        engine: SQLAlchemy database engine
        nhdplusid: NHD reach identifier
        species_config: Species configuration dict
        timeframe: Time period ('now', 'today', 'outlook')

    Returns:
        TSI result dict with score and metadata
    """
    calculator = ThermalSuitabilityCalculator(engine)
    return calculator.compute_tsi(nhdplusid, species_config, timeframe)
