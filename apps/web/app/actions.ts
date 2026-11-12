"use server";

import { revalidatePath } from "next/cache";

import { apiAuthHeaders, getApiBaseUrl } from "./api";
import {
  initialCaptureState,
  type CaptureFieldErrors,
  type CaptureFormState,
} from "./capture-state";

const REJECTED_MESSAGE =
  "The capture was rejected. Check your input and try again.";
const FIELD_ERRORS_MESSAGE = "Please fix the highlighted fields.";
const MAX_FIELD_ERROR_LENGTH = 200;

// FastAPI 422 bodies look like {detail: [{loc: ["body", "content"], msg}]}.
// Only whitelisted fields and short string messages are surfaced; anything
// else (including echoed input) is dropped.
async function readFieldErrors(
  response: Response,
): Promise<CaptureFieldErrors | null> {
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    return null;
  }

  const detail = (body as { detail?: unknown } | null)?.detail;
  if (!Array.isArray(detail)) return null;

  const fieldErrors: CaptureFieldErrors = {};
  for (const item of detail) {
    const { loc, msg } = (item ?? {}) as { loc?: unknown; msg?: unknown };
    if (!Array.isArray(loc) || loc[0] !== "body" || typeof msg !== "string") {
      continue;
    }
    const field: unknown = loc[loc.length - 1];
    if (field !== "title" && field !== "content") continue;
    const message = msg.replace(/^Value error, /, "").trim();
    if (!message || message.length > MAX_FIELD_ERROR_LENGTH) continue;
    fieldErrors[field] ??= message;
  }

  return Object.keys(fieldErrors).length > 0 ? fieldErrors : null;
}

export async function createCapture(
  _previousState: CaptureFormState,
  formData: FormData,
): Promise<CaptureFormState> {
  const source_type = String(formData.get("source_type") ?? "text");
  const rawTitle = String(formData.get("title") ?? "");
  const rawContent = String(formData.get("content") ?? "");
  const title = rawTitle.trim();
  const content = rawContent.trim();

  // Echo the user's raw input back on failure so the form keeps it.
  const submitted = { source_type, title: rawTitle, content: rawContent };

  if (!content) {
    return {
      status: "error",
      message: "Capture content cannot be empty.",
      values: submitted,
    };
  }

  try {
    const response = await fetch(`${getApiBaseUrl()}/api/v1/captures`, {
      method: "POST",
      headers: apiAuthHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({
        source_type,
        title: title || null,
        content,
      }),
    });

    if (response.status === 422) {
      const fieldErrors = await readFieldErrors(response);
      return {
        status: "error",
        message: fieldErrors ? FIELD_ERRORS_MESSAGE : REJECTED_MESSAGE,
        ...(fieldErrors && { fieldErrors }),
        values: submitted,
      };
    }

    if (!response.ok) {
      return {
        status: "error",
        message: `Capture failed: HTTP ${response.status}. Your input was kept; try again.`,
        values: submitted,
      };
    }
  } catch {
    return {
      status: "error",
      message:
        "Unable to reach the capture service. Your input was kept; try again.",
      values: submitted,
    };
  }

  revalidatePath("/");

  return {
    status: "success",
    message: "Capture saved.",
    values: initialCaptureState.values,
  };
}
