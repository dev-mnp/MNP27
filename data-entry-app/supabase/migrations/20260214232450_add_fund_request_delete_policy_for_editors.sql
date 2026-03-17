-- ============================================================================
-- ADD DELETE POLICY FOR EDITORS ON FUND_REQUEST TABLE
-- ============================================================================
-- This migration adds a DELETE policy for editors on the fund_request table.
-- Previously, only admins could delete fund requests, which caused deletion
-- to fail silently for editors even though audit logs were created.
-- Created: 2026-02-14
-- ============================================================================

-- Add DELETE policy for editors on fund_request
CREATE POLICY "Editors can delete fund_request"
  ON fund_request 
  FOR DELETE
  USING (is_editor() OR is_admin());

