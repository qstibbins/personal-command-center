import {
  proxyChatJson,
  proxyChatSse,
  readJsonBody,
  resolveChatOwner,
  unauthorizedJson,
} from "../../../bff";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type RouteContext = {
  params: Promise<{ conversationId: string }>;
};

/** GET /api/chat/conversations/:id/messages — message history. */
export async function GET(
  request: Request,
  context: RouteContext,
): Promise<Response> {
  const owner = await resolveChatOwner();
  if (!owner) {
    return unauthorizedJson();
  }

  const { conversationId } = await context.params;
  const url = new URL(request.url);
  const limit = url.searchParams.get("limit") ?? undefined;

  return proxyChatJson({
    path: `/api/v1/chat/conversations/${encodeURIComponent(conversationId)}/messages`,
    method: "GET",
    ownerEmail: owner.email,
    query: { limit },
    signal: request.signal,
  });
}

/**
 * POST /api/chat/conversations/:id/messages — stream assistant reply (SSE).
 * Pipes FastAPI chunks without buffering the full response.
 */
export async function POST(
  request: Request,
  context: RouteContext,
): Promise<Response> {
  const owner = await resolveChatOwner();
  if (!owner) {
    return unauthorizedJson();
  }

  const { conversationId } = await context.params;
  const body = await readJsonBody(request);

  return proxyChatSse({
    path: `/api/v1/chat/conversations/${encodeURIComponent(conversationId)}/messages`,
    ownerEmail: owner.email,
    body,
    signal: request.signal,
  });
}
