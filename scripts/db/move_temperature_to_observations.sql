-- =====================================================================
-- Move temperature_timeseries to observations schema
-- =====================================================================
-- Temperature data from Open-Meteo is observational/forecast data,
-- not internally derived data. Moving to observations schema.
-- =====================================================================

-- Move temperature_timeseries table
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'derived'
        AND table_name = 'temperature_timeseries'
    ) THEN
        ALTER TABLE derived.temperature_timeseries SET SCHEMA observations;
        RAISE NOTICE 'Moved temperature_timeseries from derived to observations schema';
    ELSE
        RAISE NOTICE 'temperature_timeseries not found in derived schema (may already be moved)';
    END IF;
END $$;

-- Verify the move
DO $$
DECLARE
    table_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO table_count
    FROM information_schema.tables
    WHERE table_schema = 'observations'
    AND table_name = 'temperature_timeseries';

    IF table_count = 1 THEN
        RAISE NOTICE 'SUCCESS: temperature_timeseries is now in observations schema';
    ELSE
        RAISE NOTICE 'WARNING: temperature_timeseries not found in observations schema';
    END IF;
END $$;
