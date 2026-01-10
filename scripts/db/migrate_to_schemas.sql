-- =====================================================================
-- FNWM Schema Migration Script
-- =====================================================================
-- Migrates existing tables from public schema to organized schemas
--
-- IMPORTANT: Run create_schemas.sql first!
--
-- This script:
-- 1. Creates new schemas if they don't exist
-- 2. Moves tables to appropriate schemas
-- 3. Updates materialized views
-- 4. Preserves all data, indexes, and constraints
-- =====================================================================

-- Ensure schemas exist
CREATE SCHEMA IF NOT EXISTS nwm;
CREATE SCHEMA IF NOT EXISTS nhd;
CREATE SCHEMA IF NOT EXISTS observations;
CREATE SCHEMA IF NOT EXISTS derived;
CREATE SCHEMA IF NOT EXISTS validation;

-- =====================================================================
-- SCHEMA: nwm (National Water Model)
-- =====================================================================

-- Move hydro_timeseries
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'hydro_timeseries') THEN
        ALTER TABLE public.hydro_timeseries SET SCHEMA nwm;
        RAISE NOTICE 'Moved hydro_timeseries to nwm schema';
    END IF;
END $$;

-- Move ingestion_log
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'ingestion_log') THEN
        ALTER TABLE public.ingestion_log SET SCHEMA nwm;
        RAISE NOTICE 'Moved ingestion_log to nwm schema';
    END IF;
END $$;

-- =====================================================================
-- SCHEMA: nhd (NHDPlus Geospatial Reference Data)
-- =====================================================================

-- Move nhd_flowlines
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'nhd_flowlines') THEN
        ALTER TABLE public.nhd_flowlines SET SCHEMA nhd;
        ALTER TABLE nhd.nhd_flowlines RENAME TO flowlines;
        RAISE NOTICE 'Moved nhd_flowlines to nhd.flowlines';
    END IF;
END $$;

-- Move nhd_network_topology
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'nhd_network_topology') THEN
        ALTER TABLE public.nhd_network_topology SET SCHEMA nhd;
        ALTER TABLE nhd.nhd_network_topology RENAME TO network_topology;
        RAISE NOTICE 'Moved nhd_network_topology to nhd.network_topology';
    END IF;
END $$;

-- Move nhd_flow_statistics
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'nhd_flow_statistics') THEN
        ALTER TABLE public.nhd_flow_statistics SET SCHEMA nhd;
        ALTER TABLE nhd.nhd_flow_statistics RENAME TO flow_statistics;
        RAISE NOTICE 'Moved nhd_flow_statistics to nhd.flow_statistics';
    END IF;
END $$;

-- Move nhd_reach_centroids
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'nhd_reach_centroids') THEN
        ALTER TABLE public.nhd_reach_centroids SET SCHEMA nhd;
        ALTER TABLE nhd.nhd_reach_centroids RENAME TO reach_centroids;
        RAISE NOTICE 'Moved nhd_reach_centroids to nhd.reach_centroids';
    END IF;
END $$;

-- Move reach_metadata
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'reach_metadata') THEN
        ALTER TABLE public.reach_metadata SET SCHEMA nhd;
        RAISE NOTICE 'Moved reach_metadata to nhd schema';
    END IF;
END $$;

-- =====================================================================
-- SCHEMA: observations (Ground Truth & Validation Data)
-- =====================================================================

-- Move USGS_Flowsites
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'USGS_Flowsites') THEN
        ALTER TABLE public."USGS_Flowsites" SET SCHEMA observations;
        ALTER TABLE observations."USGS_Flowsites" RENAME TO usgs_flowsites;
        RAISE NOTICE 'Moved USGS_Flowsites to observations.usgs_flowsites';
    END IF;
END $$;

-- Move usgs_instantaneous_values
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'usgs_instantaneous_values') THEN
        ALTER TABLE public.usgs_instantaneous_values SET SCHEMA observations;
        RAISE NOTICE 'Moved usgs_instantaneous_values to observations schema';
    END IF;
END $$;

-- Move user_observations
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'user_observations') THEN
        ALTER TABLE public.user_observations SET SCHEMA observations;
        RAISE NOTICE 'Moved user_observations to observations schema';
    END IF;
END $$;

-- =====================================================================
-- SCHEMA: derived (Computed Intelligence)
-- =====================================================================

-- Move temperature_timeseries
-- NOTE: Temperature data has been reclassified as observational data
-- This script initially moved it to derived, but it has since been moved to observations
-- See scripts/db/move_temperature_to_observations.sql
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'temperature_timeseries') THEN
        ALTER TABLE public.temperature_timeseries SET SCHEMA observations;
        RAISE NOTICE 'Moved temperature_timeseries to observations schema';
    END IF;
END $$;

-- Move computed_scores
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'computed_scores') THEN
        ALTER TABLE public.computed_scores SET SCHEMA derived;
        RAISE NOTICE 'Moved computed_scores to derived schema';
    END IF;
END $$;

-- =====================================================================
-- SCHEMA: validation (Model Performance)
-- =====================================================================

-- Move nwm_usgs_validation
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'nwm_usgs_validation') THEN
        ALTER TABLE public.nwm_usgs_validation SET SCHEMA validation;
        RAISE NOTICE 'Moved nwm_usgs_validation to validation schema';
    END IF;
END $$;

-- =====================================================================
-- Recreate Materialized Views (referencing new schemas)
-- =====================================================================

-- Drop and recreate usgs_latest_readings
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_matviews WHERE schemaname = 'public' AND matviewname = 'usgs_latest_readings') THEN
        DROP MATERIALIZED VIEW public.usgs_latest_readings;
        RAISE NOTICE 'Dropped old usgs_latest_readings view';
    END IF;
END $$;

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

-- usgs_latest_readings created

-- Drop validation_summary view first (depends on latest_validation_results)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_views WHERE schemaname = 'public' AND viewname = 'validation_summary') THEN
        DROP VIEW public.validation_summary;
        RAISE NOTICE 'Dropped old validation_summary view';
    END IF;
END $$;

-- Drop and recreate latest_validation_results
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_matviews WHERE schemaname = 'public' AND matviewname = 'latest_validation_results') THEN
        DROP MATERIALIZED VIEW public.latest_validation_results;
        RAISE NOTICE 'Dropped old latest_validation_results view';
    END IF;
END $$;

CREATE MATERIALIZED VIEW IF NOT EXISTS validation.latest_validation_results AS
SELECT DISTINCT ON (site_id, nwm_product)
    site_id,
    site_name,
    nwm_product,
    validation_start,
    validation_end,
    n_observations,
    correlation,
    rmse,
    mae,
    bias,
    percent_bias,
    nash_sutcliffe,
    validated_at,
    CASE
        WHEN nash_sutcliffe > 0.75 THEN 'Excellent'
        WHEN nash_sutcliffe > 0.65 THEN 'Very Good'
        WHEN nash_sutcliffe > 0.50 THEN 'Good'
        WHEN nash_sutcliffe > 0.40 THEN 'Satisfactory'
        ELSE 'Unsatisfactory'
    END as performance_rating
FROM validation.nwm_usgs_validation
ORDER BY site_id, nwm_product, validated_at DESC;

CREATE UNIQUE INDEX IF NOT EXISTS idx_latest_validation_site_product
    ON validation.latest_validation_results (site_id, nwm_product);

-- latest_validation_results created

-- validation_summary already dropped above

CREATE OR REPLACE VIEW validation.summary AS
SELECT
    nwm_product,
    COUNT(DISTINCT site_id) as sites_validated,
    AVG(n_observations) as avg_observations,
    AVG(correlation) as avg_correlation,
    AVG(rmse) as avg_rmse,
    AVG(mae) as avg_mae,
    AVG(bias) as avg_bias,
    AVG(percent_bias) as avg_percent_bias,
    AVG(nash_sutcliffe) as avg_nash_sutcliffe,
    MAX(validated_at) as last_validation
FROM validation.latest_validation_results
GROUP BY nwm_product;

-- validation.summary view created

-- Drop and recreate map_current_conditions if it exists
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_matviews WHERE schemaname = 'public' AND matviewname = 'map_current_conditions') THEN
        DROP MATERIALIZED VIEW public.map_current_conditions;
        RAISE NOTICE 'Dropped old map_current_conditions view';
    END IF;
END $$;

-- Note: map_current_conditions will need to be recreated with updated schema references
-- This should be done by running the updated create_map_current_conditions_view.sql script

-- =====================================================================
-- Update Foreign Key Constraints (if needed)
-- =====================================================================

-- Update temperature_timeseries foreign key
-- Note: temperature_timeseries is now in observations schema
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'fk_temperature_reach'
        AND table_schema = 'observations'
        AND table_name = 'temperature_timeseries'
    ) THEN
        ALTER TABLE observations.temperature_timeseries
        DROP CONSTRAINT fk_temperature_reach;

        ALTER TABLE observations.temperature_timeseries
        ADD CONSTRAINT fk_temperature_reach
        FOREIGN KEY (nhdplusid)
        REFERENCES nhd.reach_centroids(nhdplusid)
        ON DELETE CASCADE;

        RAISE NOTICE 'Updated temperature_timeseries foreign key';
    END IF;
EXCEPTION
    WHEN OTHERS THEN
        RAISE NOTICE 'WARNING: Could not update temperature_timeseries foreign key (may not exist yet)';
END $$;

-- Update usgs_instantaneous_values foreign key
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'fk_usgs_site'
        AND table_schema = 'observations'
        AND table_name = 'usgs_instantaneous_values'
    ) THEN
        ALTER TABLE observations.usgs_instantaneous_values
        DROP CONSTRAINT fk_usgs_site;

        ALTER TABLE observations.usgs_instantaneous_values
        ADD CONSTRAINT fk_usgs_site
        FOREIGN KEY (site_id)
        REFERENCES observations.usgs_flowsites("siteId")
        ON DELETE CASCADE;

        RAISE NOTICE 'Updated usgs_instantaneous_values foreign key';
    END IF;
EXCEPTION
    WHEN OTHERS THEN
        RAISE NOTICE 'WARNING: Could not update usgs_instantaneous_values foreign key';
END $$;

-- Update nwm_usgs_validation foreign key
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'fk_validation_usgs_site'
        AND table_schema = 'validation'
        AND table_name = 'nwm_usgs_validation'
    ) THEN
        ALTER TABLE validation.nwm_usgs_validation
        DROP CONSTRAINT fk_validation_usgs_site;

        ALTER TABLE validation.nwm_usgs_validation
        ADD CONSTRAINT fk_validation_usgs_site
        FOREIGN KEY (site_id)
        REFERENCES observations.usgs_flowsites("siteId")
        ON DELETE CASCADE;

        RAISE NOTICE 'Updated nwm_usgs_validation foreign key';
    END IF;
EXCEPTION
    WHEN OTHERS THEN
        RAISE NOTICE 'WARNING: Could not update nwm_usgs_validation foreign key';
END $$;

-- =====================================================================
-- Update Search Path (Optional - makes queries easier)
-- =====================================================================

-- This allows you to query tables without schema prefix when possible
-- Uncomment if desired:
-- ALTER DATABASE "fnwm-db" SET search_path TO public, nwm, nhd, observations, derived, validation;

-- =====================================================================
-- Summary
-- =====================================================================

DO $$
DECLARE
    nwm_tables INTEGER;
    nhd_tables INTEGER;
    obs_tables INTEGER;
    derived_tables INTEGER;
    val_tables INTEGER;
BEGIN
    SELECT COUNT(*) INTO nwm_tables FROM information_schema.tables WHERE table_schema = 'nwm';
    SELECT COUNT(*) INTO nhd_tables FROM information_schema.tables WHERE table_schema = 'nhd';
    SELECT COUNT(*) INTO obs_tables FROM information_schema.tables WHERE table_schema = 'observations';
    SELECT COUNT(*) INTO derived_tables FROM information_schema.tables WHERE table_schema = 'derived';
    SELECT COUNT(*) INTO val_tables FROM information_schema.tables WHERE table_schema = 'validation';

    RAISE NOTICE '';
    RAISE NOTICE '=====================================================';
    RAISE NOTICE 'Schema Migration Complete!';
    RAISE NOTICE '=====================================================';
    RAISE NOTICE 'Tables per schema:';
    RAISE NOTICE '  nwm: % tables', nwm_tables;
    RAISE NOTICE '  nhd: % tables', nhd_tables;
    RAISE NOTICE '  observations: % tables', obs_tables;
    RAISE NOTICE '  derived: % tables', derived_tables;
    RAISE NOTICE '  validation: % tables', val_tables;
    RAISE NOTICE '';
    RAISE NOTICE 'Next Steps:';
    RAISE NOTICE '  1. Update application code to use new schema names';
    RAISE NOTICE '  2. Update API queries to reference schemas';
    RAISE NOTICE '  3. Test all functionality';
    RAISE NOTICE '=====================================================';
END $$;
