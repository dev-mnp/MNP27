-- Rename cheque_sl_no to cheque_no in fund_request_recipients table
ALTER TABLE fund_request_recipients
RENAME COLUMN cheque_sl_no TO cheque_no;

-- Rename cheque_sl_no to cheque_no in fund_request_articles table
ALTER TABLE fund_request_articles
RENAME COLUMN cheque_sl_no TO cheque_no;

-- Update any indexes if they reference the old column name
-- (Check if any indexes exist and update them if needed)
-- Note: Supabase will handle index updates automatically when columns are renamed

