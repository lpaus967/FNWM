-- =====================================================================
-- NWM Schema: National Water Model Data
-- =====================================================================
-- Contains NWM hydrologic time-series data and ingestion pipeline logs
-- =====================================================================

-- hydro_timeseries table
CREATE TABLE IF NOT EXISTS nwm.hydro_timeseries (
    feature_id BIGINT NOT NULL,
    valid_time TIMESTAMPTZ NOT NULL,
    variable VARCHAR(50) NOT NULL,
    value DOUBLE PRECISION,
    source VARCHAR(50) NOT NULL,
    forecast_hour SMALLINT,
    ingested_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (feature_id, valid_time, variable, source)
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_hydro_feature_time
    ON nwm.hydro_timeseries (feature_id, valid_time DESC);

CREATE INDEX IF NOT EXISTS idx_hydro_source
    ON nwm.hydro_timeseries (source);

CREATE INDEX IF NOT EXISTS idx_hydro_variable
    ON nwm.hydro_timeseries (variable);

CREATE INDEX IF NOT EXISTS idx_hydro_valid_time
    ON nwm.hydro_timeseries (valid_time DESC);

-- ingestion_log table
CREATE TABLE IF NOT EXISTS nwm.ingestion_log (
    id SERIAL PRIMARY KEY,
    product VARCHAR(100) NOT NULL,
    cycle_time TIMESTAMPTZ NOT NULL,
    domain VARCHAR(20),
    status VARCHAR(20) NOT NULL,
    records_ingested INTEGER,
    error_message TEXT,
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    duration_seconds DOUBLE PRECISION
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_log_product_time
    ON nwm.ingestion_log (product, cycle_time DESC);

CREATE INDEX IF NOT EXISTS idx_log_status
    ON nwm.ingestion_log (status);

-- Comments
COMMENT ON TABLE nwm.hydro_timeseries IS 'NWM channel routing time-series data for stream reaches';
COMMENT ON TABLE nwm.ingestion_log IS 'Data pipeline monitoring and ingestion history';

-- Check for TimescaleDB and create hypertable if available
DO $$
DECLARE
    has_timescale BOOLEAN;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM pg_extension WHERE extname = 'timescaledb'
    ) INTO has_timescale;

    IF has_timescale THEN
        -- Check if already a hypertable
        IF NOT EXISTS (
            SELECT 1 FROM timescaledb_information.hypertables
            WHERE hypertable_schema = 'nwm' AND hypertable_name = 'hydro_timeseries'
        ) THEN
            PERFORM create_hypertable(
                'nwm.hydro_timeseries',
                'valid_time',
                if_not_exists => TRUE
            );
            RAISE NOTICE '✓ Created TimescaleDB hypertable for nwm.hydro_timeseries';
        ELSE
            RAISE NOTICE '✓ nwm.hydro_timeseries is already a hypertable';
        END IF;
    ELSE
        RAISE NOTICE '⚠ TimescaleDB not available - using standard table';
    END IF;
END $$;

RAISE NOTICE '✅ NWM schema initialized';
