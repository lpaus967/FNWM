-- Create materialized view combining hydrology metrics with flowline geometry
-- This enables fast map rendering and GeoJSON export
-- Based on EPIC 8, Ticket 8.3 from IMPLEMENTATION_GUIDE.md

-- Drop existing view if present
DROP MATERIALIZED VIEW IF EXISTS map_current_conditions CASCADE;

-- Create materialized view
CREATE MATERIALIZED VIEW map_current_conditions AS
SELECT
    f.nhdplusid as feature_id,
    f.geom,
    f.gnis_name,
    f.reachcode,
    f.totdasqkm as drainage_area_sqkm,
    f.slope,
    f.streamorde as stream_order,
    f.gradient_class,
    f.size_class,

    -- Latest hydrology data (most recent valid_time per reach)
    latest.valid_time,
    latest.streamflow,
    latest.velocity,
    latest.qBtmVertRunoff,
    latest.qBucket,
    latest.qSfcLatRunoff,
    latest.nudge,

    -- Derived metrics (computed on the fly)
    CASE
        WHEN (latest.qBtmVertRunoff + latest.qBucket + latest.qSfcLatRunoff) > 0
        THEN (latest.qBtmVertRunoff + latest.qBucket) / (latest.qBtmVertRunoff + latest.qBucket + latest.qSfcLatRunoff)
        ELSE NULL
    END as bdi,

    CASE
        WHEN (latest.qBtmVertRunoff + latest.qBucket + latest.qSfcLatRunoff) > 0 THEN
            CASE
                WHEN (latest.qBtmVertRunoff + latest.qBucket) / (latest.qBtmVertRunoff + latest.qBucket + latest.qSfcLatRunoff) >= 0.7
                    THEN 'groundwater_fed'
                WHEN (latest.qBtmVertRunoff + latest.qBucket) / (latest.qBtmVertRunoff + latest.qBucket + latest.qSfcLatRunoff) >= 0.3
                    THEN 'mixed'
                ELSE 'storm_dominated'
            END
        ELSE NULL
    END as bdi_category,

    -- Flow percentile (computed from nhd_flow_statistics)
    -- Uses same logic as src/metrics/flow_percentile.py
    fs.monthly_mean,
    CASE
        WHEN latest.streamflow IS NOT NULL AND fs.monthly_mean IS NOT NULL AND fs.monthly_mean > 0
        THEN 50.0 + (50.0 * tanh((latest.streamflow / fs.monthly_mean - 1.0) * 2.0))
        ELSE NULL
    END as flow_percentile,

    CASE
        WHEN latest.streamflow IS NOT NULL AND fs.monthly_mean IS NOT NULL AND fs.monthly_mean > 0 THEN
            CASE
                WHEN 50.0 + (50.0 * tanh((latest.streamflow / fs.monthly_mean - 1.0) * 2.0)) < 10 THEN 'extreme_low'
                WHEN 50.0 + (50.0 * tanh((latest.streamflow / fs.monthly_mean - 1.0) * 2.0)) < 25 THEN 'low'
                WHEN 50.0 + (50.0 * tanh((latest.streamflow / fs.monthly_mean - 1.0) * 2.0)) < 40 THEN 'below_normal'
                WHEN 50.0 + (50.0 * tanh((latest.streamflow / fs.monthly_mean - 1.0) * 2.0)) < 60 THEN 'normal'
                WHEN 50.0 + (50.0 * tanh((latest.streamflow / fs.monthly_mean - 1.0) * 2.0)) < 75 THEN 'above_normal'
                WHEN 50.0 + (50.0 * tanh((latest.streamflow / fs.monthly_mean - 1.0) * 2.0)) < 90 THEN 'high'
                ELSE 'extreme_high'
            END
        ELSE NULL
    END as flow_percentile_category,

    -- Temperature data (from Open-Meteo API)
    -- Celsius values
    temp.air_temp_c,
    temp.apparent_temp_c,
    -- Estimated water temperature (air temp - 3°C offset, per thermal_suitability.py)
    CASE
        WHEN temp.air_temp_c IS NOT NULL
        THEN temp.air_temp_c - 3.0
        ELSE NULL
    END as water_temp_estimate_c,

    -- Fahrenheit conversions
    CASE
        WHEN temp.air_temp_c IS NOT NULL
        THEN (temp.air_temp_c * 9.0 / 5.0) + 32.0
        ELSE NULL
    END as air_temp_f,
    CASE
        WHEN temp.apparent_temp_c IS NOT NULL
        THEN (temp.apparent_temp_c * 9.0 / 5.0) + 32.0
        ELSE NULL
    END as apparent_temp_f,
    CASE
        WHEN temp.air_temp_c IS NOT NULL
        THEN ((temp.air_temp_c - 3.0) * 9.0 / 5.0) + 32.0
        ELSE NULL
    END as water_temp_estimate_f,

    temp.precipitation_mm,
    temp.cloud_cover_pct,
    temp.temp_valid_time,

    -- Metadata
    latest.source,
    latest.forecast_hour,

    -- Confidence (simple classification based on source)
    CASE
        WHEN latest.source = 'analysis_assim' THEN 'high'
        WHEN latest.source = 'short_range' AND latest.forecast_hour <= 3 THEN 'high'
        WHEN latest.source = 'short_range' AND latest.forecast_hour <= 12 THEN 'medium'
        ELSE 'low'
    END as confidence

FROM nhd_flowlines f

-- Join to get latest hydrology data for each reach
LEFT JOIN LATERAL (
    SELECT
        ht.valid_time,
        ht.source,
        ht.forecast_hour,
        MAX(CASE WHEN ht.variable = 'streamflow' THEN ht.value END) as streamflow,
        MAX(CASE WHEN ht.variable = 'velocity' THEN ht.value END) as velocity,
        MAX(CASE WHEN ht.variable = 'qBtmVertRunoff' THEN ht.value END) as qBtmVertRunoff,
        MAX(CASE WHEN ht.variable = 'qBucket' THEN ht.value END) as qBucket,
        MAX(CASE WHEN ht.variable = 'qSfcLatRunoff' THEN ht.value END) as qSfcLatRunoff,
        MAX(CASE WHEN ht.variable = 'nudge' THEN ht.value END) as nudge
    FROM hydro_timeseries ht
    WHERE ht.feature_id = f.nhdplusid
        AND ht.source = 'analysis_assim'  -- Only "now" data (most recent analysis)
    GROUP BY ht.valid_time, ht.source, ht.forecast_hour
    ORDER BY ht.valid_time DESC
    LIMIT 1
) latest ON true

-- Join to nhd_flow_statistics for monthly mean (determine month from valid_time)
LEFT JOIN LATERAL (
    SELECT
        CASE EXTRACT(MONTH FROM latest.valid_time)
            WHEN 1 THEN nfs.qama
            WHEN 2 THEN nfs.qbma
            WHEN 3 THEN nfs.qcma
            WHEN 4 THEN nfs.qdma
            WHEN 5 THEN nfs.qema
            WHEN 6 THEN nfs.qfma
            ELSE NULL  -- Months 7-12 not available in NHD data
        END as monthly_mean
    FROM nhd_flow_statistics nfs
    WHERE nfs.nhdplusid = f.nhdplusid
) fs ON true

-- Join to temperature data (latest reading)
LEFT JOIN LATERAL (
    SELECT
        tt.temperature_2m as air_temp_c,
        tt.apparent_temperature as apparent_temp_c,
        tt.precipitation as precipitation_mm,
        tt.cloud_cover as cloud_cover_pct,
        tt.valid_time as temp_valid_time
    FROM temperature_timeseries tt
    WHERE tt.nhdplusid = f.nhdplusid
    ORDER BY tt.valid_time DESC
    LIMIT 1
) temp ON true

WHERE latest.valid_time IS NOT NULL;  -- Only include reaches with hydrology data

-- Create indexes for efficient querying
CREATE INDEX idx_map_current_geom ON map_current_conditions USING GIST (geom);
CREATE INDEX idx_map_current_feature ON map_current_conditions (feature_id);
CREATE INDEX idx_map_current_bdi ON map_current_conditions (bdi_category);
CREATE INDEX idx_map_current_drainage ON map_current_conditions (drainage_area_sqkm);
CREATE INDEX idx_map_current_flow ON map_current_conditions (streamflow);

-- Refresh function for easy updates
CREATE OR REPLACE FUNCTION refresh_map_current_conditions()
RETURNS void AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY map_current_conditions;
END;
$$ LANGUAGE plpgsql;

COMMENT ON MATERIALIZED VIEW map_current_conditions IS
'Map-ready view combining NHD flowline geometry with latest hydrology metrics.
Enables fast GeoJSON export and map rendering.
Refresh after new data ingestion using: SELECT refresh_map_current_conditions();';
