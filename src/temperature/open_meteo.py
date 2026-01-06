"""
Open-Meteo API Client

Fetches temperature and weather data from Open-Meteo API for stream reach centroids.

API Documentation: https://open-meteo.com/en/docs
"""

import logging
from datetime import datetime, timezone
from typing import List, Optional
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .schemas import (
    TemperatureReading,
    OpenMeteoResponse,
    TemperatureQuery,
    TemperatureIngestionResult,
)

logger = logging.getLogger(__name__)


class OpenMeteoClient:
    """Client for fetching weather data from Open-Meteo API."""

    FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
    HISTORICAL_URL = "https://archive-api.open-meteo.com/v1/archive"
    TIMEOUT = 30  # seconds

    def __init__(self, timeout: int = TIMEOUT):
        """
        Initialize Open-Meteo API client.

        Args:
            timeout: Request timeout in seconds
        """
        self.timeout = timeout
        self.session = self._create_session()

    def _create_session(self) -> requests.Session:
        """Create requests session with retry logic."""
        session = requests.Session()

        # Configure retry strategy
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
        )

        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        session.mount("http://", adapter)

        return session

    def fetch_temperature(
        self,
        latitude: float,
        longitude: float,
        forecast_days: int = 7,
        include_current: bool = True,
    ) -> Optional[OpenMeteoResponse]:
        """
        Fetch temperature data from Open-Meteo API.

        Args:
            latitude: Location latitude (-90 to 90)
            longitude: Location longitude (-180 to 180)
            forecast_days: Number of forecast days (0-16)
            include_current: Include current conditions

        Returns:
            OpenMeteoResponse or None if request fails
        """
        # Build query parameters
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "timezone": "UTC",
            "forecast_days": min(forecast_days, 16),  # API max is 16 days
        }

        # Add current weather parameters
        if include_current:
            params["current"] = [
                "temperature_2m",
                "apparent_temperature",
                "precipitation",
                "cloud_cover",
            ]

        # Add hourly forecast parameters
        if forecast_days > 0:
            params["hourly"] = [
                "temperature_2m",
                "apparent_temperature",
                "precipitation",
                "cloud_cover",
            ]

        try:
            logger.debug(
                f"Fetching temperature for ({latitude:.4f}, {longitude:.4f}), "
                f"forecast_days={forecast_days}"
            )

            response = self.session.get(
                self.FORECAST_URL,
                params=params,
                timeout=self.timeout,
            )

            response.raise_for_status()
            data = response.json()

            return OpenMeteoResponse(**data)

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch temperature data: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching temperature: {e}")
            return None

    def fetch_for_reach(
        self,
        query: TemperatureQuery,
    ) -> List[TemperatureReading]:
        """
        Fetch temperature data for a specific stream reach.

        Args:
            query: Temperature query with reach ID and coordinates

        Returns:
            List of TemperatureReading objects
        """
        # Fetch data from API
        response = self.fetch_temperature(
            latitude=query.latitude,
            longitude=query.longitude,
            forecast_days=query.forecast_days,
            include_current=query.include_current,
        )

        if not response:
            return []

        readings = []

        # Process current conditions
        if query.include_current and response.current:
            current_time = datetime.fromisoformat(
                response.current.get("time", "")
            ).replace(tzinfo=timezone.utc)

            readings.append(
                TemperatureReading(
                    nhdplusid=query.nhdplusid,
                    valid_time=current_time,
                    temperature_2m=response.current.get("temperature_2m"),
                    apparent_temperature=response.current.get("apparent_temperature"),
                    precipitation=response.current.get("precipitation"),
                    cloud_cover=response.current.get("cloud_cover"),
                    source="open-meteo",
                    forecast_hour=0,
                )
            )

        # Process hourly forecast
        if query.forecast_days > 0 and response.hourly:
            times = response.hourly.get("time", [])
            temps = response.hourly.get("temperature_2m", [])
            apparent_temps = response.hourly.get("apparent_temperature", [])
            precip = response.hourly.get("precipitation", [])
            clouds = response.hourly.get("cloud_cover", [])

            for i, time_str in enumerate(times):
                valid_time = datetime.fromisoformat(time_str).replace(
                    tzinfo=timezone.utc
                )

                # Calculate forecast hour from current time
                if query.include_current and response.current:
                    forecast_hour = int(
                        (valid_time - current_time).total_seconds() / 3600
                    )
                else:
                    forecast_hour = i + 1

                readings.append(
                    TemperatureReading(
                        nhdplusid=query.nhdplusid,
                        valid_time=valid_time,
                        temperature_2m=temps[i] if i < len(temps) else None,
                        apparent_temperature=(
                            apparent_temps[i] if i < len(apparent_temps) else None
                        ),
                        precipitation=precip[i] if i < len(precip) else None,
                        cloud_cover=clouds[i] if i < len(clouds) else None,
                        source="open-meteo",
                        forecast_hour=forecast_hour,
                    )
                )

        logger.info(
            f"Fetched {len(readings)} temperature readings for reach {query.nhdplusid}"
        )

        return readings

    def fetch_historical(
        self,
        latitude: float,
        longitude: float,
        target_time: datetime,
    ) -> Optional[TemperatureReading]:
        """
        Fetch historical temperature data for a specific timestamp.

        Args:
            latitude: Location latitude (-90 to 90)
            longitude: Location longitude (-180 to 180)
            target_time: Specific datetime to fetch temperature for (UTC)

        Returns:
            TemperatureReading or None if request fails
        """
        # Extract date from target_time
        date_str = target_time.strftime("%Y-%m-%d")

        # Build query parameters for historical API
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "start_date": date_str,
            "end_date": date_str,
            "hourly": [
                "temperature_2m",
                "apparent_temperature",
                "precipitation",
                "cloud_cover",
            ],
            "timezone": "UTC",
        }

        try:
            logger.debug(
                f"Fetching historical temperature for ({latitude:.4f}, {longitude:.4f}) "
                f"at {target_time}"
            )

            response = self.session.get(
                self.HISTORICAL_URL,
                params=params,
                timeout=self.timeout,
            )

            response.raise_for_status()
            data = response.json()

            # Parse hourly data to find the exact hour we need
            if "hourly" not in data or not data["hourly"].get("time"):
                logger.warning(f"No hourly data returned for {target_time}")
                return None

            times = data["hourly"]["time"]
            temps = data["hourly"].get("temperature_2m", [])
            apparent_temps = data["hourly"].get("apparent_temperature", [])
            precip = data["hourly"].get("precipitation", [])
            clouds = data["hourly"].get("cloud_cover", [])

            # Find the matching hour
            target_hour_str = target_time.strftime("%Y-%m-%dT%H:00")

            for i, time_str in enumerate(times):
                if time_str == target_hour_str:
                    valid_time = datetime.fromisoformat(time_str).replace(
                        tzinfo=timezone.utc
                    )

                    return TemperatureReading(
                        nhdplusid=0,  # Will be set by caller
                        valid_time=valid_time,
                        temperature_2m=temps[i] if i < len(temps) else None,
                        apparent_temperature=(
                            apparent_temps[i] if i < len(apparent_temps) else None
                        ),
                        precipitation=precip[i] if i < len(precip) else None,
                        cloud_cover=clouds[i] if i < len(clouds) else None,
                        source="open-meteo",
                        forecast_hour=0,  # Historical data, not a forecast
                    )

            logger.warning(
                f"Target hour {target_hour_str} not found in response times: {times}"
            )
            return None

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch historical temperature data: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching historical temperature: {e}")
            return None

    def close(self):
        """Close the session."""
        self.session.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
