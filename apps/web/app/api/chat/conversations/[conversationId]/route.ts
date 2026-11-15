import {
  proxyChatJson,
  readJsonBody,
  resolveChatOwner,
  unauthorizedJson,
} from "../../bff";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type RouteContext = {
  params: Promise<{ conversationId: string }>;
};

/** GET /api/chat/conversations/:id */
export async function GET(
  request: Request,
  context: RouteContext,
): Promise<Response> {
  const owner = await resolveChatOwner();
  if (!owner) {
    return unauthorizedJson();
  }

  const { conversationId } = await context.params;
  return proxyChatJson({
    path: `/api/v1/chat/conversations/${encodeURIComponent(conversationId)}`,
    method: "GET",
    ownerEmail: owner.email,
    signal: request.signal,
  });
}

/** PATCH /api/chat/conversations/:id */
export async function PATCH(
  request: Request,
  context: RouteContext,
): Promise<Response> {
  const owner = await resolveChatOwner();
  if (!owner) {
    return unauthorizedJson();
  }

  const { conversationId } = await context.params;
  const body = await readJsonBody(request);
  return proxyChatJson({
    path: `/api/v1/chat/conversations/${encodeURIComponent(conversationId)}`,
    method: "PATCH",
    ownerEmail: owner.email,
    body,
    signal: request.signal,
  });
}

/** DELETE /api/chat/conversations/:id */
export async function DELETE(
  request: Request,
  context: RouteContext,
): Promise<Response> {
  const owner = await resolveChatOwner();
  if (!owner) {
    return unauthorizedJson();
  }

  const { conversationId } = await context.params;
  const body = await readJsonBody(request);
  return proxyChatJson({
    path: `/api/v1/chat/conversations/${encodeURIComponent(conversationId)}`,
    method: "DELETE",
    ownerEmail: owner.email,
    body,
    signal: request.signal,
  });
}
