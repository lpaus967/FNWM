-- =====================================================================
-- FNWM Database Schema Organization
-- =====================================================================
-- This script creates the logical schema structure for organizing
-- database objects by their domain and purpose.
--
-- Schemas:
--   1. nwm - National Water Model data and pipeline
--   2. nhd - NHDPlus geospatial reference data (stream network)
--   3. observations - Ground truth data (USGS, user reports)
--   4. derived - Computed intelligence (temperature, scores)
--   5. validation - Model performance metrics
-- =====================================================================

-- Create schemas
CREATE SCHEMA IF NOT EXISTS nwm;
CREATE SCHEMA IF NOT EXISTS nhd;
CREATE SCHEMA IF NOT EXISTS observations;
CREATE SCHEMA IF NOT EXISTS derived;
CREATE SCHEMA IF NOT EXISTS validation;

-- Add schema descriptions
COMMENT ON SCHEMA nwm IS 'National Water Model hydrologic data and ingestion pipeline';
COMMENT ON SCHEMA nhd IS 'NHDPlus geospatial reference data and stream network topology';
COMMENT ON SCHEMA observations IS 'Ground truth observations from USGS gages and user trip reports';
COMMENT ON SCHEMA derived IS 'Computed intelligence including temperature predictions and habitat scores';
COMMENT ON SCHEMA validation IS 'Model performance metrics comparing predictions with observations';

-- Grant usage on schemas (adjust as needed for your security requirements)
GRANT USAGE ON SCHEMA nwm TO PUBLIC;
GRANT USAGE ON SCHEMA nhd TO PUBLIC;
GRANT USAGE ON SCHEMA observations TO PUBLIC;
GRANT USAGE ON SCHEMA derived TO PUBLIC;
GRANT USAGE ON SCHEMA validation TO PUBLIC;

-- Summary
DO $$
BEGIN
    RAISE NOTICE '';
    RAISE NOTICE '=====================================================';
    RAISE NOTICE 'Database Schema Structure Created';
    RAISE NOTICE '=====================================================';
    RAISE NOTICE 'Schemas created:';
    RAISE NOTICE '  - nwm: National Water Model data';
    RAISE NOTICE '  - nhd: NHDPlus geospatial reference data';
    RAISE NOTICE '  - observations: Ground truth data';
    RAISE NOTICE '  - derived: Computed intelligence';
    RAISE NOTICE '  - validation: Model performance metrics';
    RAISE NOTICE '=====================================================';
END $$;
