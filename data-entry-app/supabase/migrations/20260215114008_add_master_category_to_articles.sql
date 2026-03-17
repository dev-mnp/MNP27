-- ============================================================================
-- ADD MASTER CATEGORY COLUMN TO ARTICLES TABLE
-- ============================================================================
-- This migration adds a master_category column to the articles table
-- to allow optional categorization of articles
-- Created: 2026-02-15
-- ============================================================================

ALTER TABLE articles
ADD COLUMN IF NOT EXISTS master_category TEXT;

