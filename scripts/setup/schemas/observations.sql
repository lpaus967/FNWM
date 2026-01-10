-- =====================================================================
-- Observations Schema: Ground Truth Data
-- =====================================================================
-- Contains USGS gage observations and user trip reports
-- =====================================================================

-- Enable PostGIS (needed for USGS gage locations)
CREATE EXTENSION IF NOT EXISTS postgis;

-- USGS Flowsites table
CREATE TABLE IF NOT EXISTS observations.usgs_flowsites (
    id BIGINT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    "siteId" VARCHAR(50) NOT NULL UNIQUE,
    "agencyCode" VARCHAR(10),
    network VARCHAR(50),
    "stateCd" SMALLINT,
    state VARCHAR(50),
    "siteTypeCd" VARCHAR(10),
    "noaaId" VARCHAR(50),
    "managingOr" VARCHAR(255),
    uuid UUID,
    "webcamUrl" TEXT,
    "isEnabled" BOOLEAN DEFAULT TRUE,
    geom GEOMETRY(POINT, 4326) NOT NULL,
    "createdOn" TIMESTAMPTZ DEFAULT NOW(),
    "createdBy" INTEGER DEFAULT 0,
    "updatedOn" TIMESTAMPTZ DEFAULT NOW(),
    "updatedBy" INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_usgs_flowsites_geom
    ON observations.usgs_flowsites USING GIST (geom);

CREATE INDEX IF NOT EXISTS idx_usgs_flowsites_siteid
    ON observations.usgs_flowsites ("siteId");

CREATE INDEX IF NOT EXISTS idx_usgs_flowsites_state
    ON observations.usgs_flowsites (state);

CREATE INDEX IF NOT EXISTS idx_usgs_flowsites_enabled
    ON observations.usgs_flowsites ("isEnabled") WHERE "isEnabled" = TRUE;

-- USGS Instantaneous Values table
CREATE TABLE IF NOT EXISTS observations.usgs_instantaneous_values (
    site_id VARCHAR(50) NOT NULL,
    parameter_cd VARCHAR(10) NOT NULL,
    datetime TIMESTAMPTZ NOT NULL,
    parameter_name VARCHAR(255) NOT NULL,
    value DOUBLE PRECISION NOT NULL,
    unit VARCHAR(50) NOT NULL,
    qualifiers TEXT[],
    is_provisional BOOLEAN DEFAULT TRUE,
    fetched_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (site_id, parameter_cd, datetime),
    CONSTRAINT fk_usgs_site
        FOREIGN KEY (site_id)
        REFERENCES observations.usgs_flowsites("siteId")
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_usgs_iv_datetime
    ON observations.usgs_instantaneous_values (datetime DESC);

CREATE INDEX IF NOT EXISTS idx_usgs_iv_site_time
    ON observations.usgs_instantaneous_values (site_id, datetime DESC);

CREATE INDEX IF NOT EXISTS idx_usgs_iv_parameter
    ON observations.usgs_instantaneous_values (parameter_cd);

-- Materialized view for latest readings
CREATE MATERIALIZED VIEW IF NOT EXISTS observations.usgs_latest_readings AS
SELECT DISTINCT ON (site_id, parameter_cd)
    site_id,
    parameter_cd,
    parameter_name,
    value,
    unit,
    datetime as measured_at,
    is_provisional,
    fetched_at
FROM observations.usgs_instantaneous_values
ORDER BY site_id, parameter_cd, datetime DESC;

CREATE UNIQUE INDEX IF NOT EXISTS idx_usgs_latest_site_param
    ON observations.usgs_latest_readings (site_id, parameter_cd);

-- User Observations table
CREATE TABLE IF NOT EXISTS observations.user_observations (
    id SERIAL PRIMARY KEY,
    feature_id BIGINT NOT NULL,
    observation_time TIMESTAMPTZ NOT NULL,
    observation_type VARCHAR(50),
    species VARCHAR(100),
    hatch_name VARCHAR(100),
    success_rating INTEGER CHECK (success_rating BETWEEN 1 AND 5),
    notes TEXT,
    user_id VARCHAR(255),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_obs_feature_time
    ON observations.user_observations (feature_id, observation_time DESC);

CREATE INDEX IF NOT EXISTS idx_obs_type
    ON observations.user_observations (observation_type);

-- Temperature timeseries table
CREATE TABLE IF NOT EXISTS observations.temperature_timeseries (
    nhdplusid BIGINT NOT NULL,
    valid_time TIMESTAMP NOT NULL,
    temperature_2m DOUBLE PRECISION,
    apparent_temperature DOUBLE PRECISION,
    precipitation DOUBLE PRECISION,
    cloud_cover SMALLINT,
    source VARCHAR(50) NOT NULL DEFAULT 'open-meteo',
    forecast_hour SMALLINT,
    ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_temperature_reading
        UNIQUE (nhdplusid, valid_time, source, forecast_hour)
);

-- Note: Foreign key to nhd.reach_centroids will be added after nhd schema is populated

CREATE INDEX IF NOT EXISTS idx_temp_reach_time
    ON observations.temperature_timeseries(nhdplusid, valid_time);

CREATE INDEX IF NOT EXISTS idx_temp_valid_time
    ON observations.temperature_timeseries(valid_time);

CREATE INDEX IF NOT EXISTS idx_temp_source
    ON observations.temperature_timeseries(source);

-- Comments
COMMENT ON SCHEMA observations IS 'Ground truth observations from USGS gages, weather services, and user trip reports';
COMMENT ON TABLE observations.usgs_flowsites IS 'USGS gage site locations and metadata';
COMMENT ON TABLE observations.usgs_instantaneous_values IS 'Real-time USGS gage measurements (15-minute intervals)';
COMMENT ON TABLE observations.user_observations IS 'User-submitted trip reports and field observations';
COMMENT ON TABLE observations.temperature_timeseries IS 'Air temperature forecasts from Open-Meteo weather API';

RAISE NOTICE 'Observations schema initialized';
