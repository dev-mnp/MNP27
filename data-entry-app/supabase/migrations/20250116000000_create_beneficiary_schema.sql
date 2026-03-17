-- ============================================================================
-- BENEFICIARY MANAGEMENT SYSTEM SCHEMA
-- ============================================================================
-- This migration creates tables for managing district and public beneficiaries,
-- articles catalog, and historical data for validation.
-- Created: 2025-01-16
-- ============================================================================

-- ============================================================================
-- 1. ARTICLES TABLE (Master Catalog)
-- ============================================================================

CREATE TABLE IF NOT EXISTS articles (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  article_name TEXT NOT NULL UNIQUE,
  cost_per_unit NUMERIC NOT NULL DEFAULT 0,
  item_type TEXT NOT NULL CHECK (item_type IN ('Article', 'Aid')),
  category TEXT,
  is_active BOOLEAN DEFAULT true,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================================
-- 2. DISTRICT MASTER TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS district_master (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  district_name TEXT NOT NULL UNIQUE,
  allotted_budget NUMERIC NOT NULL DEFAULT 0,
  president_name TEXT NOT NULL,
  mobile_number TEXT NOT NULL,
  is_active BOOLEAN DEFAULT true,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================================
-- 3. DISTRICT BENEFICIARY ENTRIES TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS district_beneficiary_entries (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  district_id UUID NOT NULL REFERENCES district_master(id) ON DELETE RESTRICT,
  application_number TEXT UNIQUE,
  article_id UUID NOT NULL REFERENCES articles(id) ON DELETE RESTRICT,
  quantity INTEGER NOT NULL DEFAULT 1,
  total_amount NUMERIC NOT NULL DEFAULT 0,
  notes TEXT,
  status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected', 'completed')),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  created_by UUID
);

-- ============================================================================
-- 4. PUBLIC BENEFICIARY ENTRIES TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS public_beneficiary_entries (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  application_number TEXT UNIQUE,
  name TEXT NOT NULL,
  aadhar_number TEXT NOT NULL,
  is_handicapped BOOLEAN DEFAULT false,
  address TEXT,
  mobile TEXT,
  article_id UUID NOT NULL REFERENCES articles(id) ON DELETE RESTRICT,
  quantity INTEGER NOT NULL DEFAULT 1,
  total_amount NUMERIC NOT NULL DEFAULT 0,
  notes TEXT,
  status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected', 'completed')),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  created_by UUID
);

-- ============================================================================
-- 5. PUBLIC BENEFICIARY HISTORY TABLE (For Aadhar Validation)
-- ============================================================================

CREATE TABLE IF NOT EXISTS public_beneficiary_history (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  aadhar_number TEXT NOT NULL,
  name TEXT NOT NULL,
  year INTEGER NOT NULL,
  article_name TEXT,
  total_amount NUMERIC DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================================
-- INDEXES
-- ============================================================================

-- Articles indexes
CREATE INDEX IF NOT EXISTS idx_articles_article_name ON articles(article_name);
CREATE INDEX IF NOT EXISTS idx_articles_item_type ON articles(item_type);
CREATE INDEX IF NOT EXISTS idx_articles_is_active ON articles(is_active);
CREATE INDEX IF NOT EXISTS idx_articles_item_type_active ON articles(item_type, is_active);

-- District master indexes
CREATE INDEX IF NOT EXISTS idx_district_master_district_name ON district_master(district_name);
CREATE INDEX IF NOT EXISTS idx_district_master_is_active ON district_master(is_active);

-- District beneficiary entries indexes
CREATE INDEX IF NOT EXISTS idx_district_beneficiary_district_id ON district_beneficiary_entries(district_id);
CREATE INDEX IF NOT EXISTS idx_district_beneficiary_application_number ON district_beneficiary_entries(application_number);
CREATE INDEX IF NOT EXISTS idx_district_beneficiary_article_id ON district_beneficiary_entries(article_id);
CREATE INDEX IF NOT EXISTS idx_district_beneficiary_status ON district_beneficiary_entries(status);
CREATE INDEX IF NOT EXISTS idx_district_beneficiary_district_status ON district_beneficiary_entries(district_id, status);

-- Public beneficiary entries indexes
CREATE INDEX IF NOT EXISTS idx_public_beneficiary_aadhar ON public_beneficiary_entries(aadhar_number);
CREATE INDEX IF NOT EXISTS idx_public_beneficiary_application_number ON public_beneficiary_entries(application_number);
CREATE INDEX IF NOT EXISTS idx_public_beneficiary_article_id ON public_beneficiary_entries(article_id);
CREATE INDEX IF NOT EXISTS idx_public_beneficiary_status ON public_beneficiary_entries(status);

-- Public beneficiary history indexes
CREATE INDEX IF NOT EXISTS idx_public_history_aadhar ON public_beneficiary_history(aadhar_number);
CREATE INDEX IF NOT EXISTS idx_public_history_aadhar_year ON public_beneficiary_history(aadhar_number, year);

-- ============================================================================
-- TRIGGERS: Auto-update updated_at timestamp
-- ============================================================================

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply trigger to tables with updated_at
CREATE TRIGGER update_articles_updated_at
  BEFORE UPDATE ON articles
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_district_master_updated_at
  BEFORE UPDATE ON district_master
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_district_beneficiary_updated_at
  BEFORE UPDATE ON district_beneficiary_entries
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_public_beneficiary_updated_at
  BEFORE UPDATE ON public_beneficiary_entries
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- VIEWS
-- ============================================================================

-- Order Requirement View: Article-wise summary by beneficiary type
CREATE OR REPLACE VIEW order_requirement_view AS
SELECT 
  a.article_name AS "REQUESTED ARTICLE",
  COALESCE(d.district_count, 0) AS "District",
  COALESCE(i.institution_count, 0) AS "Institution",
  COALESCE(o.others_count, 0) AS "Others",
  COALESCE(p.public_count, 0) AS "Public",
  COALESCE(d.district_count, 0) + 
  COALESCE(i.institution_count, 0) + 
  COALESCE(o.others_count, 0) + 
  COALESCE(p.public_count, 0) AS "Total",
  -- Ordered Quantity and Remaining Quantity can be added based on business logic
  0 AS "Ordered Quantity",
  0 AS "Remaining Quantity"
FROM articles a
LEFT JOIN (
  SELECT article_id, SUM(quantity) as district_count 
  FROM district_beneficiary_entries 
  GROUP BY article_id
) d ON a.id = d.article_id
LEFT JOIN (
  SELECT article_id, SUM(quantity) as public_count 
  FROM public_beneficiary_entries 
  GROUP BY article_id
) p ON a.id = p.article_id
LEFT JOIN (
  SELECT article_id, SUM(quantity) as institution_count 
  FROM district_beneficiary_entries 
  WHERE status = 'approved' -- Placeholder: adjust based on Institution table when created
  GROUP BY article_id
) i ON a.id = i.article_id
LEFT JOIN (
  SELECT article_id, SUM(quantity) as others_count 
  FROM district_beneficiary_entries 
  WHERE status = 'approved' -- Placeholder: adjust based on Others table when created
  GROUP BY article_id
) o ON a.id = o.article_id
WHERE a.is_active = true
ORDER BY a.article_name;

-- District Beneficiary Summary View
CREATE OR REPLACE VIEW district_beneficiary_summary AS
SELECT 
  dbe.id,
  dbe.application_number,
  dm.district_name,
  a.article_name,
  a.cost_per_unit,
  a.item_type,
  a.category,
  dbe.quantity,
  dbe.total_amount,
  dbe.status,
  dbe.notes,
  dbe.created_at,
  dbe.updated_at
FROM district_beneficiary_entries dbe
JOIN district_master dm ON dbe.district_id = dm.id
JOIN articles a ON dbe.article_id = a.id;

-- Public Beneficiary Summary View
CREATE OR REPLACE VIEW public_beneficiary_summary AS
SELECT 
  pbe.id,
  pbe.application_number,
  pbe.name,
  pbe.aadhar_number,
  pbe.is_handicapped,
  pbe.address,
  pbe.mobile,
  a.article_name,
  a.cost_per_unit,
  a.item_type,
  a.category,
  pbe.quantity,
  pbe.total_amount,
  pbe.status,
  pbe.notes,
  pbe.created_at,
  pbe.updated_at
FROM public_beneficiary_entries pbe
JOIN articles a ON pbe.article_id = a.id;

-- District Budget Utilization View
CREATE OR REPLACE VIEW district_budget_utilization AS
SELECT 
  dm.id,
  dm.district_name,
  dm.allotted_budget,
  COALESCE(SUM(dbe.total_amount), 0) AS total_spent,
  dm.allotted_budget - COALESCE(SUM(dbe.total_amount), 0) AS remaining_budget,
  CASE 
    WHEN dm.allotted_budget > 0 THEN 
      ROUND((COALESCE(SUM(dbe.total_amount), 0) / dm.allotted_budget) * 100, 2)
    ELSE 0
  END AS utilization_percentage,
  dm.president_name,
  dm.mobile_number,
  dm.is_active
FROM district_master dm
LEFT JOIN district_beneficiary_entries dbe ON dm.id = dbe.district_id 
  AND dbe.status IN ('approved', 'completed')
GROUP BY dm.id, dm.district_name, dm.allotted_budget, dm.president_name, dm.mobile_number, dm.is_active;

-- ============================================================================
-- ROW LEVEL SECURITY (RLS)
-- ============================================================================

-- Enable RLS on all tables
ALTER TABLE articles ENABLE ROW LEVEL SECURITY;
ALTER TABLE district_master ENABLE ROW LEVEL SECURITY;
ALTER TABLE district_beneficiary_entries ENABLE ROW LEVEL SECURITY;
ALTER TABLE public_beneficiary_entries ENABLE ROW LEVEL SECURITY;
ALTER TABLE public_beneficiary_history ENABLE ROW LEVEL SECURITY;

-- Helper function to check user role (assumes user_roles table exists in user_auth schema)
-- If user_auth schema doesn't exist, these policies will need to be adjusted
CREATE OR REPLACE FUNCTION is_admin()
RETURNS BOOLEAN AS $$
BEGIN
  -- Check if current user has admin role
  -- Adjust this based on your actual auth setup
  RETURN EXISTS (
    SELECT 1 FROM auth.users 
    WHERE auth.users.id = auth.uid()
    -- Add your admin check logic here
  );
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE OR REPLACE FUNCTION is_editor()
RETURNS BOOLEAN AS $$
BEGIN
  -- Check if current user has editor role
  RETURN EXISTS (
    SELECT 1 FROM auth.users 
    WHERE auth.users.id = auth.uid()
    -- Add your editor check logic here
  );
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Articles RLS Policies
CREATE POLICY "Admins can do everything on articles"
  ON articles FOR ALL
  USING (is_admin())
  WITH CHECK (is_admin());

CREATE POLICY "Editors can select and modify articles"
  ON articles FOR SELECT, INSERT, UPDATE
  USING (is_editor() OR is_admin())
  WITH CHECK (is_editor() OR is_admin());

CREATE POLICY "Viewers can select articles"
  ON articles FOR SELECT
  USING (true); -- Allow all authenticated users to view

-- District Master RLS Policies
CREATE POLICY "Admins can do everything on district_master"
  ON district_master FOR ALL
  USING (is_admin())
  WITH CHECK (is_admin());

CREATE POLICY "Editors can select and modify district_master"
  ON district_master FOR SELECT, INSERT, UPDATE
  USING (is_editor() OR is_admin())
  WITH CHECK (is_editor() OR is_admin());

CREATE POLICY "Viewers can select district_master"
  ON district_master FOR SELECT
  USING (true);

-- District Beneficiary Entries RLS Policies
CREATE POLICY "Admins can do everything on district_beneficiary_entries"
  ON district_beneficiary_entries FOR ALL
  USING (is_admin())
  WITH CHECK (is_admin());

CREATE POLICY "Editors can select and modify district_beneficiary_entries"
  ON district_beneficiary_entries FOR SELECT, INSERT, UPDATE
  USING (is_editor() OR is_admin())
  WITH CHECK (is_editor() OR is_admin());

CREATE POLICY "Viewers can select district_beneficiary_entries"
  ON district_beneficiary_entries FOR SELECT
  USING (true);

-- Public Beneficiary Entries RLS Policies
CREATE POLICY "Admins can do everything on public_beneficiary_entries"
  ON public_beneficiary_entries FOR ALL
  USING (is_admin())
  WITH CHECK (is_admin());

CREATE POLICY "Editors can select and modify public_beneficiary_entries"
  ON public_beneficiary_entries FOR SELECT, INSERT, UPDATE
  USING (is_editor() OR is_admin())
  WITH CHECK (is_editor() OR is_admin());

CREATE POLICY "Viewers can select public_beneficiary_entries"
  ON public_beneficiary_entries FOR SELECT
  USING (true);

-- Public Beneficiary History RLS Policies (Read-only for validation)
CREATE POLICY "Admins can do everything on public_beneficiary_history"
  ON public_beneficiary_history FOR ALL
  USING (is_admin())
  WITH CHECK (is_admin());

CREATE POLICY "Editors can select public_beneficiary_history"
  ON public_beneficiary_history FOR SELECT
  USING (is_editor() OR is_admin());

CREATE POLICY "Viewers can select public_beneficiary_history"
  ON public_beneficiary_history FOR SELECT
  USING (true);

-- ============================================================================
-- COMMENTS (Documentation)
-- ============================================================================

COMMENT ON TABLE articles IS 'Master catalog of articles and aids available for distribution';
COMMENT ON TABLE district_master IS 'Master data of districts with president information and allotted budgets';
COMMENT ON TABLE district_beneficiary_entries IS 'District beneficiary entries/requests';
COMMENT ON TABLE public_beneficiary_entries IS 'Public (individual) beneficiary entries';
COMMENT ON TABLE public_beneficiary_history IS 'Historical data of public beneficiaries for Aadhar-based validation (read-only reference)';

COMMENT ON VIEW order_requirement_view IS 'Article-wise summary by beneficiary type matching Order Requirement format';
COMMENT ON VIEW district_beneficiary_summary IS 'District entries with article and district names joined';
COMMENT ON VIEW public_beneficiary_summary IS 'Public entries with article names joined';
COMMENT ON VIEW district_budget_utilization IS 'District master with total spent and remaining budget';
