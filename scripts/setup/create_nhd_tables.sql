-- =====================================================================
-- NHD v2.1 Flowlines Database Schema
-- =====================================================================
-- This schema supports spatial integration of NHDPlus v2.1 flowlines
-- with NWM hydrologic data for fisheries intelligence.
--
-- Primary Key: nhdplusid (joins to hydro_timeseries.feature_id)
--
-- Tables:
--   1. nhd_flowlines - Core spatial and attribute data
--   2. nhd_network_topology - Stream network connections
--   3. nhd_flow_statistics - NHDPlus mean annual flow estimates
-- =====================================================================

-- Enable PostGIS extension (required for spatial operations)
CREATE EXTENSION IF NOT EXISTS postgis;

-- =====================================================================
-- TABLE 1: nhd_flowlines
-- Core NHD flowline attributes with spatial geometry
-- =====================================================================
CREATE TABLE IF NOT EXISTS nhd_flowlines (
    -- Primary Key (joins to NWM data via feature_id)
    nhdplusid BIGINT PRIMARY KEY,
    permanent_identifier VARCHAR(50) NOT NULL,

    -- Stream Naming & Identification
    gnis_id VARCHAR(20),
    gnis_name VARCHAR(255),
    reachcode VARCHAR(14) NOT NULL,

    -- Geographic Attributes
    lengthkm DOUBLE PRECISION NOT NULL,
    areasqkm DOUBLE PRECISION,              -- Incremental drainage area (this reach only)
    totdasqkm DOUBLE PRECISION NOT NULL,    -- Total drainage area (entire upstream watershed)
    divdasqkm DOUBLE PRECISION,             -- Divergence routed area

    -- Stream Classification
    streamorde SMALLINT,                     -- Strahler stream order
    streamleve SMALLINT,                     -- Level in drainage network
    streamcalc SMALLINT,                     -- Calculated stream order
    ftype INTEGER,                           -- Feature type code
    fcode INTEGER,                           -- Feature code

    -- Elevation & Slope
    slope DOUBLE PRECISION,                  -- Stream gradient (m/m)
    slopelenkm DOUBLE PRECISION,             -- Length used for slope calculation
    maxelevraw INTEGER,                      -- Maximum elevation (centimeters)
    minelevraw INTEGER,                      -- Minimum elevation (centimeters)
    maxelevsmo INTEGER,                      -- Smoothed maximum elevation (centimeters)
    minelevsmo INTEGER,                      -- Smoothed minimum elevation (centimeters)

    -- Derived Metrics (computed on insert/update)
    gradient_class VARCHAR(20),              -- pool/run/riffle/cascade
    size_class VARCHAR(20),                  -- headwater/creek/small_river/river/large_river
    elev_drop_m_per_km DOUBLE PRECISION,     -- Elevation drop (meters per kilometer)

    -- Administrative Metadata
    vpuid VARCHAR(4),                        -- Vector Processing Unit ID
    statusflag CHAR(1),                      -- Active status (A = active)
    fdate BIGINT,                            -- Feature date (Unix timestamp)
    resolution SMALLINT,                     -- Data resolution level

    -- Spatial Geometry (PostGIS LineString)
    geom GEOMETRY(LINESTRING, 4326) NOT NULL,

    -- Audit Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Spatial index (CRITICAL for map queries)
CREATE INDEX IF NOT EXISTS idx_nhd_geom
    ON nhd_flowlines USING GIST (geom);

-- Attribute indexes
CREATE INDEX IF NOT EXISTS idx_nhd_gnis_name
    ON nhd_flowlines (gnis_name) WHERE gnis_name IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_nhd_streamorde
    ON nhd_flowlines (streamorde);

CREATE INDEX IF NOT EXISTS idx_nhd_totdasqkm
    ON nhd_flowlines (totdasqkm);

CREATE INDEX IF NOT EXISTS idx_nhd_reachcode
    ON nhd_flowlines (reachcode);

CREATE INDEX IF NOT EXISTS idx_nhd_gradient_class
    ON nhd_flowlines (gradient_class) WHERE gradient_class IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_nhd_size_class
    ON nhd_flowlines (size_class) WHERE size_class IS NOT NULL;

-- Comment on table
COMMENT ON TABLE nhd_flowlines IS 'NHDPlus v2.1 flowline spatial layer with core attributes. Joins to hydro_timeseries via nhdplusid=feature_id.';
COMMENT ON COLUMN nhd_flowlines.nhdplusid IS 'Primary key - joins to NWM data via feature_id';
COMMENT ON COLUMN nhd_flowlines.totdasqkm IS 'Total drainage area - CRITICAL for species habitat scoring';
COMMENT ON COLUMN nhd_flowlines.geom IS 'Spatial geometry for map rendering (EPSG:4326)';


-- =====================================================================
-- TABLE 2: nhd_network_topology
-- Stream network connectivity and routing information
-- =====================================================================
CREATE TABLE IF NOT EXISTS nhd_network_topology (
    -- Primary Key
    nhdplusid BIGINT PRIMARY KEY REFERENCES nhd_flowlines(nhdplusid) ON DELETE CASCADE,

    -- Node Connections
    fromnode BIGINT,                         -- Upstream node ID
    tonode BIGINT,                           -- Downstream node ID

    -- Hydrologic Sequencing
    hydroseq BIGINT NOT NULL,                -- Hydrologic sequence number (for ordering)
    levelpathi BIGINT NOT NULL,              -- Mainstem path identifier
    terminalpa BIGINT NOT NULL,              -- Terminal path ID (basin outlet)

    -- Upstream Connections
    uphydroseq BIGINT,                       -- Upstream hydroseq
    uplevelpat BIGINT,                       -- Upstream level path

    -- Downstream Connections
    dnhydroseq BIGINT,                       -- Downstream hydroseq
    dnlevelpat BIGINT,                       -- Downstream level path
    dnminorhyd BIGINT,                       -- Downstream minor hydroseq
    dndraincou SMALLINT,                     -- Downstream drainage count

    -- Path Metrics
    pathlength DOUBLE PRECISION,             -- Distance to basin outlet (km)
    arbolatesu DOUBLE PRECISION,             -- Total upstream network length (km)

    -- Network Flags
    startflag SMALLINT,                      -- 1 = headwater reach
    terminalfl SMALLINT,                     -- 1 = terminal reach (outlet)
    divergence SMALLINT,                     -- Divergence code
    mainpath SMALLINT,                       -- 1 = on mainstem
    innetwork SMALLINT,                      -- 1 = in active network

    -- Linear Referencing
    frommeas DOUBLE PRECISION,               -- From measure (%)
    tomeas DOUBLE PRECISION                  -- To measure (%)
);

-- Indexes for network traversal
CREATE INDEX IF NOT EXISTS idx_topo_hydroseq
    ON nhd_network_topology (hydroseq);

CREATE INDEX IF NOT EXISTS idx_topo_levelpathi
    ON nhd_network_topology (levelpathi);

CREATE INDEX IF NOT EXISTS idx_topo_dnhydroseq
    ON nhd_network_topology (dnhydroseq) WHERE dnhydroseq IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_topo_uphydroseq
    ON nhd_network_topology (uphydroseq) WHERE uphydroseq IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_topo_startflag
    ON nhd_network_topology (startflag) WHERE startflag = 1;

CREATE INDEX IF NOT EXISTS idx_topo_terminalfl
    ON nhd_network_topology (terminalfl) WHERE terminalfl = 1;

-- Comment on table
COMMENT ON TABLE nhd_network_topology IS 'NHDPlus network topology for stream routing and upstream/downstream analysis.';
COMMENT ON COLUMN nhd_network_topology.hydroseq IS 'Hydrologic sequence - use for ordering reaches from upstream to downstream';
COMMENT ON COLUMN nhd_network_topology.arbolatesu IS 'Total upstream network length - useful for identifying major tributaries';


-- =====================================================================
-- TABLE 3: nhd_flow_statistics
-- NHDPlus mean annual flow estimates (historical context)
-- =====================================================================
CREATE TABLE IF NOT EXISTS nhd_flow_statistics (
    -- Primary Key
    nhdplusid BIGINT PRIMARY KEY REFERENCES nhd_flowlines(nhdplusid) ON DELETE CASCADE,

    -- Mean Annual Flow by Month (m³/s)
    qama DOUBLE PRECISION,                   -- January
    qbma DOUBLE PRECISION,                   -- February
    qcma DOUBLE PRECISION,                   -- March
    qdma DOUBLE PRECISION,                   -- April
    qema DOUBLE PRECISION,                   -- May
    qfma DOUBLE PRECISION,                   -- June
    qgma DOUBLE PRECISION,                   -- July
    qhma DOUBLE PRECISION,                   -- August
    qima DOUBLE PRECISION,                   -- September
    qjma DOUBLE PRECISION,                   -- October
    qkma DOUBLE PRECISION,                   -- November
    qlma DOUBLE PRECISION,                   -- December

    -- Incremental Flow (generated in this reach only)
    qincrama DOUBLE PRECISION,
    qincrbma DOUBLE PRECISION,
    qincrcma DOUBLE PRECISION,
    qincrdma DOUBLE PRECISION,
    qincrema DOUBLE PRECISION,
    qincrfma DOUBLE PRECISION,

    -- Mean Annual Velocity by Month (m/s)
    vama DOUBLE PRECISION,                   -- January velocity
    vbma DOUBLE PRECISION,                   -- February velocity
    vcma DOUBLE PRECISION,                   -- March velocity
    vdma DOUBLE PRECISION,                   -- April velocity
    vema DOUBLE PRECISION,                   -- May velocity

    -- Gage Information
    gageidma VARCHAR(20),                    -- USGS gage ID (if gaged)
    gageqma DOUBLE PRECISION,                -- Gage flow measurement
    gageadjma SMALLINT                       -- 1 = gage-adjusted
);

-- Indexes for flow lookups
CREATE INDEX IF NOT EXISTS idx_flow_stats_qama
    ON nhd_flow_statistics (qama) WHERE qama > 0;

CREATE INDEX IF NOT EXISTS idx_flow_stats_qema
    ON nhd_flow_statistics (qema) WHERE qema > 0;

CREATE INDEX IF NOT EXISTS idx_flow_stats_gaged
    ON nhd_flow_statistics (gageidma) WHERE gageidma IS NOT NULL;

-- Comment on table
COMMENT ON TABLE nhd_flow_statistics IS 'NHDPlus mean annual flow statistics for computing flow percentiles and historical context.';
COMMENT ON COLUMN nhd_flow_statistics.qama IS 'Mean annual flow for January - use for flow percentile calculations';
COMMENT ON COLUMN nhd_flow_statistics.gageidma IS 'USGS gage ID if reach is gaged';


-- =====================================================================
-- FOREIGN KEY: Link NWM data to NHD spatial layer
-- =====================================================================
-- Add foreign key constraint to hydro_timeseries (if table exists)
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_name = 'hydro_timeseries'
    ) THEN
        -- Add constraint if it doesn't exist
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.table_constraints
            WHERE constraint_name = 'fk_hydro_nhd'
        ) THEN
            ALTER TABLE hydro_timeseries
            ADD CONSTRAINT fk_hydro_nhd
            FOREIGN KEY (feature_id)
            REFERENCES nhd_flowlines(nhdplusid)
            ON DELETE RESTRICT;

            RAISE NOTICE 'Added foreign key constraint: hydro_timeseries.feature_id -> nhd_flowlines.nhdplusid';
        END IF;
    END IF;
END $$;


-- =====================================================================
-- TRIGGER: Auto-compute derived metrics on insert/update
-- =====================================================================
CREATE OR REPLACE FUNCTION compute_nhd_derived_metrics()
RETURNS TRIGGER AS $$
BEGIN
    -- Compute gradient class
    NEW.gradient_class := CASE
        WHEN NEW.slope IS NULL THEN NULL
        WHEN NEW.slope < 0.001 THEN 'pool'
        WHEN NEW.slope < 0.01 THEN 'run'
        WHEN NEW.slope < 0.05 THEN 'riffle'
        ELSE 'cascade'
    END;

    -- Compute size class based on drainage area
    NEW.size_class := CASE
        WHEN NEW.totdasqkm IS NULL THEN NULL
        WHEN NEW.totdasqkm < 10 THEN 'headwater'
        WHEN NEW.totdasqkm < 100 THEN 'creek'
        WHEN NEW.totdasqkm < 1000 THEN 'small_river'
        WHEN NEW.totdasqkm < 10000 THEN 'river'
        ELSE 'large_river'
    END;

    -- Compute elevation drop (meters per kilometer)
    IF NEW.maxelevraw IS NOT NULL AND NEW.minelevraw IS NOT NULL
       AND NEW.lengthkm IS NOT NULL AND NEW.lengthkm > 0 THEN
        -- Convert cm to m, then divide by length
        NEW.elev_drop_m_per_km := ((NEW.maxelevraw - NEW.minelevraw) / 100.0) / NEW.lengthkm;
    END IF;

    -- Update timestamp
    NEW.updated_at := NOW();

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_compute_nhd_metrics ON nhd_flowlines;
CREATE TRIGGER trigger_compute_nhd_metrics
    BEFORE INSERT OR UPDATE ON nhd_flowlines
    FOR EACH ROW
    EXECUTE FUNCTION compute_nhd_derived_metrics();


-- =====================================================================
-- SUMMARY
-- =====================================================================
-- Display table creation summary
DO $$
DECLARE
    table_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO table_count
    FROM information_schema.tables
    WHERE table_schema = 'public'
    AND table_name IN ('nhd_flowlines', 'nhd_network_topology', 'nhd_flow_statistics');

    RAISE NOTICE '';
    RAISE NOTICE '=====================================================';
    RAISE NOTICE 'NHD Schema Initialization Complete';
    RAISE NOTICE '=====================================================';
    RAISE NOTICE 'Tables created: %/3', table_count;
    RAISE NOTICE '  1. nhd_flowlines         - Core spatial attributes';
    RAISE NOTICE '  2. nhd_network_topology  - Network connectivity';
    RAISE NOTICE '  3. nhd_flow_statistics   - Flow estimates';
    RAISE NOTICE '';
    RAISE NOTICE 'Spatial extension: PostGIS';
    RAISE NOTICE 'Primary key: nhdplusid';
    RAISE NOTICE 'Join to NWM: nhdplusid = feature_id';
    RAISE NOTICE '=====================================================';
END $$;
