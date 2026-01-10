-- =====================================================================
-- NHD Schema: Geospatial Reference Data
-- =====================================================================
-- Contains NHDPlus flowlines, network topology, and flow statistics
-- These tables are populated by loading NHD GeoJSON data
-- =====================================================================

-- Enable PostGIS
CREATE EXTENSION IF NOT EXISTS postgis;

-- This file defines the schema structure
-- Tables will be created when loading NHD data via:
--   python scripts/ingestion/spatial/load_nhd_data.py <geojson_path>

-- The following tables will be created:
--   - nhd.flowlines (formerly nhd_flowlines)
--   - nhd.network_topology (formerly nhd_network_topology)
--   - nhd.flow_statistics (formerly nhd_flow_statistics)
--   - nhd.reach_centroids (formerly nhd_reach_centroids)
--   - nhd.reach_metadata

-- See scripts/setup/create_nhd_tables.sql for full table definitions

COMMENT ON SCHEMA nhd IS 'Geospatial reference data from NHDPlus v2.1';

RAISE NOTICE 'NHD schema ready - load data with: python scripts/ingestion/spatial/load_nhd_data.py';
