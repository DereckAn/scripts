-- Create the scripts table for temporary script storage
CREATE TABLE IF NOT EXISTS scripts (
  id TEXT PRIMARY KEY,
  script_content TEXT NOT NULL,
  platform TEXT NOT NULL CHECK (platform IN ('macos', 'linux')),
  distribution TEXT,
  apps TEXT[] NOT NULL,
  expires_at TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create an index on expires_at for efficient cleanup
CREATE INDEX IF NOT EXISTS idx_scripts_expires_at ON scripts(expires_at);

-- Enable Row Level Security (optional but recommended)
ALTER TABLE scripts ENABLE ROW LEVEL SECURITY;

-- Create a policy that allows anyone to read non-expired scripts
CREATE POLICY "Allow read access to non-expired scripts" ON scripts
FOR SELECT USING (expires_at > NOW());

-- Create a policy that allows anyone to insert scripts
CREATE POLICY "Allow insert access to scripts" ON scripts
FOR INSERT WITH CHECK (true);

-- Create a function to automatically delete expired scripts
CREATE OR REPLACE FUNCTION delete_expired_scripts()
RETURNS void AS $$
BEGIN
  DELETE FROM scripts WHERE expires_at < NOW();
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Create a cron job to run cleanup every 5 minutes (requires pg_cron extension)
-- This is optional - you can also run cleanup manually or via a scheduled function
-- SELECT cron.schedule('delete-expired-scripts', '*/5 * * * *', 'SELECT delete_expired_scripts();');