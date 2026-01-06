-- Create table to store reach centroids for temperature API queries
-- Extracts lat/lon from PostGIS spatial geometries in nhd_flowlines

CREATE TABLE IF NOT EXISTS nhd_reach_centroids (
    nhdplusid BIGINT PRIMARY KEY,
    permanent_identifier VARCHAR(50) NOT NULL,
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Foreign key to nhd_flowlines
    CONSTRAINT fk_nhd_flowlines
        FOREIGN KEY (nhdplusid)
        REFERENCES nhd_flowlines(nhdplusid)
        ON DELETE CASCADE
);

-- Create index for spatial queries
CREATE INDEX IF NOT EXISTS idx_nhd_centroids_latlon
    ON nhd_reach_centroids(latitude, longitude);

-- Populate table with centroids from nhd_flowlines
-- Uses ST_Centroid to extract center point from LineString geometries
-- ST_Y extracts latitude, ST_X extracts longitude
INSERT INTO nhd_reach_centroids (nhdplusid, permanent_identifier, latitude, longitude)
SELECT
    nhdplusid,
    permanent_identifier,
    ST_Y(ST_Centroid(geom)) AS latitude,
    ST_X(ST_Centroid(geom)) AS longitude
FROM nhd_flowlines
WHERE geom IS NOT NULL
ON CONFLICT (nhdplusid) DO UPDATE
    SET permanent_identifier = EXCLUDED.permanent_identifier,
        latitude = EXCLUDED.latitude,
        longitude = EXCLUDED.longitude;

-- Verify results
SELECT
    COUNT(*) as total_centroids,
    MIN(latitude) as min_lat,
    MAX(latitude) as max_lat,
    MIN(longitude) as min_lon,
    MAX(longitude) as max_lon
FROM nhd_reach_centroids;
