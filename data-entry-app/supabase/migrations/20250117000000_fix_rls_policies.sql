-- ============================================================================
-- FIX RLS POLICIES FOR DISTRICT BENEFICIARY ENTRIES
-- ============================================================================
-- This migration fixes RLS policies to allow operations for development
-- Since the app uses hardcoded login without Supabase auth, we allow all operations
-- For production, you should implement proper Supabase authentication
-- Created: 2025-01-17
-- ============================================================================

-- Drop existing policies
DROP POLICY IF EXISTS "Admins can do everything on district_beneficiary_entries" ON district_beneficiary_entries;
DROP POLICY IF EXISTS "Editors can select and modify district_beneficiary_entries" ON district_beneficiary_entries;
DROP POLICY IF EXISTS "Viewers can select district_beneficiary_entries" ON district_beneficiary_entries;

-- ============================================================================
-- DEVELOPMENT MODE: Allow all operations (no authentication required)
-- ============================================================================
-- This allows all CRUD operations without authentication checks
-- Use this for development when using hardcoded login
-- ============================================================================

CREATE POLICY "Allow all operations on district_beneficiary_entries"
  ON district_beneficiary_entries FOR ALL
  USING (true)
  WITH CHECK (true);

-- ============================================================================
-- PRODUCTION MODE: Uncomment below and comment out above if you want
-- authenticated-only access (requires Supabase auth to be implemented)
-- ============================================================================

-- CREATE POLICY "Authenticated users can insert district_beneficiary_entries"
--   ON district_beneficiary_entries FOR INSERT
--   WITH CHECK (auth.uid() IS NOT NULL);
--
-- CREATE POLICY "Authenticated users can select district_beneficiary_entries"
--   ON district_beneficiary_entries FOR SELECT
--   USING (auth.uid() IS NOT NULL);
--
-- CREATE POLICY "Authenticated users can update district_beneficiary_entries"
--   ON district_beneficiary_entries FOR UPDATE
--   USING (auth.uid() IS NOT NULL)
--   WITH CHECK (auth.uid() IS NOT NULL);
--
-- CREATE POLICY "Authenticated users can delete district_beneficiary_entries"
--   ON district_beneficiary_entries FOR DELETE
--   USING (auth.uid() IS NOT NULL);
