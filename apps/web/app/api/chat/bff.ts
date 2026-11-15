/**
 * Shared helpers for the authenticated chat BFF (Phase 1A.2 PR4).
 *
 * Browser → Next.js (Auth.js session) → private FastAPI (service principal).
 * owner_email is derived only from the allowlisted session — never from the
 * browser body/query. Service credentials never leave the server.
 */

import "server-only";

import { getAllowlistedSession } from "../../../auth-session";
import { apiAuthHeaders, getApiBaseUrl } from "../../api";

const SSE_RESPONSE_HEADERS: Record<string, string> = {
  "Content-Type": "text/event-stream; charset=utf-8",
  "Cache-Control": "no-store, no-transform",
  "X-Accel-Buffering": "no",
  Connection: "keep-alive",
};

export type ChatOwner = {
  email: string;
};

/**
 * Resolve the chat owner from the allowlisted Auth.js session.
 * Returns null when unauthenticated / not allowlisted.
 */
export async function resolveChatOwner(): Promise<ChatOwner | null> {
  const session = await getAllowlistedSession();
  const email = session?.user?.email?.trim().toLowerCase();
  if (!email || !email.includes("@")) {
    return null;
  }
  return { email };
}

export function unauthorizedJson(): Response {
  return Response.json(
    {
      detail: {
        code: "unauthenticated",
        message: "Authentication required",
      },
    },
    {
      status: 401,
      headers: { "Cache-Control": "no-store" },
    },
  );
}

/** Drop any client-supplied owner_email and inject the session owner. */
export function withSessionOwner<T extends Record<string, unknown>>(
  body: T | null | undefined,
  ownerEmail: string,
): T & { owner_email: string } {
  const { owner_email: _forged, ...rest } = (body ?? {}) as T & {
    owner_email?: unknown;
  };
  void _forged;
  return { ...(rest as T), owner_email: ownerEmail };
}

export async function readJsonBody(
  request: Request,
): Promise<Record<string, unknown>> {
  const contentType = request.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) {
    return {};
  }
  try {
    const parsed: unknown = await request.json();
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      return parsed as Record<string, unknown>;
    }
    return {};
  } catch {
    return {};
  }
}

function upstreamUrl(path: string, query?: URLSearchParams): string {
  const base = getApiBaseUrl();
  const qs = query && query.toString() ? `?${query.toString()}` : "";
  return `${base}${path}${qs}`;
}

/**
 * Proxy a non-streaming JSON request to FastAPI with service credentials.
 * Forwards upstream status and body (including 404/409 structured errors).
 */
export async function proxyChatJson(options: {
  path: string;
  method: string;
  ownerEmail: string;
  body?: Record<string, unknown> | null;
  query?: Record<string, string | undefined>;
  signal?: AbortSignal;
}): Promise<Response> {
  const query = new URLSearchParams();
  if (options.query) {
    for (const [key, value] of Object.entries(options.query)) {
      if (value !== undefined && value !== "") {
        query.set(key, value);
      }
    }
  }
  // GETs that require owner use the session email only.
  if (options.method.toUpperCase() === "GET") {
    query.set("owner_email", options.ownerEmail);
  }

  const hasBody =
    options.body !== undefined &&
    options.body !== null &&
    options.method.toUpperCase() !== "GET" &&
    options.method.toUpperCase() !== "HEAD";

  const payload = hasBody
    ? withSessionOwner(options.body, options.ownerEmail)
    : undefined;

  let upstream: Response;
  try {
    upstream = await fetch(upstreamUrl(options.path, query), {
      method: options.method,
      headers: apiAuthHeaders({
        Accept: "application/json",
        ...(payload ? { "Content-Type": "application/json" } : {}),
      }),
      body: payload ? JSON.stringify(payload) : undefined,
      signal: options.signal,
      cache: "no-store",
    });
  } catch {
    if (options.signal?.aborted) {
      return new Response(null, { status: 499 });
    }
    return Response.json(
      {
        detail: {
          code: "upstream_unreachable",
          message: "Chat API is unavailable",
        },
      },
      { status: 502, headers: { "Cache-Control": "no-store" } },
    );
  }

  const contentType = upstream.headers.get("Content-Type") ?? "application/json";
  const text = await upstream.text();
  return new Response(text, {
    status: upstream.status,
    headers: {
      "Content-Type": contentType,
      "Cache-Control": "no-store",
    },
  });
}

/**
 * Proxy an SSE stream from FastAPI without buffering the full body.
 * Propagates browser abort via fetch signal and stream cancel.
 */
export async function proxyChatSse(options: {
  path: string;
  ownerEmail: string;
  body: Record<string, unknown>;
  signal: AbortSignal;
}): Promise<Response> {
  const payload = withSessionOwner(options.body, options.ownerEmail);

  let upstream: Response;
  try {
    upstream = await fetch(upstreamUrl(options.path), {
      method: "POST",
      headers: apiAuthHeaders({
        Accept: "text/event-stream",
        "Content-Type": "application/json",
      }),
      body: JSON.stringify(payload),
      signal: options.signal,
      cache: "no-store",
    });
  } catch {
    if (options.signal.aborted) {
      return new Response(null, { status: 499 });
    }
    return Response.json(
      {
        detail: {
          code: "upstream_unreachable",
          message: "Chat API is unavailable",
        },
      },
      { status: 502, headers: { "Cache-Control": "no-store" } },
    );
  }

  // Non-2xx before stream starts (401/403/404/409/422…): forward as-is.
  if (!upstream.ok || !upstream.body) {
    const contentType =
      upstream.headers.get("Content-Type") ?? "application/json";
    const text = await upstream.text();
    return new Response(text, {
      status: upstream.status,
      headers: {
        "Content-Type": contentType,
        "Cache-Control": "no-store",
      },
    });
  }

  const reader = upstream.body.getReader();
  const stream = new ReadableStream<Uint8Array>({
    async pull(controller) {
      try {
        const { done, value } = await reader.read();
        if (done) {
          controller.close();
          return;
        }
        controller.enqueue(value);
      } catch (error) {
        try {
          await reader.cancel();
        } catch {
          // ignore cancel errors during teardown
        }
        controller.error(error);
      }
    },
    async cancel(reason) {
      try {
        await reader.cancel(reason);
      } catch {
        // ignore
      }
    },
  });

  return new Response(stream, {
    status: upstream.status,
    headers: SSE_RESPONSE_HEADERS,
  });
}

/** Test helper: ensure Authorization never appears in a Response body string. */
export function responseMentionsServiceCredential(
  body: string,
  credential: string,
): boolean {
  if (!credential) return false;
  return body.includes(credential) || body.includes("Bearer ");
}
