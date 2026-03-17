-- ============================================================================
-- ADD ARTICLE_COST_PER_UNIT COLUMN TO DISTRICT_BENEFICIARY_ENTRIES
-- ============================================================================
-- This migration adds article_cost_per_unit column to store the actual
-- cost per unit used for each entry (which may differ from article's
-- original cost if it was 0 and a custom value was set)
-- Created: 2025-01-17
-- ============================================================================

ALTER TABLE district_beneficiary_entries
ADD COLUMN IF NOT EXISTS article_cost_per_unit NUMERIC NOT NULL DEFAULT 0;

-- Create index for faster lookups when fetching custom costs for a district
CREATE INDEX IF NOT EXISTS idx_district_beneficiary_entries_district_article 
ON district_beneficiary_entries(district_id, article_id, created_at DESC);

-- ============================================================================
-- RLS POLICY (if needed for development)
-- ============================================================================
-- The existing RLS policy should cover this column automatically
-- ============================================================================
