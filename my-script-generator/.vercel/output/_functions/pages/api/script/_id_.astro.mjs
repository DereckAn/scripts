import { s as supabase } from '../../../chunks/supabase_o3IDeq8X.mjs';
export { renderers } from '../../../renderers.mjs';

const GET = async ({ params }) => {
  const { id } = params;
  if (!id) {
    return new Response("Script ID required", { status: 400 });
  }
  try {
    const { data: script, error } = await supabase.from("scripts").select("*").eq("id", id).single();
    if (error || !script) {
      return new Response("Script not found", { status: 404 });
    }
    const now = /* @__PURE__ */ new Date();
    const expiresAt = new Date(script.expires_at);
    if (now > expiresAt) {
      await supabase.from("scripts").delete().eq("id", id);
      return new Response("Script has expired", { status: 410 });
    }
    return new Response(script.script_content, {
      status: 200,
      headers: {
        "Content-Type": "text/plain",
        "Content-Disposition": `attachment; filename="install-${id}.sh"`,
        "Cache-Control": "no-cache, no-store, must-revalidate"
      }
    });
  } catch (error) {
    console.error("Error fetching script:", error);
    return new Response("Internal server error", { status: 500 });
  }
};

const _page = /*#__PURE__*/Object.freeze(/*#__PURE__*/Object.defineProperty({
  __proto__: null,
  GET
}, Symbol.toStringTag, { value: 'Module' }));

const page = () => _page;

export { page };
