-- ============================================================================
-- ADD ARTICLE FUND REQUEST FIELDS
-- ============================================================================
-- This migration adds new fields for Article fund requests:
-- - cheque_in_favour, cheque_sl_no, supplier_article_name to fund_request_articles
-- - gst_number to fund_request (for Article type)
-- Created: 2025-01-24
-- ============================================================================

-- Add new fields to fund_request_articles table
ALTER TABLE fund_request_articles
  ADD COLUMN IF NOT EXISTS cheque_in_favour TEXT,
  ADD COLUMN IF NOT EXISTS cheque_sl_no TEXT,
  ADD COLUMN IF NOT EXISTS supplier_article_name TEXT;

-- Add gst_number and supplier fields to fund_request table (for Article type)
ALTER TABLE fund_request
  ADD COLUMN IF NOT EXISTS gst_number TEXT,
  ADD COLUMN IF NOT EXISTS supplier_name TEXT,
  ADD COLUMN IF NOT EXISTS supplier_address TEXT,
  ADD COLUMN IF NOT EXISTS supplier_city TEXT,
  ADD COLUMN IF NOT EXISTS supplier_state TEXT,
  ADD COLUMN IF NOT EXISTS supplier_pincode TEXT;

-- Add comments for documentation
COMMENT ON COLUMN fund_request_articles.cheque_in_favour IS 'Cheque in favour for Article fund request';
COMMENT ON COLUMN fund_request_articles.cheque_sl_no IS 'Cheque serial number for Article fund request';
COMMENT ON COLUMN fund_request_articles.supplier_article_name IS 'Supplier article name (used for purchase order)';
COMMENT ON COLUMN fund_request.gst_number IS 'GST number for Article type fund requests (applies to all articles)';
COMMENT ON COLUMN fund_request.supplier_name IS 'Supplier name for Article type fund requests';
COMMENT ON COLUMN fund_request.supplier_address IS 'Supplier address for Article type fund requests';
COMMENT ON COLUMN fund_request.supplier_city IS 'Supplier city for Article type fund requests';
COMMENT ON COLUMN fund_request.supplier_state IS 'Supplier state for Article type fund requests';
COMMENT ON COLUMN fund_request.supplier_pincode IS 'Supplier pincode for Article type fund requests';

