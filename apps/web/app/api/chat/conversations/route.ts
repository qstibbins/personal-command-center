import {
  proxyChatJson,
  readJsonBody,
  resolveChatOwner,
  unauthorizedJson,
} from "../bff";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/** GET /api/chat/conversations — list conversations for the session owner. */
export async function GET(request: Request): Promise<Response> {
  const owner = await resolveChatOwner();
  if (!owner) {
    return unauthorizedJson();
  }

  const url = new URL(request.url);
  // Ignore any client-supplied owner_email query param.
  const limit = url.searchParams.get("limit") ?? undefined;

  return proxyChatJson({
    path: "/api/v1/chat/conversations",
    method: "GET",
    ownerEmail: owner.email,
    query: { limit },
    signal: request.signal,
  });
}

/** POST /api/chat/conversations — create a conversation for the session owner. */
export async function POST(request: Request): Promise<Response> {
  const owner = await resolveChatOwner();
  if (!owner) {
    return unauthorizedJson();
  }

  const body = await readJsonBody(request);
  return proxyChatJson({
    path: "/api/v1/chat/conversations",
    method: "POST",
    ownerEmail: owner.email,
    body,
    signal: request.signal,
  });
}
