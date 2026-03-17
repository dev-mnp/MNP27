-- ============================================================================
-- CREATE APP USERS TABLE FOR USER MANAGEMENT
-- ============================================================================
-- Simple user management table that links to Supabase Auth
-- Stores user profile info (name, role, status)
-- Created: 2025-01-19
-- ============================================================================

CREATE TABLE IF NOT EXISTS app_users (
  id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  email TEXT NOT NULL UNIQUE,
  name TEXT,
  first_name TEXT,
  last_name TEXT,
  role TEXT NOT NULL DEFAULT 'viewer' CHECK (role IN ('admin', 'editor', 'viewer')),
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive')),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_app_users_email ON app_users(email);
CREATE INDEX IF NOT EXISTS idx_app_users_role ON app_users(role);
CREATE INDEX IF NOT EXISTS idx_app_users_status ON app_users(status);

-- Create updated_at trigger
CREATE OR REPLACE FUNCTION update_app_users_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_app_users_updated_at
  BEFORE UPDATE ON app_users
  FOR EACH ROW
  EXECUTE FUNCTION update_app_users_updated_at();

-- ============================================================================
-- RLS POLICY (for development - allow all operations)
-- ============================================================================

ALTER TABLE app_users ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Allow all operations on app_users" ON app_users;

CREATE POLICY "Allow all operations on app_users"
  ON app_users FOR ALL
  USING (true)
  WITH CHECK (true);
