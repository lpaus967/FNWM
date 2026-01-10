-- =====================================================================
-- Derived Schema: Computed Intelligence
-- =====================================================================
-- Contains temperature predictions, habitat scores, and map views
-- =====================================================================

-- Computed scores table (for caching species/hatch scores)
CREATE TABLE IF NOT EXISTS derived.computed_scores (
    id SERIAL PRIMARY KEY,
    feature_id BIGINT NOT NULL,
    score_type VARCHAR(50) NOT NULL,
    score_target VARCHAR(100) NOT NULL,
    valid_time TIMESTAMPTZ NOT NULL,
    score_value DOUBLE PRECISION NOT NULL,
    rating VARCHAR(50),
    components JSONB,
    explanation TEXT,
    confidence VARCHAR(20),
    computed_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (feature_id, score_type, score_target, valid_time)
);

CREATE INDEX IF NOT EXISTS idx_scores_feature_time
    ON derived.computed_scores (feature_id, valid_time DESC);

CREATE INDEX IF NOT EXISTS idx_scores_type
    ON derived.computed_scores (score_type);

CREATE INDEX IF NOT EXISTS idx_scores_components
    ON derived.computed_scores USING GIN (components);

-- Map current conditions materialized view
-- This will be created by running create_map_current_conditions_view.sql
-- after spatial and nwm schemas are populated

-- Comments
COMMENT ON SCHEMA derived IS 'Computed intelligence including habitat scores and derived metrics';
COMMENT ON TABLE derived.computed_scores IS 'Cached species and hatch suitability scores';

RAISE NOTICE 'Derived schema initialized';
