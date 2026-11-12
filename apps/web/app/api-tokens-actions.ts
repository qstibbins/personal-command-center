"use server";

import { revalidatePath } from "next/cache";

import { getAllowlistedSession } from "../auth-session";
import { apiAuthHeaders, getApiBaseUrl } from "./api";
import {
  initialCreateApiTokenState,
  type ApiTokenCreated,
  type ApiTokenMetadata,
  type CreateApiTokenState,
} from "./api-tokens-state";

const SETTINGS_PATH = "/settings/api-tokens";

export async function listApiTokensAction(): Promise<{
  tokens: ApiTokenMetadata[] | null;
  error: string | null;
}> {
  const session = await getAllowlistedSession();
  if (!session) {
    return { tokens: null, error: "You must sign in to manage API tokens." };
  }

  try {
    const response = await fetch(`${getApiBaseUrl()}/api/v1/api-tokens`, {
      cache: "no-store",
      headers: apiAuthHeaders(),
    });
    if (!response.ok) {
      return {
        tokens: null,
        error: `Unable to load tokens (HTTP ${response.status}).`,
      };
    }
    const tokens = (await response.json()) as ApiTokenMetadata[];
    return { tokens, error: null };
  } catch {
    return {
      tokens: null,
      error: "Unable to reach the API. Start FastAPI and try again.",
    };
  }
}

export async function createApiTokenAction(
  _previous: CreateApiTokenState,
  formData: FormData,
): Promise<CreateApiTokenState> {
  const label = String(formData.get("label") ?? "");
  const scopeRead = formData.get("scope_read") === "on";
  const scopeWrite = formData.get("scope_write") === "on";
  const values = { label, scopeRead, scopeWrite };

  const session = await getAllowlistedSession();
  const email = session?.user?.email;
  if (!session || !email) {
    return {
      status: "error",
      message: "You must sign in to create API tokens.",
      revealedToken: null,
      values,
    };
  }

  const scopes: string[] = [];
  if (scopeRead) scopes.push("captures:read");
  if (scopeWrite) scopes.push("captures:write");
  if (scopes.length === 0) {
    return {
      status: "error",
      message: "Select at least one scope.",
      revealedToken: null,
      values,
    };
  }
  if (!label.trim()) {
    return {
      status: "error",
      message: "Label is required.",
      revealedToken: null,
      values,
    };
  }

  try {
    const response = await fetch(`${getApiBaseUrl()}/api/v1/api-tokens`, {
      method: "POST",
      headers: apiAuthHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({
        label: label.trim(),
        scopes,
        created_by_email: email,
      }),
    });

    if (!response.ok) {
      return {
        status: "error",
        message: `Token creation failed (HTTP ${response.status}).`,
        revealedToken: null,
        values,
      };
    }

    const created = (await response.json()) as ApiTokenCreated;
    revalidatePath(SETTINGS_PATH);
    return {
      status: "success",
      message:
        "Token created. Copy it now — it will not be shown again.",
      revealedToken: created.token,
      values: initialCreateApiTokenState.values,
    };
  } catch {
    return {
      status: "error",
      message: "Unable to reach the API. Your input was kept; try again.",
      revealedToken: null,
      values,
    };
  }
}

export async function revokeApiTokenAction(tokenId: string): Promise<{
  ok: boolean;
  message: string;
}> {
  const session = await getAllowlistedSession();
  if (!session) {
    return { ok: false, message: "You must sign in to revoke API tokens." };
  }

  try {
    const response = await fetch(
      `${getApiBaseUrl()}/api/v1/api-tokens/${encodeURIComponent(tokenId)}/revoke`,
      {
        method: "POST",
        headers: apiAuthHeaders(),
      },
    );
    if (!response.ok) {
      return {
        ok: false,
        message: `Revocation failed (HTTP ${response.status}).`,
      };
    }
    revalidatePath(SETTINGS_PATH);
    return { ok: true, message: "Token revoked." };
  } catch {
    return {
      ok: false,
      message: "Unable to reach the API. Try again.",
    };
  }
}
