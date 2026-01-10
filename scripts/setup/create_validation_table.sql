-- =====================================================================
-- NWM-USGS Validation Table
-- =====================================================================
-- Stores validation metrics comparing NWM predictions with USGS observations
-- =====================================================================

CREATE TABLE IF NOT EXISTS nwm_usgs_validation (
    -- Identification
    site_id VARCHAR(50) NOT NULL,
    site_name VARCHAR(255),
    nwm_product VARCHAR(50) NOT NULL,

    -- Validation Period
    validation_start TIMESTAMPTZ NOT NULL,
    validation_end TIMESTAMPTZ NOT NULL,

    -- Sample Size
    n_observations INTEGER NOT NULL,

    -- Accuracy Metrics
    correlation DOUBLE PRECISION,          -- Pearson correlation coefficient (-1 to 1)
    rmse DOUBLE PRECISION,                 -- Root Mean Square Error (CFS)
    mae DOUBLE PRECISION,                  -- Mean Absolute Error (CFS)
    bias DOUBLE PRECISION,                 -- Mean bias: NWM - USGS (CFS)
    percent_bias DOUBLE PRECISION,         -- Percent bias (%)
    nash_sutcliffe DOUBLE PRECISION,       -- Nash-Sutcliffe Efficiency (-∞ to 1)

    -- Metadata
    validated_at TIMESTAMPTZ DEFAULT NOW(),

    -- Primary key
    PRIMARY KEY (site_id, nwm_product, validation_start, validation_end),

    -- Foreign key to USGS sites
    CONSTRAINT fk_validation_usgs_site
        FOREIGN KEY (site_id)
        REFERENCES "USGS_Flowsites"("siteId")
        ON DELETE CASCADE
);

-- =====================================================================
-- INDEXES
-- =====================================================================

-- Index for querying by site
CREATE INDEX IF NOT EXISTS idx_validation_site
    ON nwm_usgs_validation (site_id);

-- Index for querying by product
CREATE INDEX IF NOT EXISTS idx_validation_product
    ON nwm_usgs_validation (nwm_product);

-- Index for recent validations
CREATE INDEX IF NOT EXISTS idx_validation_recent
    ON nwm_usgs_validation (validated_at DESC);

-- Index for validation period
CREATE INDEX IF NOT EXISTS idx_validation_period
    ON nwm_usgs_validation (validation_start, validation_end);

-- =====================================================================
-- COMMENTS
-- =====================================================================

COMMENT ON TABLE nwm_usgs_validation IS 'Validation metrics comparing NWM predictions with USGS observed data';
COMMENT ON COLUMN nwm_usgs_validation.correlation IS 'Pearson correlation coefficient: 1.0 = perfect correlation, 0.0 = no correlation';
COMMENT ON COLUMN nwm_usgs_validation.rmse IS 'Root Mean Square Error in CFS: lower is better';
COMMENT ON COLUMN nwm_usgs_validation.nash_sutcliffe IS 'Nash-Sutcliffe Efficiency: 1.0 = perfect, 0.0 = as good as mean, <0 = worse than mean';
COMMENT ON COLUMN nwm_usgs_validation.percent_bias IS 'Percent bias: positive = NWM overestimates, negative = NWM underestimates';

-- =====================================================================
-- MATERIALIZED VIEW: Latest Validation Results
-- =====================================================================

CREATE MATERIALIZED VIEW IF NOT EXISTS latest_validation_results AS
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
FROM nwm_usgs_validation
ORDER BY site_id, nwm_product, validated_at DESC;

-- Index on materialized view
CREATE UNIQUE INDEX IF NOT EXISTS idx_latest_validation_site_product
    ON latest_validation_results (site_id, nwm_product);

COMMENT ON MATERIALIZED VIEW latest_validation_results IS 'Latest validation results for each site and product. Refresh with: REFRESH MATERIALIZED VIEW CONCURRENTLY latest_validation_results;';

-- =====================================================================
-- SUMMARY VIEW: Overall Model Performance
-- =====================================================================

CREATE OR REPLACE VIEW validation_summary AS
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
FROM latest_validation_results
GROUP BY nwm_product;

COMMENT ON VIEW validation_summary IS 'Summary of validation performance across all sites for each NWM product';

-- =====================================================================
-- SUMMARY
-- =====================================================================

DO $$
BEGIN
    RAISE NOTICE '';
    RAISE NOTICE '=====================================================';
    RAISE NOTICE 'NWM-USGS Validation Tables Created';
    RAISE NOTICE '=====================================================';
    RAISE NOTICE 'Table: nwm_usgs_validation';
    RAISE NOTICE '  - Stores validation metrics';
    RAISE NOTICE '  - Compares NWM predictions vs USGS observations';
    RAISE NOTICE '';
    RAISE NOTICE 'Materialized View: latest_validation_results';
    RAISE NOTICE '  - Latest validation for each site/product';
    RAISE NOTICE '  - Includes performance rating';
    RAISE NOTICE '';
    RAISE NOTICE 'View: validation_summary';
    RAISE NOTICE '  - Overall model performance summary';
    RAISE NOTICE '=====================================================';
END $$;
