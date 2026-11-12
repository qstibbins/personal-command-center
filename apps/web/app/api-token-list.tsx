"use client";

import { useTransition } from "react";

import { revokeApiTokenAction } from "./api-tokens-actions";
import type { ApiTokenMetadata } from "./api-tokens-state";

type Props = {
  tokens: ApiTokenMetadata[];
};

export function ApiTokenList({ tokens }: Props) {
  const [pending, startTransition] = useTransition();

  if (tokens.length === 0) {
    return <p className="muted">No API tokens yet.</p>;
  }

  return (
    <div className="capture-list">
      {tokens.map((token) => {
        const revoked = Boolean(token.revoked_at);
        return (
          <article key={token.id}>
            <div className="capture-meta">
              <span>{revoked ? "REVOKED" : "ACTIVE"}</span>
              <span>{token.token_prefix}…</span>
              <time dateTime={token.created_at}>
                {new Date(token.created_at).toLocaleString("en-US")}
              </time>
            </div>
            <h3>{token.label}</h3>
            <p>
              Scopes: {token.scopes.join(", ")}
              {token.expires_at
                ? ` · Expires ${new Date(token.expires_at).toLocaleString("en-US")}`
                : " · No expiry"}
            </p>
            {!revoked ? (
              <button
                type="button"
                className="sign-out-button"
                style={{ marginTop: 12 }}
                disabled={pending}
                onClick={() => {
                  startTransition(async () => {
                    await revokeApiTokenAction(token.id);
                  });
                }}
              >
                Revoke
              </button>
            ) : null}
          </article>
        );
      })}
    </div>
  );
}
