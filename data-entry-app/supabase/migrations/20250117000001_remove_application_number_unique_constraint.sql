-- ============================================================================
-- REMOVE UNIQUE CONSTRAINT ON APPLICATION_NUMBER
-- ============================================================================
-- This migration removes the unique constraint on application_number
-- to allow multiple entries with the same application number
-- (since one application can have multiple articles)
-- Created: 2025-01-17
-- ============================================================================

-- Drop the unique constraint on application_number
-- The constraint name follows PostgreSQL naming convention: table_column_key
ALTER TABLE district_beneficiary_entries
DROP CONSTRAINT IF EXISTS district_beneficiary_entries_application_number_key;

-- Note: If the constraint was created with a different name, you can find it with:
-- SELECT constraint_name 
-- FROM information_schema.table_constraints 
-- WHERE table_name = 'district_beneficiary_entries' 
-- AND constraint_type = 'UNIQUE'
-- AND table_schema = 'public';

-- Alternative: If the above doesn't work, you can also try dropping by index name
-- DROP INDEX IF EXISTS district_beneficiary_entries_application_number_key;

-- ============================================================================
-- REMOVE UNIQUE CONSTRAINT ON APPLICATION_NUMBER
-- ============================================================================
-- This migration removes the unique constraint on application_number
-- to allow multiple entries with the same application number
-- (since one application can have multiple articles)
-- Created: 2025-01-17
-- ============================================================================

-- Drop the unique constraint on application_number
ALTER TABLE district_beneficiary_entries
DROP CONSTRAINT IF EXISTS district_beneficiary_entries_application_number_key;
