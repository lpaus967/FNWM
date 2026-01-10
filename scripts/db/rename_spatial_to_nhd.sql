-- =====================================================================
-- Rename spatial schema to nhd
-- =====================================================================
-- The spatial schema contains NHDPlus data, so renaming to 'nhd'
-- for clearer semantic meaning.
-- =====================================================================

-- Rename spatial schema to nhd
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.schemata
        WHERE schema_name = 'spatial'
    ) THEN
        ALTER SCHEMA spatial RENAME TO nhd;
        RAISE NOTICE 'Renamed spatial schema to nhd';
    ELSE
        RAISE NOTICE 'spatial schema not found (may already be renamed)';
    END IF;
END $$;

-- Verify the rename
DO $$
DECLARE
    schema_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO schema_count
    FROM information_schema.schemata
    WHERE schema_name = 'nhd';

    IF schema_count = 1 THEN
        RAISE NOTICE 'SUCCESS: nhd schema exists';
    ELSE
        RAISE NOTICE 'WARNING: nhd schema not found';
    END IF;
END $$;
