import { createClient } from '@supabase/supabase-js';

const supabaseUrl = "https://awzmtrrvnnazinepdyic.supabase.co";
const supabaseKey = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImF3em10cnJ2bm5hemluZXBkeWljIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTEyNTY3OTUsImV4cCI6MjA2NjgzMjc5NX0.KgCR648zqz5HAK9u6goxdzvvdZ09ql6OpdsnEF_kXcY";
const supabase = createClient(supabaseUrl, supabaseKey);

export { supabase as s };
