"use client";

import { useActionState } from "react";

import {
  createApiTokenAction,
} from "./api-tokens-actions";
import {
  initialCreateApiTokenState,
  type CreateApiTokenState,
} from "./api-tokens-state";

export function ApiTokenCreateForm() {
  const [state, formAction, pending] = useActionState<
    CreateApiTokenState,
    FormData
  >(createApiTokenAction, initialCreateApiTokenState);

  return (
    <div>
      <form className="capture-form" action={formAction}>
        <label htmlFor="token-label">Label</label>
        <input
          id="token-label"
          name="label"
          type="text"
          maxLength={100}
          required
          defaultValue={state.values.label}
          placeholder="e.g. ChatGPT integration (future)"
        />

        <fieldset className="scope-fieldset">
          <legend>Scopes</legend>
          <label className="scope-option">
            <input
              type="checkbox"
              name="scope_read"
              defaultChecked={state.values.scopeRead}
            />
            captures:read — list captures
          </label>
          <label className="scope-option">
            <input
              type="checkbox"
              name="scope_write"
              defaultChecked={state.values.scopeWrite}
            />
            captures:write — create captures
          </label>
        </fieldset>

        <button type="submit" disabled={pending}>
          {pending ? "Creating…" : "Create token"}
        </button>
      </form>

      {state.status === "error" ? (
        <p className="form-message form-error" style={{ marginTop: 12 }}>
          {state.message}
        </p>
      ) : null}

      {state.status === "success" && state.revealedToken ? (
        <div className="token-reveal" role="status">
          <p className="form-message form-success">{state.message}</p>
          <label htmlFor="revealed-token">Raw token (copy once)</label>
          <textarea
            id="revealed-token"
            readOnly
            rows={3}
            value={state.revealedToken}
          />
        </div>
      ) : null}
    </div>
  );
}
