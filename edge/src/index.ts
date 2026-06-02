export interface Env {
  DASHBOARD_API_KEY: string;
  INTERNAL_SECRET: string;
  BACKEND_URL: string;
  DASHBOARD_ORIGIN: string;
  RATE_LIMIT_KV: KVNamespace;
}

const RATE_LIMIT_MAX = 60;
const RATE_LIMIT_WINDOW_S = 60;

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // CORS preflight
    if (request.method === "OPTIONS") {
      return corsResponse(new Response(null, { status: 204 }), env.DASHBOARD_ORIGIN);
    }

    // Auth
    const authHeader = request.headers.get("Authorization") ?? "";
    if (!authHeader.startsWith("Bearer ") || authHeader.slice(7) !== env.DASHBOARD_API_KEY) {
      return corsResponse(new Response(JSON.stringify({ error: "Unauthorized" }), { status: 401 }), env.DASHBOARD_ORIGIN);
    }

    // Rate limiting per user
    const userId = request.headers.get("X-User-ID") ?? "anonymous";
    const key = `rl:${userId}`;
    const now = Math.floor(Date.now() / 1000);
    const windowKey = `${key}:${Math.floor(now / RATE_LIMIT_WINDOW_S)}`;
    const countStr = await env.RATE_LIMIT_KV.get(windowKey);
    const count = countStr ? parseInt(countStr) : 0;
    if (count >= RATE_LIMIT_MAX) {
      return corsResponse(new Response(JSON.stringify({ error: "Rate limit exceeded" }), { status: 429 }), env.DASHBOARD_ORIGIN);
    }
    await env.RATE_LIMIT_KV.put(windowKey, String(count + 1), { expirationTtl: RATE_LIMIT_WINDOW_S * 2 });

    // Forward request — strip Authorization, inject X-Internal-Token
    const forwardHeaders = new Headers(request.headers);
    forwardHeaders.delete("Authorization");
    forwardHeaders.set("X-Internal-Token", env.INTERNAL_SECRET);
    forwardHeaders.set("Host", new URL(env.BACKEND_URL).host);

    const backendUrl = env.BACKEND_URL.replace(/\/$/, "") + new URL(request.url).pathname;
    const backendResp = await fetch(backendUrl, {
      method: request.method,
      headers: forwardHeaders,
      body: request.body,
    });

    const respHeaders = new Headers(backendResp.headers);
    respHeaders.set("Access-Control-Allow-Origin", env.DASHBOARD_ORIGIN);
    return new Response(backendResp.body, { status: backendResp.status, headers: respHeaders });
  },
};

function corsResponse(resp: Response, origin: string): Response {
  const headers = new Headers(resp.headers);
  headers.set("Access-Control-Allow-Origin", origin);
  headers.set("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
  headers.set("Access-Control-Allow-Headers", "Content-Type, Authorization, X-User-ID");
  return new Response(resp.body, { status: resp.status, headers });
}
