"""
Thermal Suitability Index (TSI) Calculator

Computes thermal habitat suitability for fish species based on air temperature data
from Open-Meteo API, with conversion to estimated water temperature.

Design Principles:
- Air temperature is a proxy for water temperature (typical offset: -3°C)
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


# Air to water temperature conversion offset (°C)
# Stream water is typically 2-5°C cooler than air temperature
AIR_TO_WATER_OFFSET = 3.0


class ThermalSuitabilityCalculator:
    """Calculate thermal suitability scores for fish habitat."""

    def __init__(self, engine: Engine):
        """
        Initialize TSI calculator.

        Args:
            engine: SQLAlchemy database engine
        """
        self.engine = engine

    def _air_to_water_temp(self, air_temp: float) -> float:
        """
        Convert air temperature to estimated water temperature.

        Uses conservative offset to estimate stream water temperature.

        Args:
            air_temp: Air temperature in Celsius

        Returns:
            Estimated water temperature in Celsius
        """
        return air_temp - AIR_TO_WATER_OFFSET

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
    ) -> Optional[float]:
        """
        Fetch air temperature data for a reach from database.

        Args:
            nhdplusid: NHD reach identifier
            timeframe: Time period ('now', 'today', 'outlook')

        Returns:
            Average air temperature in Celsius, or None if no data
        """
        with self.engine.begin() as conn:
            if timeframe == "now":
                # Get most recent current temperature (forecast_hour = 0)
                result = conn.execute(
                    text("""
                        SELECT temperature_2m
                        FROM temperature_timeseries
                        WHERE nhdplusid = :nhdplusid
                          AND forecast_hour = 0
                          AND temperature_2m IS NOT NULL
                        ORDER BY valid_time DESC
                        LIMIT 1
                    """),
                    {"nhdplusid": nhdplusid},
                )

                row = result.fetchone()
                return row[0] if row else None

            elif timeframe == "today":
                # Average temperature for next 6-12 hours
                result = conn.execute(
                    text("""
                        SELECT AVG(temperature_2m) as avg_temp
                        FROM temperature_timeseries
                        WHERE nhdplusid = :nhdplusid
                          AND forecast_hour BETWEEN 1 AND 12
                          AND temperature_2m IS NOT NULL
                          AND valid_time >= NOW()
                    """),
                    {"nhdplusid": nhdplusid},
                )

                row = result.fetchone()
                return row[0] if row and row[0] is not None else None

            elif timeframe == "outlook":
                # Average temperature for 24-72 hour forecast
                result = conn.execute(
                    text("""
                        SELECT AVG(temperature_2m) as avg_temp
                        FROM temperature_timeseries
                        WHERE nhdplusid = :nhdplusid
                          AND forecast_hour BETWEEN 24 AND 72
                          AND temperature_2m IS NOT NULL
                          AND valid_time >= NOW()
                    """),
                    {"nhdplusid": nhdplusid},
                )

                row = result.fetchone()
                return row[0] if row and row[0] is not None else None

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
        air_temp = self.fetch_temperature_for_reach(nhdplusid, timeframe)

        if air_temp is None:
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

        # Convert air to water temperature
        water_temp_est = self._air_to_water_temp(air_temp)

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
            "conversion_note": f"Water temp estimated as air temp - {AIR_TO_WATER_OFFSET}°C",
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
