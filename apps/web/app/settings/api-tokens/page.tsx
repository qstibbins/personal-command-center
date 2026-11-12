import Link from "next/link";
import { redirect } from "next/navigation";

import { getAllowlistedSession } from "../../../auth-session";
import { listApiTokensAction } from "../../api-tokens-actions";
import { ApiTokenCreateForm } from "../../api-token-create-form";
import { ApiTokenList } from "../../api-token-list";
import { signOutAction } from "../../auth-actions";
import { SignOutButton } from "../../sign-out-button";

export const dynamic = "force-dynamic";

export default async function ApiTokensSettingsPage() {
  const session = await getAllowlistedSession();
  if (!session) {
    redirect("/signin");
  }

  const { tokens, error } = await listApiTokensAction();
  const email = session.user?.email ?? "signed in";

  return (
    <main>
      <header className="top-bar">
        <p className="eyebrow">PERSONAL COMMAND CENTER · V0.1</p>
        <div className="session-meta">
          <Link href="/">Inbox</Link>
          <span className="muted">{email}</span>
          <SignOutButton signOutAction={signOutAction} />
        </div>
      </header>

      <h1>API tokens</h1>
      <p className="intro">
        Issue scoped, revocable bearer tokens for future non-browser clients.
        The raw token is shown only once at creation.
      </p>

      <section className="panel">
        <h2>Create token</h2>
        <ApiTokenCreateForm />
      </section>

      <section className="panel inbox">
        <h2>Existing tokens</h2>
        {error ? (
          <p className="muted">{error}</p>
        ) : tokens ? (
          <ApiTokenList tokens={tokens} />
        ) : (
          <p className="muted">Unable to load tokens.</p>
        )}
      </section>
    </main>
  );
}
