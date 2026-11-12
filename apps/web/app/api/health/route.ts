/**
 * Unauthenticated liveness probe for Render web-service healthCheckPath.
 * Does not touch Auth.js, Postgres, or FastAPI — process-up only.
 */
export const dynamic = "force-dynamic";

export function GET(): Response {
  return Response.json(
    { status: "ok", service: "pcc-web" },
    {
      status: 200,
      headers: {
        "Cache-Control": "no-store",
      },
    },
  );
}
