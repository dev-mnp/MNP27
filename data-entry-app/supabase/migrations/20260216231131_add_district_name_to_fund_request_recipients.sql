-- Add district_name column to fund_request_recipients table
ALTER TABLE fund_request_recipients
ADD COLUMN IF NOT EXISTS district_name TEXT;

-- Add comment to explain the column
COMMENT ON COLUMN fund_request_recipients.district_name IS 'Name of the district for District type beneficiaries';

