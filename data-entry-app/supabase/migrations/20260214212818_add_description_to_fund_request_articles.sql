-- ============================================================================
-- ADD DESCRIPTION COLUMN TO FUND_REQUEST_ARTICLES
-- ============================================================================
-- This migration adds a description column to the fund_request_articles table
-- to allow users to add descriptions for each article in Fund Request Article form.
-- Created: 2026-02-14
-- ============================================================================

ALTER TABLE fund_request_articles
ADD COLUMN IF NOT EXISTS description TEXT;

-- Add index for description if needed for search (optional)
-- CREATE INDEX IF NOT EXISTS idx_fund_request_articles_description ON fund_request_articles(description);

