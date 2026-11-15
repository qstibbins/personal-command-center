import {
  proxyChatJson,
  readJsonBody,
  resolveChatOwner,
  unauthorizedJson,
} from "../../../bff";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type RouteContext = {
  params: Promise<{ runId: string }>;
};

/** POST /api/chat/runs/:runId/cancel — idempotent stop. */
export async function POST(
  request: Request,
  context: RouteContext,
): Promise<Response> {
  const owner = await resolveChatOwner();
  if (!owner) {
    return unauthorizedJson();
  }

  const { runId } = await context.params;
  const body = await readJsonBody(request);
  return proxyChatJson({
    path: `/api/v1/chat/runs/${encodeURIComponent(runId)}/cancel`,
    method: "POST",
    ownerEmail: owner.email,
    body,
    signal: request.signal,
  });
}
