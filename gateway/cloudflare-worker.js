const OPENROUTER_CHAT_COMPLETIONS_URL = "https://openrouter.ai/api/v1/chat/completions";
const DEFAULT_MODEL = "qwen/qwen3.5-9b";
const DEFAULT_MAX_TOKENS = 8192;
const DEFAULT_REASONING_EFFORT = "none";

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname === "/health") {
      return jsonResponse({
        ok: true,
        service: "llm-extractor-gateway",
        model: env.DEFAULT_MODEL || DEFAULT_MODEL,
      });
    }

    if (!["/v1/chat/completions", "/chat/completions"].includes(url.pathname)) {
      return jsonError("Not found.", 404);
    }

    if (request.method !== "POST") {
      return jsonError("Method not allowed.", 405);
    }

    if (!env.OPENROUTER_API_KEY) {
      return jsonError("Gateway is not configured.", 500);
    }

    const authError = validateClientAuth(request, env);
    if (authError) {
      return authError;
    }

    let payload;
    try {
      payload = await request.json();
    } catch (_error) {
      return jsonError("Request body must be valid JSON.", 400);
    }

    if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
      return jsonError("Request body must be a JSON object.", 400);
    }

    const policyError = applyGatewayPolicy(payload, env);
    if (policyError) {
      return policyError;
    }

    const upstreamResponse = await fetch(env.OPENROUTER_CHAT_COMPLETIONS_URL || OPENROUTER_CHAT_COMPLETIONS_URL, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.OPENROUTER_API_KEY}`,
        "Content-Type": "application/json",
        "HTTP-Referer": env.OPENROUTER_HTTP_REFERER || "https://github.com/drbahadirsahin/data-extractor",
        "X-Title": env.OPENROUTER_APP_TITLE || "LLM Extractor",
      },
      body: JSON.stringify(payload),
    });

    const responseBody = await upstreamResponse.text();
    return new Response(responseBody, {
      status: upstreamResponse.status,
      headers: {
        "Content-Type": upstreamResponse.headers.get("Content-Type") || "application/json",
        "Cache-Control": "no-store",
      },
    });
  },
};

function validateClientAuth(request, env) {
  const requiredToken = String(env.CLIENT_TOKEN || "").trim();
  if (!requiredToken) {
    return null;
  }
  const header = request.headers.get("Authorization") || "";
  const providedToken = header.replace(/^Bearer\s+/i, "").trim();
  if (!providedToken || providedToken !== requiredToken) {
    return jsonError("Unauthorized.", 401);
  }
  return null;
}

function applyGatewayPolicy(payload, env) {
  payload.stream = false;
  payload.model = String(env.DEFAULT_MODEL || DEFAULT_MODEL);

  const maxTokens = parsePositiveInteger(env.MAX_TOKENS, DEFAULT_MAX_TOKENS);
  payload.max_tokens = Math.min(parsePositiveInteger(payload.max_tokens, maxTokens), maxTokens);

  const reasoningEffort = String(env.DEFAULT_REASONING_EFFORT || DEFAULT_REASONING_EFFORT).trim();
  if (reasoningEffort) {
    payload.reasoning = {
      effort: reasoningEffort,
      exclude: true,
    };
  }

  if (typeof payload.temperature === "number") {
    payload.temperature = Math.max(0, Math.min(payload.temperature, 1));
  }

  if (!Array.isArray(payload.messages) || payload.messages.length === 0) {
    return jsonError("messages must be a non-empty array.", 400);
  }

  return null;
}

function parsePositiveInteger(value, fallback) {
  const parsed = Number.parseInt(String(value ?? ""), 10);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return fallback;
  }
  return parsed;
}

function jsonResponse(payload, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: {
      "Content-Type": "application/json",
      "Cache-Control": "no-store",
    },
  });
}

function jsonError(message, status) {
  return jsonResponse({ error: { message } }, status);
}
