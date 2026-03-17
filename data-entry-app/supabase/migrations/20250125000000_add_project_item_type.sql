-- ============================================================================
-- ADD 'PROJECT' TO ITEM_TYPE CHECK CONSTRAINT
-- ============================================================================
-- This migration updates the articles table to allow 'Project' as an item_type
-- Created: 2025-01-25
-- ============================================================================

-- Drop the existing check constraint
ALTER TABLE articles DROP CONSTRAINT IF EXISTS articles_item_type_check;

-- Add the new check constraint with 'Project' included
ALTER TABLE articles ADD CONSTRAINT articles_item_type_check 
  CHECK (item_type IN ('Article', 'Aid', 'Project'));

