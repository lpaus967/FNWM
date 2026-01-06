-- Temperature Time Series Schema
-- Stores air temperature data from Open-Meteo API for stream reach centroids
-- Supports both current conditions and forecasts

CREATE TABLE IF NOT EXISTS temperature_timeseries (
    nhdplusid BIGINT NOT NULL,
    valid_time TIMESTAMP NOT NULL,
    temperature_2m DOUBLE PRECISION,  -- Air temperature at 2m (°C)
    apparent_temperature DOUBLE PRECISION,  -- "Feels like" temperature (°C)
    precipitation DOUBLE PRECISION,  -- Precipitation (mm)
    cloud_cover SMALLINT,  -- Cloud cover (%)
    source VARCHAR(50) NOT NULL DEFAULT 'open-meteo',
    forecast_hour SMALLINT,  -- NULL or 0 for current, >0 for forecast
    ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Foreign key to nhd_reach_centroids
    CONSTRAINT fk_temperature_reach
        FOREIGN KEY (nhdplusid)
        REFERENCES nhd_reach_centroids(nhdplusid)
        ON DELETE CASCADE,

    -- Prevent duplicate entries for same reach/time/source/forecast_hour
    CONSTRAINT unique_temperature_reading
        UNIQUE (nhdplusid, valid_time, source, forecast_hour)
);

-- Create indexes for efficient queries
CREATE INDEX IF NOT EXISTS idx_temp_reach_time
    ON temperature_timeseries(nhdplusid, valid_time);

CREATE INDEX IF NOT EXISTS idx_temp_valid_time
    ON temperature_timeseries(valid_time);

CREATE INDEX IF NOT EXISTS idx_temp_source
    ON temperature_timeseries(source);

-- Create hypertable for time-series optimization (if TimescaleDB is enabled)
-- Uncomment if using TimescaleDB:
-- SELECT create_hypertable('temperature_timeseries', 'valid_time', if_not_exists => TRUE);

-- Verification query
SELECT
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables
WHERE tablename = 'temperature_timeseries';

COMMENT ON TABLE temperature_timeseries IS 'Air temperature time series from Open-Meteo API for stream reach centroids';
COMMENT ON COLUMN temperature_timeseries.temperature_2m IS 'Air temperature at 2 meters above ground (°C)';
COMMENT ON COLUMN temperature_timeseries.apparent_temperature IS 'Apparent/"feels like" temperature (°C)';
COMMENT ON COLUMN temperature_timeseries.forecast_hour IS 'Hours ahead of reference time (0 or NULL = current conditions)';
