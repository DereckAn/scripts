import type { APIRoute } from 'astro';
import { nanoid } from 'nanoid';
import { supabase } from '../../lib/supabase';
import { ScriptGenerator } from '../../lib/scriptGenerator';

export const POST: APIRoute = async ({ request }) => {
  try {
    const body = await request.json();
    const { platform, distribution, selectedApps } = body;

    if (!platform || !selectedApps || !Array.isArray(selectedApps)) {
      return new Response(
        JSON.stringify({ error: 'Invalid request data' }),
        { status: 400, headers: { 'Content-Type': 'application/json' } }
      );
    }

    // Generate the script
    const generator = new ScriptGenerator();
    const scriptContent = generator.generateScript({
      platform,
      distribution,
      selectedApps,
    });

    // Generate unique ID for the script
    const scriptId = nanoid(10);
    
    // Set expiration time (10 minutes from now)
    const expiresAt = new Date(Date.now() + 10 * 60 * 1000).toISOString();

    // Store in Supabase
    const { error } = await supabase
      .from('scripts')
      .insert({
        id: scriptId,
        script_content: scriptContent,
        platform,
        distribution,
        apps: selectedApps,
        expires_at: expiresAt,
      });

    if (error) {
      console.error('Supabase error:', error);
      return new Response(
        JSON.stringify({ error: 'Failed to store script' }),
        { status: 500, headers: { 'Content-Type': 'application/json' } }
      );
    }

    // Return the command for users to copy
    const baseUrl = new URL(request.url).origin;
    const command = `sh -c "$(curl -fsSL ${baseUrl}/api/script/${scriptId})"`;

    return new Response(
      JSON.stringify({
        success: true,
        scriptId,
        command,
        expiresAt,
      }),
      { status: 200, headers: { 'Content-Type': 'application/json' } }
    );
  } catch (error) {
    console.error('Error generating script:', error);
    return new Response(
      JSON.stringify({ error: 'Internal server error' }),
      { status: 500, headers: { 'Content-Type': 'application/json' } }
    );
  }
};