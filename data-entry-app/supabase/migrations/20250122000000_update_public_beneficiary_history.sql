-- ============================================================================
-- UPDATE PUBLIC BENEFICIARY HISTORY TABLE
-- ============================================================================
-- This migration updates the public_beneficiary_history table to match
-- the CSV structure from public_beneficiary_history_modified.csv
-- Created: 2025-01-22
-- ============================================================================

-- Add new columns
ALTER TABLE public_beneficiary_history
  ADD COLUMN IF NOT EXISTS application_number TEXT,
  ADD COLUMN IF NOT EXISTS comments TEXT,
  ADD COLUMN IF NOT EXISTS is_handicapped BOOLEAN DEFAULT false,
  ADD COLUMN IF NOT EXISTS address TEXT,
  ADD COLUMN IF NOT EXISTS mobile TEXT;

-- Remove total_amount column (as per requirement)
ALTER TABLE public_beneficiary_history
  DROP COLUMN IF EXISTS total_amount;

-- ============================================================================
-- COMMENTS (Documentation)
-- ============================================================================

COMMENT ON COLUMN public_beneficiary_history.application_number IS 'Application number from historical records';
COMMENT ON COLUMN public_beneficiary_history.comments IS 'Comments or notes from historical records';
COMMENT ON COLUMN public_beneficiary_history.is_handicapped IS 'Whether the beneficiary is handicapped';
COMMENT ON COLUMN public_beneficiary_history.address IS 'Address of the beneficiary';
COMMENT ON COLUMN public_beneficiary_history.mobile IS 'Mobile number of the beneficiary';

