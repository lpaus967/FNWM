-- =====================================================================
-- Validation Schema: Model Performance Metrics
-- =====================================================================
-- Contains validation metrics comparing NWM predictions with USGS observations
-- =====================================================================

-- NWM-USGS Validation table
CREATE TABLE IF NOT EXISTS validation.nwm_usgs_validation (
    site_id VARCHAR(50) NOT NULL,
    site_name VARCHAR(255),
    nwm_product VARCHAR(50) NOT NULL,
    validation_start TIMESTAMPTZ NOT NULL,
    validation_end TIMESTAMPTZ NOT NULL,
    n_observations INTEGER NOT NULL,
    correlation DOUBLE PRECISION,
    rmse DOUBLE PRECISION,
    mae DOUBLE PRECISION,
    bias DOUBLE PRECISION,
    percent_bias DOUBLE PRECISION,
    nash_sutcliffe DOUBLE PRECISION,
    validated_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (site_id, nwm_product, validation_start, validation_end),
    CONSTRAINT fk_validation_usgs_site
        FOREIGN KEY (site_id)
        REFERENCES observations.usgs_flowsites("siteId")
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_validation_site
    ON validation.nwm_usgs_validation (site_id);

CREATE INDEX IF NOT EXISTS idx_validation_product
    ON validation.nwm_usgs_validation (nwm_product);

CREATE INDEX IF NOT EXISTS idx_validation_recent
    ON validation.nwm_usgs_validation (validated_at DESC);

CREATE INDEX IF NOT EXISTS idx_validation_period
    ON validation.nwm_usgs_validation (validation_start, validation_end);

-- Materialized view for latest validation results
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

-- View for overall model performance summary
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

-- Comments
COMMENT ON SCHEMA validation IS 'Model performance metrics and validation results';
COMMENT ON TABLE validation.nwm_usgs_validation IS 'Statistical validation comparing NWM predictions with USGS observations';
COMMENT ON VIEW validation.summary IS 'Overall model performance summary across all sites';

RAISE NOTICE '✅ Validation schema initialized';
