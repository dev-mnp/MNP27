-- Add combo flag for split/combo articles used in order management
ALTER TABLE articles
  ADD COLUMN IF NOT EXISTS combo BOOLEAN NOT NULL DEFAULT FALSE;

COMMENT ON COLUMN articles.combo IS 'Marks split/combo articles created for order management; typically inactive';
