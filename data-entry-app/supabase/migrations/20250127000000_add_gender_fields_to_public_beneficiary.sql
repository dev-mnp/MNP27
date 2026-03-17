-- ============================================================================
-- ADD GENDER FIELDS TO PUBLIC BENEFICIARY ENTRIES
-- ============================================================================
-- This migration adds gender and female_status fields to public_beneficiary_entries
-- Created: 2025-01-27
-- ============================================================================

-- Add gender column
ALTER TABLE public_beneficiary_entries 
ADD COLUMN IF NOT EXISTS gender TEXT CHECK (gender IN ('Male', 'Female', 'Transgender'));

-- Add female_status column (nullable, only relevant when gender is 'Female')
ALTER TABLE public_beneficiary_entries 
ADD COLUMN IF NOT EXISTS female_status TEXT CHECK (female_status IN ('Single Mother', 'Widow', 'Married', 'Unmarried'));

-- Add index for gender field (useful for filtering/reporting)
CREATE INDEX IF NOT EXISTS idx_public_beneficiary_gender ON public_beneficiary_entries(gender);

-- Add index for female_status field
CREATE INDEX IF NOT EXISTS idx_public_beneficiary_female_status ON public_beneficiary_entries(female_status);

