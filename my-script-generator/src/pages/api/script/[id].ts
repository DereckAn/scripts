import type { APIRoute } from 'astro';
import { supabase } from '../../../lib/supabase';

export const GET: APIRoute = async ({ params }) => {
  const { id } = params;

  if (!id) {
    return new Response('Script ID required', { status: 400 });
  }

  try {
    // Fetch script from Supabase
    const { data: script, error } = await supabase
      .from('scripts')
      .select('*')
      .eq('id', id)
      .single();

    if (error || !script) {
      return new Response('Script not found', { status: 404 });
    }

    // Check if script has expired
    const now = new Date();
    const expiresAt = new Date(script.expires_at);
    
    if (now > expiresAt) {
      // Clean up expired script
      await supabase.from('scripts').delete().eq('id', id);
      return new Response('Script has expired', { status: 410 });
    }

    // Return the script content with proper headers
    return new Response(script.script_content, {
      status: 200,
      headers: {
        'Content-Type': 'text/plain',
        'Content-Disposition': `attachment; filename="install-${id}.sh"`,
        'Cache-Control': 'no-cache, no-store, must-revalidate',
      },
    });
  } catch (error) {
    console.error('Error fetching script:', error);
    return new Response('Internal server error', { status: 500 });
  }
};