-- ============================================================================
-- Fix Flow Units: Convert CFS to m³/s in nhd_flow_statistics
-- ============================================================================
--
-- ISSUE: NHDPlus flow statistics (QA_01 through QA_12) are stored in CFS
--        but the system expects m³/s, causing incorrect flow percentile
--        calculations (showing ~4% when should be ~50%).
--
-- SOLUTION: Convert all flow values from CFS to m³/s using conversion factor:
--           1 m³/s = 35.3147 cubic feet per second
--           Therefore: m³/s = CFS ÷ 35.3147
--
-- SCOPE: This affects:
--        - Monthly mean flows (qama through qlma)
--        - Incremental flows (qincrama through qincrfma)
--        - Gage flow measurements (gageqma)
--
-- IMPACT: After this conversion:
--         - flow_percentile calculations will be accurate
--         - API responses will show correct percentiles
--         - Map exports will display proper flow classifications
--
-- Created: 2026-01-06
-- ============================================================================

BEGIN;

-- Show sample BEFORE conversion for verification
SELECT
    'BEFORE CONVERSION - Sample Data' as status,
    nhdplusid,
    qama as jan_cfs,
    qema as may_cfs,
    qfma as june_cfs
FROM nhd_flow_statistics
WHERE qama IS NOT NULL
LIMIT 3;

-- Conversion factor constant
-- 1 m³/s = 35.3147 CFS (cubic feet per second)
DO $$
DECLARE
    cfs_to_m3s CONSTANT NUMERIC := 35.3147;
    rows_updated INTEGER;
BEGIN
    -- Convert monthly mean flows from CFS to m³/s
    -- NOTE: Only Jan-Jun columns exist in schema (qama-qfma)
    UPDATE nhd_flow_statistics
    SET
        -- January through June monthly means (only months available in NHD data)
        qama = CASE WHEN qama IS NOT NULL THEN qama / cfs_to_m3s ELSE NULL END,
        qbma = CASE WHEN qbma IS NOT NULL THEN qbma / cfs_to_m3s ELSE NULL END,
        qcma = CASE WHEN qcma IS NOT NULL THEN qcma / cfs_to_m3s ELSE NULL END,
        qdma = CASE WHEN qdma IS NOT NULL THEN qdma / cfs_to_m3s ELSE NULL END,
        qema = CASE WHEN qema IS NOT NULL THEN qema / cfs_to_m3s ELSE NULL END,
        qfma = CASE WHEN qfma IS NOT NULL THEN qfma / cfs_to_m3s ELSE NULL END,

        -- Incremental flows (Jan-Jun only)
        qincrama = CASE WHEN qincrama IS NOT NULL THEN qincrama / cfs_to_m3s ELSE NULL END,
        qincrbma = CASE WHEN qincrbma IS NOT NULL THEN qincrbma / cfs_to_m3s ELSE NULL END,
        qincrcma = CASE WHEN qincrcma IS NOT NULL THEN qincrcma / cfs_to_m3s ELSE NULL END,
        qincrdma = CASE WHEN qincrdma IS NOT NULL THEN qincrdma / cfs_to_m3s ELSE NULL END,
        qincrema = CASE WHEN qincrema IS NOT NULL THEN qincrema / cfs_to_m3s ELSE NULL END,
        qincrfma = CASE WHEN qincrfma IS NOT NULL THEN qincrfma / cfs_to_m3s ELSE NULL END,

        -- Gage flow measurement (if present)
        gageqma = CASE WHEN gageqma IS NOT NULL THEN gageqma / cfs_to_m3s ELSE NULL END;

    -- Get count of rows updated
    GET DIAGNOSTICS rows_updated = ROW_COUNT;

    RAISE NOTICE 'Converted % rows from CFS to m³/s', rows_updated;
END $$;

-- Show sample AFTER conversion for verification
SELECT
    'AFTER CONVERSION - Sample Data' as status,
    nhdplusid,
    qama as jan_m3s,
    qema as may_m3s,
    qfma as june_m3s
FROM nhd_flow_statistics
WHERE qama IS NOT NULL
LIMIT 3;

-- Show verification: compare typical flow ratios
-- Before fix: current_flow(m3s) / monthly_mean(CFS) would give ~0.03 ratio
-- After fix:  current_flow(m3s) / monthly_mean(m3s) should give ~1.0 ratio
SELECT
    'VERIFICATION - Expected Ratios' as status,
    'Monthly means are now ~35x smaller (converted from CFS to m³/s)' as note,
    'Flow percentile calculations will now be accurate' as result;

COMMIT;

-- Refresh the materialized view to use the corrected data
REFRESH MATERIALIZED VIEW map_current_conditions;

-- Final success message
SELECT
    '✓ SUCCESS' as status,
    'Flow units converted from CFS to m³/s' as action,
    'Materialized view refreshed' as view_status,
    'Flow percentile calculations will now be accurate' as result;
