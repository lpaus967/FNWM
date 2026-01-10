"""
USGS Water Services API Client

Client for fetching real-time streamflow and gage data from USGS monitoring stations.

API Documentation: https://waterservices.usgs.gov/docs/instantaneous-values/
"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Literal
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .schemas import (
    USGSInstantaneousValue,
    USGSSiteData,
    USGSTimeSeries,
    USGSFetchResult,
)

logger = logging.getLogger(__name__)


# USGS Parameter Codes (common ones for streamflow monitoring)
class ParameterCodes:
    """Common USGS parameter codes."""
    DISCHARGE = "00060"  # Discharge, cubic feet per second
    GAGE_HEIGHT = "00065"  # Gage height, feet
    WATER_TEMP = "00010"  # Temperature, water, degrees Celsius
    SPECIFIC_CONDUCTANCE = "00095"  # Specific conductance, uS/cm at 25C
    DISSOLVED_OXYGEN = "00300"  # Dissolved oxygen, mg/L
    PH = "00400"  # pH, standard units
    TURBIDITY = "63680"  # Turbidity, FNU


class USGSClient:
    """
    Client for fetching data from USGS Water Services Instantaneous Values API.

    This client provides access to real-time (15-minute interval) data from
    USGS monitoring stations across the United States.
    """

    BASE_URL = "https://waterservices.usgs.gov/nwis/iv/"
    TIMEOUT = 30  # seconds
    MAX_SITES_PER_REQUEST = 100  # USGS API limit

    def __init__(
        self,
        timeout: int = TIMEOUT,
        max_retries: int = 3
    ):
        """
        Initialize USGS Water Services client.

        Args:
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts
        """
        self.timeout = timeout
        self.session = self._create_session(max_retries)
        logger.info("USGS Water Services client initialized")

    def _create_session(self, max_retries: int) -> requests.Session:
        """Create requests session with retry logic."""
        session = requests.Session()

        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
        )

        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        session.mount("http://", adapter)

        return session

    def fetch_current_conditions(
        self,
        site_ids: List[str],
        parameter_codes: Optional[List[str]] = None,
        period: Optional[str] = None
    ) -> List[USGSFetchResult]:
        """
        Fetch current conditions for multiple USGS sites.

        Args:
            site_ids: List of USGS site IDs (e.g., ['13311000', '13310800'])
            parameter_codes: List of parameter codes to fetch (defaults to discharge and gage height)
            period: ISO-8601 duration (e.g., 'P1D' for 1 day, 'PT6H' for 6 hours)
                   If None, returns only the most recent value

        Returns:
            List of USGSFetchResult objects, one per site

        Example:
            >>> client = USGSClient()
            >>> results = client.fetch_current_conditions(['13311000', '13310800'])
            >>> for result in results:
            ...     if result.success:
            ...         print(f"Site {result.site_id}: {len(result.data)} readings")
        """
        if not site_ids:
            logger.warning("No site IDs provided")
            return []

        # Default to discharge and gage height
        if parameter_codes is None:
            parameter_codes = [ParameterCodes.DISCHARGE, ParameterCodes.GAGE_HEIGHT]

        # Process sites in batches (USGS allows up to 100 per request)
        results = []
        for i in range(0, len(site_ids), self.MAX_SITES_PER_REQUEST):
            batch = site_ids[i:i + self.MAX_SITES_PER_REQUEST]
            batch_results = self._fetch_batch(batch, parameter_codes, period)
            results.extend(batch_results)

        return results

    def _fetch_batch(
        self,
        site_ids: List[str],
        parameter_codes: List[str],
        period: Optional[str] = None
    ) -> List[USGSFetchResult]:
        """Fetch data for a batch of sites."""
        params = {
            'sites': ','.join(site_ids),
            'parameterCd': ','.join(parameter_codes),
            'format': 'json',
            'siteStatus': 'all'
        }

        if period:
            params['period'] = period

        try:
            logger.info(f"Fetching USGS data for {len(site_ids)} sites")
            response = self.session.get(
                self.BASE_URL,
                params=params,
                timeout=self.timeout
            )
            response.raise_for_status()

            data = response.json()
            return self._parse_response(data, site_ids)

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                logger.warning(f"No data found for sites: {site_ids}")
                return [
                    USGSFetchResult(
                        site_id=site_id,
                        success=False,
                        error="No data available"
                    )
                    for site_id in site_ids
                ]
            else:
                logger.error(f"HTTP error fetching USGS data: {e}")
                return [
                    USGSFetchResult(
                        site_id=site_id,
                        success=False,
                        error=f"HTTP {e.response.status_code}: {str(e)}"
                    )
                    for site_id in site_ids
                ]

        except Exception as e:
            logger.error(f"Error fetching USGS data: {e}")
            return [
                USGSFetchResult(
                    site_id=site_id,
                    success=False,
                    error=str(e)
                )
                for site_id in site_ids
            ]

    def _parse_response(
        self,
        data: Dict[str, Any],
        requested_site_ids: List[str]
    ) -> List[USGSFetchResult]:
        """Parse USGS JSON response into structured results."""
        results = []

        # Get time series data from response
        time_series_list = data.get('value', {}).get('timeSeries', [])

        if not time_series_list:
            logger.warning("No time series data in response")
            return [
                USGSFetchResult(
                    site_id=site_id,
                    success=False,
                    error="No time series data returned"
                )
                for site_id in requested_site_ids
            ]

        # Group time series by site
        site_data_map: Dict[str, List[Dict[str, Any]]] = {}
        for ts in time_series_list:
            site_code = ts.get('sourceInfo', {}).get('siteCode', [{}])[0].get('value', '')
            if site_code:
                if site_code not in site_data_map:
                    site_data_map[site_code] = []
                site_data_map[site_code].append(ts)

        # Process each site
        for site_id in requested_site_ids:
            if site_id not in site_data_map:
                results.append(USGSFetchResult(
                    site_id=site_id,
                    success=False,
                    error="Site not found in response"
                ))
                continue

            try:
                readings = self._parse_site_data(site_id, site_data_map[site_id])
                results.append(USGSFetchResult(
                    site_id=site_id,
                    success=True,
                    data=readings
                ))
            except Exception as e:
                logger.error(f"Error parsing site {site_id}: {e}")
                results.append(USGSFetchResult(
                    site_id=site_id,
                    success=False,
                    error=f"Parse error: {str(e)}"
                ))

        return results

    def _parse_site_data(
        self,
        site_id: str,
        time_series_list: List[Dict[str, Any]]
    ) -> List[USGSInstantaneousValue]:
        """Parse time series data for a single site."""
        readings = []

        for ts in time_series_list:
            try:
                # Extract variable info
                variable = ts.get('variable', {})
                var_code = variable.get('variableCode', [{}])[0].get('value', '')
                var_name = variable.get('variableName', '')
                unit_info = variable.get('unit', {})
                unit_code = unit_info.get('unitCode', '')

                # Get values
                values = ts.get('values', [{}])[0].get('value', [])

                for value_entry in values:
                    try:
                        # Parse value
                        value_str = value_entry.get('value', '')
                        if value_str == '' or value_str is None:
                            continue

                        value_float = float(value_str)

                        # Parse datetime
                        dt_str = value_entry.get('dateTime', '')
                        dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))

                        # Get qualifiers (e.g., 'P' for provisional)
                        qualifiers = value_entry.get('qualifiers', [])
                        is_provisional = 'P' in qualifiers

                        reading = USGSInstantaneousValue(
                            site_id=site_id,
                            parameter_cd=var_code,
                            parameter_name=var_name,
                            value=value_float,
                            unit=unit_code,
                            datetime=dt,
                            qualifiers=qualifiers,
                            is_provisional=is_provisional
                        )
                        readings.append(reading)

                    except (ValueError, KeyError) as e:
                        logger.debug(f"Skipping invalid value entry: {e}")
                        continue

            except Exception as e:
                logger.warning(f"Error parsing time series: {e}")
                continue

        return readings

    def fetch_site_info(self, site_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Fetch site information (location, name, etc.) for given site IDs.

        Args:
            site_ids: List of USGS site IDs

        Returns:
            Dictionary mapping site IDs to site information
        """
        params = {
            'sites': ','.join(site_ids),
            'format': 'json',
            'siteOutput': 'expanded'
        }

        try:
            response = self.session.get(
                "https://waterservices.usgs.gov/nwis/site/",
                params=params,
                timeout=self.timeout
            )
            response.raise_for_status()

            data = response.json()
            site_info_map = {}

            for site in data.get('value', {}).get('timeSeries', []):
                source_info = site.get('sourceInfo', {})
                site_code = source_info.get('siteCode', [{}])[0].get('value', '')
                if site_code:
                    site_info_map[site_code] = {
                        'site_name': source_info.get('siteName', ''),
                        'latitude': source_info.get('geoLocation', {}).get('geogLocation', {}).get('latitude'),
                        'longitude': source_info.get('geoLocation', {}).get('geogLocation', {}).get('longitude'),
                        'site_type': source_info.get('siteType', [{}])[0].get('value', ''),
                    }

            return site_info_map

        except Exception as e:
            logger.error(f"Error fetching site info: {e}")
            return {}
