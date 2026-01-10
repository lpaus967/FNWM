-- =====================================================================
-- USGS Instantaneous Values Data Table
-- =====================================================================
-- This schema stores real-time streamflow and gage data from USGS
-- monitoring stations, fetched via the USGS Water Services API.
--
-- Data is typically collected every 15 minutes and transmitted hourly.
-- =====================================================================

-- =====================================================================
-- TABLE: usgs_instantaneous_values
-- Real-time gage data from USGS monitoring stations
-- =====================================================================
CREATE TABLE IF NOT EXISTS usgs_instantaneous_values (
    -- Primary Key (composite)
    site_id VARCHAR(50) NOT NULL,
    parameter_cd VARCHAR(10) NOT NULL,
    datetime TIMESTAMPTZ NOT NULL,

    -- Measurement Data
    parameter_name VARCHAR(255) NOT NULL,
    value DOUBLE PRECISION NOT NULL,
    unit VARCHAR(50) NOT NULL,

    -- Quality Flags
    qualifiers TEXT[],
    is_provisional BOOLEAN DEFAULT TRUE,

    -- Metadata
    fetched_at TIMESTAMPTZ DEFAULT NOW(),

    -- Primary key constraint
    PRIMARY KEY (site_id, parameter_cd, datetime),

    -- Foreign key to USGS_Flowsites
    CONSTRAINT fk_usgs_site
        FOREIGN KEY (site_id)
        REFERENCES "USGS_Flowsites"("siteId")
        ON DELETE CASCADE
);

-- =====================================================================
-- INDEXES
-- =====================================================================

-- Index for time-based queries (most recent values)
CREATE INDEX IF NOT EXISTS idx_usgs_iv_datetime
    ON usgs_instantaneous_values (datetime DESC);

-- Index for site + time queries
CREATE INDEX IF NOT EXISTS idx_usgs_iv_site_time
    ON usgs_instantaneous_values (site_id, datetime DESC);

-- Index for parameter filtering
CREATE INDEX IF NOT EXISTS idx_usgs_iv_parameter
    ON usgs_instantaneous_values (parameter_cd);

-- Index for discharge queries specifically
CREATE INDEX IF NOT EXISTS idx_usgs_iv_discharge
    ON usgs_instantaneous_values (parameter_cd, datetime DESC)
    WHERE parameter_cd = '00060';

-- Index for provisional data filtering
CREATE INDEX IF NOT EXISTS idx_usgs_iv_provisional
    ON usgs_instantaneous_values (is_provisional)
    WHERE is_provisional = TRUE;

-- Index for fetched_at (useful for data pipeline monitoring)
CREATE INDEX IF NOT EXISTS idx_usgs_iv_fetched
    ON usgs_instantaneous_values (fetched_at DESC);

-- =====================================================================
-- COMMENTS
-- =====================================================================
COMMENT ON TABLE usgs_instantaneous_values IS 'Real-time gage measurements from USGS monitoring stations (15-minute intervals).';
COMMENT ON COLUMN usgs_instantaneous_values.site_id IS 'USGS site identifier (references USGS_Flowsites.siteId)';
COMMENT ON COLUMN usgs_instantaneous_values.parameter_cd IS 'USGS parameter code (e.g., 00060=discharge, 00065=gage height)';
COMMENT ON COLUMN usgs_instantaneous_values.datetime IS 'Measurement timestamp (UTC)';
COMMENT ON COLUMN usgs_instantaneous_values.value IS 'Measured value';
COMMENT ON COLUMN usgs_instantaneous_values.unit IS 'Unit of measurement (e.g., ft3/s, ft, degC)';
COMMENT ON COLUMN usgs_instantaneous_values.is_provisional IS 'TRUE if data is provisional (not yet reviewed/approved by USGS)';
COMMENT ON COLUMN usgs_instantaneous_values.fetched_at IS 'Timestamp when data was fetched from USGS API';

-- =====================================================================
-- MATERIALIZED VIEW: Latest USGS Readings
-- For quick access to most recent values at each site
-- =====================================================================
CREATE MATERIALIZED VIEW IF NOT EXISTS usgs_latest_readings AS
SELECT DISTINCT ON (site_id, parameter_cd)
    site_id,
    parameter_cd,
    parameter_name,
    value,
    unit,
    datetime as measured_at,
    is_provisional,
    fetched_at
FROM usgs_instantaneous_values
ORDER BY site_id, parameter_cd, datetime DESC;

-- Index on materialized view
CREATE UNIQUE INDEX IF NOT EXISTS idx_usgs_latest_site_param
    ON usgs_latest_readings (site_id, parameter_cd);

COMMENT ON MATERIALIZED VIEW usgs_latest_readings IS 'Latest reading for each parameter at each USGS site. Refresh with: REFRESH MATERIALIZED VIEW CONCURRENTLY usgs_latest_readings;';

-- =====================================================================
-- SUMMARY
-- =====================================================================
DO $$
BEGIN
    RAISE NOTICE '';
    RAISE NOTICE '=====================================================';
    RAISE NOTICE 'USGS Data Tables Creation Complete';
    RAISE NOTICE '=====================================================';
    RAISE NOTICE 'Table: usgs_instantaneous_values';
    RAISE NOTICE '  - Stores real-time gage measurements';
    RAISE NOTICE '  - 15-minute interval data';
    RAISE NOTICE '  - Primary key: (site_id, parameter_cd, datetime)';
    RAISE NOTICE '';
    RAISE NOTICE 'Materialized View: usgs_latest_readings';
    RAISE NOTICE '  - Quick access to latest values';
    RAISE NOTICE '  - Refresh with: REFRESH MATERIALIZED VIEW CONCURRENTLY usgs_latest_readings';
    RAISE NOTICE '=====================================================';
END $$;
