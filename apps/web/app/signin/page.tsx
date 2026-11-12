import { redirect } from "next/navigation";

import { signIn } from "../../auth";
import { getAllowlistedSession } from "../../auth-session";

export const dynamic = "force-dynamic";

type SignInPageProps = {
  searchParams: Promise<{ error?: string; callbackUrl?: string }>;
};

function errorMessage(code: string | undefined): string | null {
  if (!code) return null;
  switch (code) {
    case "AccessDenied":
      return "That Google account is not authorized for Personal Command Center.";
    case "Configuration":
      return "Sign-in is misconfigured. Check AUTH_SECRET and Google OAuth settings.";
    case "OAuthAccountNotLinked":
      return "This Google account could not be linked. Contact the owner.";
    default:
      return "Sign-in failed. Try again, or use the allowlisted Google account.";
  }
}

export default async function SignInPage({ searchParams }: SignInPageProps) {
  const session = await getAllowlistedSession();
  if (session) {
    redirect("/");
  }

  const params = await searchParams;
  const message = errorMessage(params.error);

  return (
    <main>
      <p className="eyebrow">PERSONAL COMMAND CENTER · V0.1</p>
      <h1>Sign in</h1>
      <p className="intro">
        Access is limited to an allowlisted Google account.
      </p>

      <section className="panel">
        {message ? <p className="form-message form-error">{message}</p> : null}

        <form
          action={async () => {
            "use server";
            await signIn("google", { redirectTo: "/" });
          }}
        >
          <button type="submit">Sign in with Google</button>
        </form>

        <p className="muted" style={{ marginTop: 16 }}>
          Use the Google account configured in{" "}
          <code>PCC_ALLOWED_GOOGLE_EMAILS</code>. Other accounts are denied.
        </p>
      </section>
    </main>
  );
}
