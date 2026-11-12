export type ApiTokenScope = "captures:read" | "captures:write";

export type ApiTokenMetadata = {
  id: string;
  label: string;
  token_prefix: string;
  scopes: string[];
  created_at: string;
  expires_at: string | null;
  revoked_at: string | null;
  created_by_email: string;
};

export type ApiTokenCreated = ApiTokenMetadata & {
  token: string;
};

export type CreateApiTokenState = {
  status: "idle" | "success" | "error";
  message: string;
  /** Raw token shown once after creation; never re-fetched. */
  revealedToken: string | null;
  values: {
    label: string;
    scopeRead: boolean;
    scopeWrite: boolean;
  };
};

export const initialCreateApiTokenState: CreateApiTokenState = {
  status: "idle",
  message: "",
  revealedToken: null,
  values: {
    label: "",
    scopeRead: true,
    scopeWrite: false,
  },
};
