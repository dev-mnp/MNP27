-- ============================================================================
-- FIX RLS POLICIES FOR PUBLIC AND INSTITUTIONS BENEFICIARY ENTRIES
-- ============================================================================
-- This migration fixes RLS policies to allow operations for development
-- Since the app uses hardcoded login without Supabase auth, we allow all operations
-- For production, you should implement proper Supabase authentication
-- Created: 2025-01-26
-- ============================================================================

-- ============================================================================
-- PUBLIC BENEFICIARY ENTRIES
-- ============================================================================

-- Drop existing policies
DROP POLICY IF EXISTS "Admins can do everything on public_beneficiary_entries" ON public_beneficiary_entries;
DROP POLICY IF EXISTS "Editors can select and modify public_beneficiary_entries" ON public_beneficiary_entries;
DROP POLICY IF EXISTS "Viewers can select public_beneficiary_entries" ON public_beneficiary_entries;

-- ============================================================================
-- DEVELOPMENT MODE: Allow all operations (no authentication required)
-- ============================================================================
-- This allows all CRUD operations without authentication checks
-- Use this for development when using hardcoded login
-- ============================================================================

CREATE POLICY "Allow all operations on public_beneficiary_entries"
  ON public_beneficiary_entries FOR ALL
  USING (true)
  WITH CHECK (true);

-- ============================================================================
-- INSTITUTIONS BENEFICIARY ENTRIES
-- ============================================================================

-- Drop existing policies
DROP POLICY IF EXISTS "Admins can do everything on institutions_beneficiary_entries" ON institutions_beneficiary_entries;
DROP POLICY IF EXISTS "Editors can read institutions_beneficiary_entries" ON institutions_beneficiary_entries;
DROP POLICY IF EXISTS "Editors can insert institutions_beneficiary_entries" ON institutions_beneficiary_entries;
DROP POLICY IF EXISTS "Editors can update institutions_beneficiary_entries" ON institutions_beneficiary_entries;
DROP POLICY IF EXISTS "Viewers can select institutions_beneficiary_entries" ON institutions_beneficiary_entries;

-- ============================================================================
-- DEVELOPMENT MODE: Allow all operations (no authentication required)
-- ============================================================================
-- This allows all CRUD operations including DELETE which was missing
-- Use this for development when using hardcoded login
-- ============================================================================

CREATE POLICY "Allow all operations on institutions_beneficiary_entries"
  ON institutions_beneficiary_entries FOR ALL
  USING (true)
  WITH CHECK (true);

-- ============================================================================
-- PRODUCTION MODE: Uncomment below and comment out above if you want
-- authenticated-only access (requires Supabase auth to be implemented)
-- ============================================================================

-- For public_beneficiary_entries:
-- CREATE POLICY "Authenticated users can insert public_beneficiary_entries"
--   ON public_beneficiary_entries FOR INSERT
--   WITH CHECK (auth.uid() IS NOT NULL);
--
-- CREATE POLICY "Authenticated users can select public_beneficiary_entries"
--   ON public_beneficiary_entries FOR SELECT
--   USING (auth.uid() IS NOT NULL);
--
-- CREATE POLICY "Authenticated users can update public_beneficiary_entries"
--   ON public_beneficiary_entries FOR UPDATE
--   USING (auth.uid() IS NOT NULL)
--   WITH CHECK (auth.uid() IS NOT NULL);
--
-- CREATE POLICY "Authenticated users can delete public_beneficiary_entries"
--   ON public_beneficiary_entries FOR DELETE
--   USING (auth.uid() IS NOT NULL);

-- For institutions_beneficiary_entries:
-- CREATE POLICY "Authenticated users can insert institutions_beneficiary_entries"
--   ON institutions_beneficiary_entries FOR INSERT
--   WITH CHECK (auth.uid() IS NOT NULL);
--
-- CREATE POLICY "Authenticated users can select institutions_beneficiary_entries"
--   ON institutions_beneficiary_entries FOR SELECT
--   USING (auth.uid() IS NOT NULL);
--
-- CREATE POLICY "Authenticated users can update institutions_beneficiary_entries"
--   ON institutions_beneficiary_entries FOR UPDATE
--   USING (auth.uid() IS NOT NULL)
--   WITH CHECK (auth.uid() IS NOT NULL);
--
-- CREATE POLICY "Authenticated users can delete institutions_beneficiary_entries"
--   ON institutions_beneficiary_entries FOR DELETE
--   USING (auth.uid() IS NOT NULL);

