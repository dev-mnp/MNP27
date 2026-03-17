-- ============================================================================
-- ADD FUND REQUEST LINKS TO BENEFICIARY AND ORDER TABLES
-- ============================================================================
-- This migration adds optional fund_request_id foreign keys to link beneficiary
-- entries and order entries to fund request records
-- Created: 2025-01-23
-- ============================================================================

-- Add fund_request_id to district_beneficiary_entries
ALTER TABLE district_beneficiary_entries
ADD COLUMN IF NOT EXISTS fund_request_id UUID REFERENCES fund_request(id) ON DELETE SET NULL;

-- Add fund_request_id to public_beneficiary_entries
ALTER TABLE public_beneficiary_entries
ADD COLUMN IF NOT EXISTS fund_request_id UUID REFERENCES fund_request(id) ON DELETE SET NULL;

-- Add fund_request_id to institution_beneficiary_entries (if table exists)
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'institutions_beneficiary_entries') THEN
    ALTER TABLE institutions_beneficiary_entries
    ADD COLUMN IF NOT EXISTS fund_request_id UUID REFERENCES fund_request(id) ON DELETE SET NULL;
  END IF;
END $$;

-- Add fund_request_id to order_entries
ALTER TABLE order_entries
ADD COLUMN IF NOT EXISTS fund_request_id UUID REFERENCES fund_request(id) ON DELETE SET NULL;

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_district_beneficiary_fund_request_id ON district_beneficiary_entries(fund_request_id);
CREATE INDEX IF NOT EXISTS idx_public_beneficiary_fund_request_id ON public_beneficiary_entries(fund_request_id);
CREATE INDEX IF NOT EXISTS idx_order_entries_fund_request_id ON order_entries(fund_request_id);

-- Create index for institution_beneficiary_entries if table exists
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'institutions_beneficiary_entries') THEN
    CREATE INDEX IF NOT EXISTS idx_institution_beneficiary_fund_request_id ON institutions_beneficiary_entries(fund_request_id);
  END IF;
END $$;

