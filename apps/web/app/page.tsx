import Link from "next/link";
import { redirect } from "next/navigation";

import { apiAuthHeaders, getApiBaseUrl } from "./api";
import { signOutAction } from "./auth-actions";
import { CaptureForm } from "./capture-form";
import { SignOutButton } from "./sign-out-button";
import { getAllowlistedSession } from "../auth-session";

export const dynamic = "force-dynamic";

type Health = {
  status: string;
  service: string;
};

type Capture = {
  id: string;
  source_type: string;
  title: string | null;
  content: string;
  status: string;
  created_at: string;
};

async function getHealth(): Promise<Health | null> {
  try {
    // Health is intentionally unauthenticated (ADR 0003 / Milestone 3.2).
    const response = await fetch(`${getApiBaseUrl()}/api/v1/health`, {
      cache: "no-store",
    });
    if (!response.ok) return null;
    return (await response.json()) as Health;
  } catch {
    return null;
  }
}

async function getCaptures(): Promise<Capture[] | null> {
  try {
    const response = await fetch(`${getApiBaseUrl()}/api/v1/captures`, {
      cache: "no-store",
      headers: apiAuthHeaders(),
    });
    if (!response.ok) return null;
    return (await response.json()) as Capture[];
  } catch {
    return null;
  }
}

export default async function Home() {
  const session = await getAllowlistedSession();
  if (!session) {
    redirect("/signin");
  }

  const [health, captures] = await Promise.all([getHealth(), getCaptures()]);
  const email = session.user?.email ?? "signed in";

  return (
    <main>
      <header className="top-bar">
        <p className="eyebrow">PERSONAL COMMAND CENTER · V0.1</p>
        <div className="session-meta">
          <Link href="/settings/api-tokens">API tokens</Link>
          <span className="muted">{email}</span>
          <SignOutButton signOutAction={signOutAction} />
        </div>
      </header>
      <h1>From capture to action.</h1>
      <p className="intro">
        A foundation for your Second Brain, Chief of Staff,
        and execution workflows.
      </p>

      <section className="panel">
        <h2>Quick Capture</h2>

        <CaptureForm />
      </section>

      <section className="panel inbox">
        <h2>Inbox</h2>

        {captures === null ? (
          <p className="muted">
            Unable to load captures. Check that FastAPI is running.
          </p>
        ) : captures.length === 0 ? (
          <p className="muted">No captures yet. Add your first one above.</p>
        ) : (
          <div className="capture-list">
            {captures.map((capture) => (
              <article key={capture.id}>
                <div className="capture-meta">
                  <span>{capture.source_type.toUpperCase()}</span>
                  <span>{capture.status}</span>
                  <time dateTime={capture.created_at}>
                    {new Date(capture.created_at).toLocaleString("en-US")}
                  </time>
                </div>

                <h3>{capture.title || "Untitled capture"}</h3>
                <p>{capture.content}</p>
              </article>
            ))}
          </div>
        )}
      </section>

      <section className="panel system-status">
        <h2>System status</h2>
        <p>
          FastAPI:{" "}
          <strong>
            {health?.status === "ok" ? "Connected" : "Not reachable"}
          </strong>
        </p>
        <p className="muted">
          {health
            ? `Service: ${health.service}`
            : "Start the API at localhost:8000, then refresh."}
        </p>
      </section>
    </main>
  );
}
