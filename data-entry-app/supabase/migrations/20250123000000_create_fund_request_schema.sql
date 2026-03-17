-- ============================================================================
-- FUND REQUEST SCHEMA
-- ============================================================================
-- This migration creates tables for managing fund requests for both Aid and Article types
-- Created: 2025-01-23
-- ============================================================================

-- ============================================================================
-- 1. FUND REQUEST TABLE (Main table)
-- ============================================================================

CREATE TABLE IF NOT EXISTS fund_request (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  fund_request_type TEXT NOT NULL CHECK (fund_request_type IN ('Aid', 'Article')),
  fund_request_number TEXT UNIQUE NOT NULL,
  status TEXT DEFAULT 'draft' CHECK (status IN ('draft', 'submitted', 'approved', 'rejected', 'completed')),
  total_amount NUMERIC NOT NULL DEFAULT 0,
  aid_type TEXT, -- Type of aid (e.g., 'Medical Aid', 'Education Aid', 'Accident Aid', etc.)
  notes TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  created_by UUID
);

-- ============================================================================
-- 2. FUND REQUEST RECIPIENTS TABLE (For Aid - multiple recipients per fund request)
-- ============================================================================

CREATE TABLE IF NOT EXISTS fund_request_recipients (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  fund_request_id UUID NOT NULL REFERENCES fund_request(id) ON DELETE CASCADE,
  beneficiary_type TEXT CHECK (beneficiary_type IN ('District', 'Public', 'Institutions', 'Others')),
  beneficiary TEXT,
  recipient_name TEXT NOT NULL,
  name_of_beneficiary TEXT,
  name_of_institution TEXT,
  details TEXT,
  fund_requested NUMERIC NOT NULL DEFAULT 0,
  aadhar_number TEXT,
  address TEXT,
  cheque_in_favour TEXT,
  cheque_sl_no TEXT,
  notes TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================================
-- 3. FUND REQUEST ARTICLES TABLE (For Article - multiple articles per fund request)
-- ============================================================================

CREATE TABLE IF NOT EXISTS fund_request_articles (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  fund_request_id UUID NOT NULL REFERENCES fund_request(id) ON DELETE CASCADE,
  article_id UUID NOT NULL REFERENCES articles(id) ON DELETE RESTRICT,
  sl_no INTEGER,
  beneficiary TEXT,
  article_name TEXT NOT NULL,
  gst_no TEXT,
  quantity INTEGER NOT NULL DEFAULT 1,
  unit_price NUMERIC NOT NULL DEFAULT 0,
  price_including_gst NUMERIC NOT NULL DEFAULT 0,
  value NUMERIC NOT NULL DEFAULT 0,
  cumulative NUMERIC NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================================
-- 4. FUND REQUEST DOCUMENTS TABLE (Store generated documents metadata)
-- ============================================================================

CREATE TABLE IF NOT EXISTS fund_request_documents (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  fund_request_id UUID NOT NULL REFERENCES fund_request(id) ON DELETE CASCADE,
  document_type TEXT NOT NULL CHECK (document_type IN ('fund_request', 'purchase_order')),
  file_path TEXT,
  file_name TEXT NOT NULL,
  generated_at TIMESTAMPTZ DEFAULT NOW(),
  generated_by UUID
);

-- ============================================================================
-- INDEXES
-- ============================================================================

-- Fund request indexes
CREATE INDEX IF NOT EXISTS idx_fund_request_type ON fund_request(fund_request_type);
CREATE INDEX IF NOT EXISTS idx_fund_request_status ON fund_request(status);
CREATE INDEX IF NOT EXISTS idx_fund_request_number ON fund_request(fund_request_number);
CREATE INDEX IF NOT EXISTS idx_fund_request_created_at ON fund_request(created_at);
CREATE INDEX IF NOT EXISTS idx_fund_request_type_status ON fund_request(fund_request_type, status);
CREATE INDEX IF NOT EXISTS idx_fund_request_aid_type ON fund_request(aid_type);

-- Fund request recipients indexes
CREATE INDEX IF NOT EXISTS idx_fund_request_recipients_fund_request_id ON fund_request_recipients(fund_request_id);
CREATE INDEX IF NOT EXISTS idx_fund_request_recipients_beneficiary_type ON fund_request_recipients(beneficiary_type);

-- Fund request articles indexes
CREATE INDEX IF NOT EXISTS idx_fund_request_articles_fund_request_id ON fund_request_articles(fund_request_id);
CREATE INDEX IF NOT EXISTS idx_fund_request_articles_article_id ON fund_request_articles(article_id);

-- Fund request documents indexes
CREATE INDEX IF NOT EXISTS idx_fund_request_documents_fund_request_id ON fund_request_documents(fund_request_id);
CREATE INDEX IF NOT EXISTS idx_fund_request_documents_type ON fund_request_documents(document_type);

-- ============================================================================
-- TRIGGERS: Auto-update updated_at timestamp
-- ============================================================================

CREATE TRIGGER update_fund_request_updated_at
  BEFORE UPDATE ON fund_request
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- VIEWS
-- ============================================================================

-- Fund Request Summary View
CREATE OR REPLACE VIEW fund_request_summary AS
SELECT 
  fr.id,
  fr.fund_request_type,
  fr.fund_request_number,
  fr.status,
  fr.total_amount,
  fr.aid_type,
  fr.created_at,
  fr.updated_at,
  COUNT(DISTINCT frr.id) AS recipient_count,
  COUNT(DISTINCT fra.id) AS article_count
FROM fund_request fr
LEFT JOIN fund_request_recipients frr ON fr.id = frr.fund_request_id
LEFT JOIN fund_request_articles fra ON fr.id = fra.fund_request_id
GROUP BY fr.id, fr.fund_request_type, fr.fund_request_number, fr.status, fr.total_amount,
         fr.aid_type, fr.created_at, fr.updated_at;

-- ============================================================================
-- ROW LEVEL SECURITY (RLS)
-- ============================================================================

-- Enable RLS on all tables
ALTER TABLE fund_request ENABLE ROW LEVEL SECURITY;
ALTER TABLE fund_request_recipients ENABLE ROW LEVEL SECURITY;
ALTER TABLE fund_request_articles ENABLE ROW LEVEL SECURITY;
ALTER TABLE fund_request_documents ENABLE ROW LEVEL SECURITY;

-- Fund Request RLS Policies
CREATE POLICY "Admins can do everything on fund_request"
  ON fund_request FOR ALL
  USING (is_admin())
  WITH CHECK (is_admin());

CREATE POLICY "Editors can select fund_request"
  ON fund_request 
  FOR SELECT
  USING (is_editor() OR is_admin());

CREATE POLICY "Editors can insert fund_request"
  ON fund_request 
  FOR INSERT
  WITH CHECK (is_editor() OR is_admin());

CREATE POLICY "Editors can modify fund_request"
  ON fund_request 
  FOR UPDATE
  USING (is_editor() OR is_admin())
  WITH CHECK (is_editor() OR is_admin());

CREATE POLICY "Viewers can select fund_request"
  ON fund_request FOR SELECT
  USING (true);

-- Fund Request Recipients RLS Policies
CREATE POLICY "Admins can do everything on fund_request_recipients"
  ON fund_request_recipients FOR ALL
  USING (is_admin())
  WITH CHECK (is_admin());

CREATE POLICY "Editors can select fund_request_recipients"
  ON fund_request_recipients 
  FOR SELECT
  USING (is_editor() OR is_admin());

CREATE POLICY "Editors can insert fund_request_recipients"
  ON fund_request_recipients 
  FOR INSERT
  WITH CHECK (is_editor() OR is_admin());

CREATE POLICY "Editors can modify fund_request_recipients"
  ON fund_request_recipients 
  FOR UPDATE
  USING (is_editor() OR is_admin())
  WITH CHECK (is_editor() OR is_admin());

CREATE POLICY "Editors can select and modify fund_request_recipients"
  ON fund_request_recipients 
  FOR DELETE
  USING (is_editor() OR is_admin());

CREATE POLICY "Viewers can select fund_request_recipients"
  ON fund_request_recipients 
  FOR SELECT
  USING (true);

-- Fund Request Articles RLS Policies
CREATE POLICY "Admins can do everything on fund_request_articles"
  ON fund_request_articles FOR ALL
  USING (is_admin())
  WITH CHECK (is_admin());

CREATE POLICY "Editors can select fund_request_articles"
  ON fund_request_articles 
  FOR SELECT
  USING (is_editor() OR is_admin());

CREATE POLICY "Editors can insert fund_request_articles"
  ON fund_request_articles 
  FOR INSERT
  WITH CHECK (is_editor() OR is_admin());

CREATE POLICY "Editors can modify fund_request_articles"
  ON fund_request_articles 
  FOR UPDATE
  USING (is_editor() OR is_admin())
  WITH CHECK (is_editor() OR is_admin());

CREATE POLICY "Editors can delete fund_request_articles"
  ON fund_request_articles 
  FOR DELETE
  USING (is_editor() OR is_admin());

CREATE POLICY "Viewers can select fund_request_articles"
  ON fund_request_articles 
  FOR SELECT
  USING (true);

-- Fund Request Documents RLS Policies
CREATE POLICY "Admins can do everything on fund_request_documents"
  ON fund_request_documents FOR ALL
  USING (is_admin())
  WITH CHECK (is_admin());

CREATE POLICY "Editors can select fund_request_documents"
  ON fund_request_documents 
  FOR SELECT
  USING (is_editor() OR is_admin());

CREATE POLICY "Editors can insert fund_request_documents"
  ON fund_request_documents 
  FOR INSERT
  WITH CHECK (is_editor() OR is_admin());

CREATE POLICY "Editors can modify fund_request_documents"
  ON fund_request_documents 
  FOR UPDATE
  USING (is_editor() OR is_admin())
  WITH CHECK (is_editor() OR is_admin());

CREATE POLICY "Viewers can select fund_request_documents"
  ON fund_request_documents FOR SELECT
  USING (true);

-- ============================================================================
-- COMMENTS (Documentation)
-- ============================================================================

COMMENT ON TABLE fund_request IS 'Main table for fund request records supporting both Aid and Article types';
COMMENT ON TABLE fund_request_recipients IS 'Recipients for Aid type fund requests (multiple recipients per fund request)';
COMMENT ON TABLE fund_request_articles IS 'Articles for Article type fund requests (multiple articles per fund request)';
COMMENT ON TABLE fund_request_documents IS 'Metadata for generated fund request and purchase order documents';
