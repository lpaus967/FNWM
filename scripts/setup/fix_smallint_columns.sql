-- Fix smallint columns that may contain values > 32767
-- Run this to update existing tables without losing data

ALTER TABLE nhd_flowlines
    ALTER COLUMN ftype TYPE INTEGER,
    ALTER COLUMN fcode TYPE INTEGER;

-- Verify the changes
SELECT
    column_name,
    data_type
FROM information_schema.columns
WHERE table_name = 'nhd_flowlines'
    AND column_name IN ('ftype', 'fcode')
ORDER BY column_name;
