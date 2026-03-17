-- ============================================================================
-- CREATE ORDER ENTRIES TABLE FOR ORDER TRACKING
-- ============================================================================
-- This migration creates a table to track purchase orders for articles.
-- Allows incremental ordering (e.g., order 4 today, order rest tomorrow)
-- Created: 2025-01-18
-- ============================================================================

CREATE TABLE IF NOT EXISTS order_entries (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  article_id UUID NOT NULL REFERENCES articles(id) ON DELETE RESTRICT,
  quantity_ordered INTEGER NOT NULL DEFAULT 1 CHECK (quantity_ordered > 0),
  order_date DATE NOT NULL DEFAULT CURRENT_DATE,
  status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'ordered', 'received', 'cancelled')),
  supplier_name TEXT,
  supplier_contact TEXT,
  unit_price NUMERIC,
  total_amount NUMERIC NOT NULL DEFAULT 0,
  expected_delivery_date DATE,
  notes TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  created_by UUID
);

-- Create indexes for faster queries
CREATE INDEX IF NOT EXISTS idx_order_entries_article_id ON order_entries(article_id);
CREATE INDEX IF NOT EXISTS idx_order_entries_order_date ON order_entries(order_date);
CREATE INDEX IF NOT EXISTS idx_order_entries_status ON order_entries(status);
CREATE INDEX IF NOT EXISTS idx_order_entries_article_status ON order_entries(article_id, status);

-- Create updated_at trigger
CREATE OR REPLACE FUNCTION update_order_entries_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_order_entries_updated_at
  BEFORE UPDATE ON order_entries
  FOR EACH ROW
  EXECUTE FUNCTION update_order_entries_updated_at();

-- ============================================================================
-- RLS POLICY (for development - allow all operations)
-- ============================================================================

ALTER TABLE order_entries ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Allow all operations on order_entries" ON order_entries;

CREATE POLICY "Allow all operations on order_entries"
  ON order_entries FOR ALL
  USING (true)
  WITH CHECK (true);