import { createClient } from '@supabase/supabase-js';

const supabaseUrl = import.meta.env.SUPABASE_URL;
const supabaseKey = import.meta.env.SUPABASE_ANON_KEY;

if (!supabaseUrl || !supabaseKey) {
  throw new Error('Missing Supabase environment variables');
}

export const supabase = createClient(supabaseUrl, supabaseKey);

export interface StoredScript {
  id: string;
  script_content: string;
  platform: 'macos' | 'linux';
  distribution?: string;
  apps: string[];
  expires_at: string;
  created_at: string;
}