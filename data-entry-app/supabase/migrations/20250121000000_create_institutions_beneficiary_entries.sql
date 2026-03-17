-- ============================================================================
-- INSTITUTIONS BENEFICIARY ENTRIES TABLE
-- ============================================================================
-- This migration creates the institutions_beneficiary_entries table for
-- managing institutions and others beneficiary entries with multiple articles.
-- Created: 2025-01-21
-- ============================================================================

-- ============================================================================
-- INSTITUTIONS BENEFICIARY ENTRIES TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS institutions_beneficiary_entries (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  institution_name TEXT NOT NULL,
  institution_type TEXT NOT NULL CHECK (institution_type IN ('institutions', 'others')),
  application_number TEXT,
  address TEXT,
  mobile TEXT,
  article_id UUID NOT NULL REFERENCES articles(id) ON DELETE RESTRICT,
  quantity INTEGER NOT NULL DEFAULT 1,
  article_cost_per_unit NUMERIC,
  total_amount NUMERIC NOT NULL DEFAULT 0,
  notes TEXT,
  status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected', 'completed')),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  created_by UUID
);

-- ============================================================================
-- INDEXES
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_institutions_beneficiary_entries_application_number 
  ON institutions_beneficiary_entries(application_number);

CREATE INDEX IF NOT EXISTS idx_institutions_beneficiary_entries_institution_name 
  ON institutions_beneficiary_entries(institution_name);

CREATE INDEX IF NOT EXISTS idx_institutions_beneficiary_entries_institution_type 
  ON institutions_beneficiary_entries(institution_type);

CREATE INDEX IF NOT EXISTS idx_institutions_beneficiary_entries_article_id 
  ON institutions_beneficiary_entries(article_id);

CREATE INDEX IF NOT EXISTS idx_institutions_beneficiary_entries_created_at 
  ON institutions_beneficiary_entries(created_at DESC);

-- ============================================================================
-- ROW LEVEL SECURITY (RLS) POLICIES
-- ============================================================================

ALTER TABLE institutions_beneficiary_entries ENABLE ROW LEVEL SECURITY;

-- Helper function to check if user is admin
CREATE OR REPLACE FUNCTION is_admin()
RETURNS BOOLEAN AS $$
BEGIN
  RETURN EXISTS (
    SELECT 1 FROM app_users
    WHERE id = auth.uid() AND role = 'admin'
  );
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Helper function to check if user is editor
CREATE OR REPLACE FUNCTION is_editor()
RETURNS BOOLEAN AS $$
BEGIN
  RETURN EXISTS (
    SELECT 1 FROM app_users
    WHERE id = auth.uid() AND role IN ('admin', 'editor')
  );
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Institutions Beneficiary Entries RLS Policies
CREATE POLICY "Admins can do everything on institutions_beneficiary_entries"
  ON institutions_beneficiary_entries FOR ALL
  USING (is_admin())
  WITH CHECK (is_admin());

CREATE POLICY "Editors can read institutions_beneficiary_entries"
ON institutions_beneficiary_entries
FOR SELECT
USING (is_editor() OR is_admin());

-- INSERT
CREATE POLICY "Editors can insert institutions_beneficiary_entries"
ON institutions_beneficiary_entries
FOR INSERT
WITH CHECK (is_editor() OR is_admin());

-- UPDATE
CREATE POLICY "Editors can update institutions_beneficiary_entries"
ON institutions_beneficiary_entries
FOR UPDATE
USING (is_editor() OR is_admin())
WITH CHECK (is_editor() OR is_admin());

CREATE POLICY "Viewers can select institutions_beneficiary_entries"
  ON institutions_beneficiary_entries FOR SELECT
  USING (true);

-- ============================================================================
-- COMMENTS (Documentation)
-- ============================================================================

COMMENT ON TABLE institutions_beneficiary_entries IS 'Institutions and others beneficiary entries with multiple articles per application';
