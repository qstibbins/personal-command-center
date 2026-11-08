type Health = { status: string; service: string };

async function getHealth(): Promise<Health | null> {
  try {
    const response = await fetch(`${process.env.API_INTERNAL_URL ?? "http://localhost:8000"}/api/v1/health`, { cache: "no-store" });
    if (!response.ok) return null;
    return (await response.json()) as Health;
  } catch { return null; }
}

export default async function Home() {
  const health = await getHealth();
  return <main>
    <p className="eyebrow">PERSONAL COMMAND CENTER · V0.1</p>
    <h1>From capture to action.</h1>
    <p className="intro">A foundation for your Second Brain, Chief of Staff, and execution workflows.</p>
    <section className="panel"><h2>System status</h2>
      <p>FastAPI: <strong>{health?.status === "ok" ? "Connected" : "Not reachable"}</strong></p>
      <p className="muted">{health ? `Service: ${health.service}` : "Start the API at localhost:8000, then refresh."}</p>
    </section>
    <section className="cards">
      <article><h3>Capture</h3><p>Coming next: text, links, and file uploads.</p></article>
      <article><h3>Knowledge</h3><p>Coming next: source-grounded retrieval.</p></article>
      <article><h3>Execution</h3><p>Coming next: tasks, Kanban, and focus sessions.</p></article>
    </section>
  </main>;
}
