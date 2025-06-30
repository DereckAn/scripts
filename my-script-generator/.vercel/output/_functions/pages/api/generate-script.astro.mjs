import { nanoid } from 'nanoid';
import { s as supabase } from '../../chunks/supabase_o3IDeq8X.mjs';
import { S as ScriptGenerator } from '../../chunks/scriptGenerator_EUkB3Ipc.mjs';
export { renderers } from '../../renderers.mjs';

const POST = async ({ request }) => {
  try {
    const body = await request.json();
    const { platform, distribution, selectedApps } = body;
    if (!platform || !selectedApps || !Array.isArray(selectedApps)) {
      return new Response(
        JSON.stringify({ error: "Invalid request data" }),
        { status: 400, headers: { "Content-Type": "application/json" } }
      );
    }
    const generator = new ScriptGenerator();
    const scriptContent = generator.generateScript({
      platform,
      distribution,
      selectedApps
    });
    const scriptId = nanoid(10);
    const expiresAt = new Date(Date.now() + 10 * 60 * 1e3).toISOString();
    const { error } = await supabase.from("scripts").insert({
      id: scriptId,
      script_content: scriptContent,
      platform,
      distribution,
      apps: selectedApps,
      expires_at: expiresAt
    });
    if (error) {
      console.error("Supabase error:", error);
      return new Response(
        JSON.stringify({ error: "Failed to store script" }),
        { status: 500, headers: { "Content-Type": "application/json" } }
      );
    }
    const baseUrl = new URL(request.url).origin;
    const command = `sh -c "$(curl -fsSL ${baseUrl}/api/script/${scriptId})"`;
    return new Response(
      JSON.stringify({
        success: true,
        scriptId,
        command,
        expiresAt
      }),
      { status: 200, headers: { "Content-Type": "application/json" } }
    );
  } catch (error) {
    console.error("Error generating script:", error);
    return new Response(
      JSON.stringify({ error: "Internal server error" }),
      { status: 500, headers: { "Content-Type": "application/json" } }
    );
  }
};

const _page = /*#__PURE__*/Object.freeze(/*#__PURE__*/Object.defineProperty({
  __proto__: null,
  POST
}, Symbol.toStringTag, { value: 'Module' }));

const page = () => _page;

export { page };
