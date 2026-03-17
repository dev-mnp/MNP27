-- ============================================================================
-- ADD PURCHASE ORDER NUMBER COLUMN TO FUND_REQUEST TABLE
-- ============================================================================
-- This migration adds a purchase_order_number column to the fund_request table
-- to store sequential purchase order numbers in format MASM/MNP00126
-- Created: 2026-02-15
-- ============================================================================

ALTER TABLE fund_request
ADD COLUMN IF NOT EXISTS purchase_order_number TEXT;

-- Create index for faster lookups
CREATE INDEX IF NOT EXISTS idx_fund_request_purchase_order_number ON fund_request(purchase_order_number);

