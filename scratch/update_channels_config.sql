-- You need to run this SQL in your Supabase SQL editor to add the new columns
ALTER TABLE channels_config 
ADD COLUMN IF NOT EXISTS instagram_access_token TEXT,
ADD COLUMN IF NOT EXISTS instagram_page_id TEXT,
ADD COLUMN IF NOT EXISTS tiktok_access_token TEXT,
ADD COLUMN IF NOT EXISTS tiktok_shop_id TEXT;
