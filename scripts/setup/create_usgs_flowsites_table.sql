-- =====================================================================
-- USGS Flowsites Table Schema
-- =====================================================================
-- This schema supports USGS gage site locations and metadata
-- for integration with flow data and fisheries intelligence.
--
-- Primary Key: id
-- Unique Constraint: siteId (USGS site identifier)
-- =====================================================================

-- Enable PostGIS extension (required for spatial operations)
CREATE EXTENSION IF NOT EXISTS postgis;

-- =====================================================================
-- TABLE: USGS_Flowsites
-- USGS gage site locations with metadata
-- =====================================================================
CREATE TABLE IF NOT EXISTS "USGS_Flowsites" (
    -- Primary Key
    id BIGINT PRIMARY KEY,

    -- Site Identification
    name VARCHAR(255) NOT NULL,
    "siteId" VARCHAR(50) NOT NULL UNIQUE,

    -- Agency & Network Information
    "agencyCode" VARCHAR(10),
    network VARCHAR(50),
    "stateCd" SMALLINT,
    state VARCHAR(50),
    "siteTypeCd" VARCHAR(10),

    -- External References
    "noaaId" VARCHAR(50),
    "managingOr" VARCHAR(255),
    uuid UUID,
    "webcamUrl" TEXT,

    -- Status & Flags
    "isEnabled" BOOLEAN DEFAULT TRUE,

    -- Spatial Geometry (PostGIS Point)
    geom GEOMETRY(POINT, 4326) NOT NULL,

    -- Audit Timestamps
    "createdOn" TIMESTAMPTZ DEFAULT NOW(),
    "createdBy" INTEGER DEFAULT 0,
    "updatedOn" TIMESTAMPTZ DEFAULT NOW(),
    "updatedBy" INTEGER DEFAULT 0
);

-- =====================================================================
-- INDEXES
-- =====================================================================

-- Spatial index (CRITICAL for map queries)
CREATE INDEX IF NOT EXISTS idx_usgs_flowsites_geom
    ON "USGS_Flowsites" USING GIST (geom);

-- Site ID index (for lookups)
CREATE INDEX IF NOT EXISTS idx_usgs_flowsites_siteid
    ON "USGS_Flowsites" ("siteId");

-- State index (for filtering by state)
CREATE INDEX IF NOT EXISTS idx_usgs_flowsites_state
    ON "USGS_Flowsites" (state);

-- Enabled sites index (for active sites only)
CREATE INDEX IF NOT EXISTS idx_usgs_flowsites_enabled
    ON "USGS_Flowsites" ("isEnabled") WHERE "isEnabled" = TRUE;

-- NOAA ID index (for sites with NOAA integration)
CREATE INDEX IF NOT EXISTS idx_usgs_flowsites_noaaid
    ON "USGS_Flowsites" ("noaaId") WHERE "noaaId" IS NOT NULL;

-- =====================================================================
-- COMMENTS
-- =====================================================================
COMMENT ON TABLE "USGS_Flowsites" IS 'USGS gage site locations and metadata for flow monitoring and fisheries intelligence.';
COMMENT ON COLUMN "USGS_Flowsites".id IS 'Primary key - unique identifier for each gage site';
COMMENT ON COLUMN "USGS_Flowsites"."siteId" IS 'USGS site identifier (e.g., 13311000)';
COMMENT ON COLUMN "USGS_Flowsites".geom IS 'Spatial point geometry (EPSG:4326 - WGS84)';
COMMENT ON COLUMN "USGS_Flowsites"."isEnabled" IS 'Whether this site is actively monitored';

-- =====================================================================
-- SUMMARY
-- =====================================================================
DO $$
BEGIN
    RAISE NOTICE '';
    RAISE NOTICE '=====================================================';
    RAISE NOTICE 'USGS Flowsites Table Creation Complete';
    RAISE NOTICE '=====================================================';
    RAISE NOTICE 'Table: USGS_Flowsites';
    RAISE NOTICE 'Primary key: id';
    RAISE NOTICE 'Unique constraint: siteId';
    RAISE NOTICE 'Spatial extension: PostGIS';
    RAISE NOTICE 'Geometry type: POINT (EPSG:4326)';
    RAISE NOTICE '=====================================================';
END $$;
