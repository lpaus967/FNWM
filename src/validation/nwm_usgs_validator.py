"""
NWM-USGS Validation Module

Compares NWM streamflow predictions with USGS observed gage data
to assess model accuracy and generate validation metrics.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import pandas as pd
import numpy as np
from dataclasses import dataclass
from sqlalchemy import create_engine, text

logger = logging.getLogger(__name__)


@dataclass
class ValidationMetrics:
    """Validation metrics for NWM vs USGS comparison."""
    site_id: str
    site_name: str
    n_observations: int
    correlation: float
    rmse: float  # Root Mean Square Error
    mae: float  # Mean Absolute Error
    bias: float  # Mean bias (NWM - USGS)
    percent_bias: float  # Percent bias
    nash_sutcliffe: float  # Nash-Sutcliffe Efficiency

    def __str__(self):
        return f"""
Validation Metrics for {self.site_id} ({self.site_name}):
  Observations: {self.n_observations}
  Correlation (R): {self.correlation:.3f}
  RMSE: {self.rmse:.2f} cfs
  MAE: {self.mae:.2f} cfs
  Bias: {self.bias:.2f} cfs ({self.percent_bias:.1f}%)
  Nash-Sutcliffe: {self.nash_sutcliffe:.3f}
"""


class NWMUSGSValidator:
    """
    Validates NWM predictions against USGS observed data.

    Compares streamflow predictions from NWM with actual gage measurements
    from USGS to assess model performance.
    """

    # Conversion factor: CFS to CMS (cubic meters per second)
    CFS_TO_CMS = 0.0283168

    def __init__(self, database_url: str):
        """
        Initialize validator.

        Args:
            database_url: SQLAlchemy database URL
        """
        self.database_url = database_url
        self.engine = create_engine(database_url)

    def get_usgs_nhdplus_mapping(self) -> Dict[str, int]:
        """
        Get mapping between USGS site IDs and NHDPlus feature IDs.

        This queries the database to find which USGS gages are spatially
        near NHD flowlines and creates a mapping.

        Returns:
            Dictionary mapping USGS site_id to nhdplusid
        """
        with self.engine.connect() as conn:
            # Find USGS sites within 100m of NHD flowlines
            result = conn.execute(text("""
                SELECT DISTINCT
                    usgs.\"siteId\" as usgs_site_id,
                    nhd.nhdplusid,
                    usgs.name as site_name,
                    ST_Distance(usgs.geom::geography, nhd.geom::geography) as distance_m
                FROM "USGS_Flowsites" usgs
                CROSS JOIN LATERAL (
                    SELECT nhdplusid, geom
                    FROM nhd.flowlines
                    WHERE ST_DWithin(usgs.geom::geography, geom::geography, 100)
                    ORDER BY ST_Distance(usgs.geom::geography, geom::geography)
                    LIMIT 1
                ) nhd
                WHERE usgs."isEnabled" = TRUE
                ORDER BY usgs.\"siteId\";
            """))

            mapping = {}
            for row in result:
                mapping[row[0]] = {
                    'nhdplusid': row[1],
                    'site_name': row[2],
                    'distance_m': row[3]
                }

            logger.info(f"Found {len(mapping)} USGS sites mapped to NHD flowlines")
            return mapping

    def fetch_comparison_data(
        self,
        site_id: str,
        nhdplusid: int,
        start_time: datetime,
        end_time: datetime,
        nwm_product: str = 'analysis_assim'
    ) -> pd.DataFrame:
        """
        Fetch paired NWM and USGS data for comparison.

        Args:
            site_id: USGS site ID
            nhdplusid: NHDPlus feature ID
            start_time: Start of comparison period
            end_time: End of comparison period
            nwm_product: NWM product to compare (default: analysis_assim for observations)

        Returns:
            DataFrame with columns: datetime, usgs_flow_cfs, nwm_flow_cms, nwm_flow_cfs
        """
        with self.engine.connect() as conn:
            # Fetch USGS data (discharge in CFS)
            usgs_result = conn.execute(text("""
                SELECT datetime, value as flow_cfs
                FROM observations.usgs_instantaneous_values
                WHERE site_id = :site_id
                  AND parameter_cd = '00060'
                  AND datetime BETWEEN :start_time AND :end_time
                ORDER BY datetime;
            """), {
                'site_id': site_id,
                'start_time': start_time,
                'end_time': end_time
            })

            usgs_df = pd.DataFrame(usgs_result.fetchall(), columns=['datetime', 'usgs_flow_cfs'])

            if usgs_df.empty:
                logger.warning(f"No USGS data found for site {site_id}")
                return pd.DataFrame()

            # Fetch NWM data (discharge in CMS)
            nwm_result = conn.execute(text("""
                SELECT valid_time as datetime, value as flow_cms
                FROM nwm.hydro_timeseries
                WHERE feature_id = :feature_id
                  AND variable = 'streamflow'
                  AND source = :source
                  AND valid_time BETWEEN :start_time AND :end_time
                ORDER BY valid_time;
            """), {
                'feature_id': nhdplusid,
                'source': nwm_product,
                'start_time': start_time,
                'end_time': end_time
            })

            nwm_df = pd.DataFrame(nwm_result.fetchall(), columns=['datetime', 'nwm_flow_cms'])

            if nwm_df.empty:
                logger.warning(f"No NWM data found for feature {nhdplusid}")
                return pd.DataFrame()

        # Merge datasets on datetime (inner join to get paired observations)
        merged_df = pd.merge(usgs_df, nwm_df, on='datetime', how='inner')

        # Convert NWM from CMS to CFS for comparison
        merged_df['nwm_flow_cfs'] = merged_df['nwm_flow_cms'] / self.CFS_TO_CMS

        logger.info(f"Found {len(merged_df)} paired observations for site {site_id}")

        return merged_df

    def calculate_metrics(
        self,
        observed: np.ndarray,
        predicted: np.ndarray,
        site_id: str,
        site_name: str
    ) -> ValidationMetrics:
        """
        Calculate validation metrics.

        Args:
            observed: Observed values (USGS)
            predicted: Predicted values (NWM)
            site_id: USGS site ID
            site_name: Site name

        Returns:
            ValidationMetrics object
        """
        n = len(observed)

        # Correlation
        correlation = np.corrcoef(observed, predicted)[0, 1] if n > 1 else 0.0

        # RMSE (Root Mean Square Error)
        rmse = np.sqrt(np.mean((predicted - observed) ** 2))

        # MAE (Mean Absolute Error)
        mae = np.mean(np.abs(predicted - observed))

        # Bias
        bias = np.mean(predicted - observed)
        percent_bias = (bias / np.mean(observed)) * 100 if np.mean(observed) != 0 else 0.0

        # Nash-Sutcliffe Efficiency
        numerator = np.sum((observed - predicted) ** 2)
        denominator = np.sum((observed - np.mean(observed)) ** 2)
        nash_sutcliffe = 1 - (numerator / denominator) if denominator != 0 else -np.inf

        return ValidationMetrics(
            site_id=site_id,
            site_name=site_name,
            n_observations=n,
            correlation=correlation,
            rmse=rmse,
            mae=mae,
            bias=bias,
            percent_bias=percent_bias,
            nash_sutcliffe=nash_sutcliffe
        )

    def validate_site(
        self,
        site_id: str,
        nhdplusid: int,
        site_name: str,
        start_time: datetime,
        end_time: datetime,
        nwm_product: str = 'analysis_assim'
    ) -> Optional[ValidationMetrics]:
        """
        Validate NWM predictions against USGS observations for a single site.

        Args:
            site_id: USGS site ID
            nhdplusid: NHDPlus feature ID
            site_name: Site name
            start_time: Start of validation period
            end_time: End of validation period
            nwm_product: NWM product to validate

        Returns:
            ValidationMetrics or None if insufficient data
        """
        # Fetch paired data
        df = self.fetch_comparison_data(site_id, nhdplusid, start_time, end_time, nwm_product)

        if df.empty or len(df) < 5:
            logger.warning(f"Insufficient data for validation (need at least 5 points, got {len(df)})")
            return None

        # Calculate metrics
        metrics = self.calculate_metrics(
            observed=df['usgs_flow_cfs'].values,
            predicted=df['nwm_flow_cfs'].values,
            site_id=site_id,
            site_name=site_name
        )

        return metrics

    def validate_all_sites(
        self,
        start_time: datetime,
        end_time: datetime,
        nwm_product: str = 'analysis_assim'
    ) -> List[ValidationMetrics]:
        """
        Validate NWM predictions against all available USGS sites.

        Args:
            start_time: Start of validation period
            end_time: End of validation period
            nwm_product: NWM product to validate

        Returns:
            List of ValidationMetrics for all sites with sufficient data
        """
        # Get USGS-NHD mapping
        mapping = self.get_usgs_nhdplus_mapping()

        results = []

        for site_id, info in mapping.items():
            logger.info(f"Validating site {site_id} ({info['site_name']})...")

            metrics = self.validate_site(
                site_id=site_id,
                nhdplusid=info['nhdplusid'],
                site_name=info['site_name'],
                start_time=start_time,
                end_time=end_time,
                nwm_product=nwm_product
            )

            if metrics:
                results.append(metrics)

        return results

    def store_validation_results(
        self,
        metrics: ValidationMetrics,
        validation_period_start: datetime,
        validation_period_end: datetime,
        nwm_product: str
    ):
        """
        Store validation results in database.

        Args:
            metrics: Validation metrics to store
            validation_period_start: Start of validation period
            validation_period_end: End of validation period
            nwm_product: NWM product that was validated
        """
        with self.engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO validation.nwm_usgs_validation (
                    site_id, site_name, nwm_product,
                    validation_start, validation_end,
                    n_observations, correlation, rmse, mae,
                    bias, percent_bias, nash_sutcliffe,
                    validated_at
                ) VALUES (
                    :site_id, :site_name, :nwm_product,
                    :val_start, :val_end,
                    :n_obs, :corr, :rmse, :mae,
                    :bias, :pct_bias, :nse,
                    :validated_at
                )
                ON CONFLICT (site_id, nwm_product, validation_start, validation_end)
                DO UPDATE SET
                    n_observations = EXCLUDED.n_observations,
                    correlation = EXCLUDED.correlation,
                    rmse = EXCLUDED.rmse,
                    mae = EXCLUDED.mae,
                    bias = EXCLUDED.bias,
                    percent_bias = EXCLUDED.percent_bias,
                    nash_sutcliffe = EXCLUDED.nash_sutcliffe,
                    validated_at = EXCLUDED.validated_at;
            """), {
                'site_id': metrics.site_id,
                'site_name': metrics.site_name,
                'nwm_product': nwm_product,
                'val_start': validation_period_start,
                'val_end': validation_period_end,
                'n_obs': metrics.n_observations,
                'corr': metrics.correlation,
                'rmse': metrics.rmse,
                'mae': metrics.mae,
                'bias': metrics.bias,
                'pct_bias': metrics.percent_bias,
                'nse': metrics.nash_sutcliffe,
                'validated_at': datetime.utcnow()
            })
