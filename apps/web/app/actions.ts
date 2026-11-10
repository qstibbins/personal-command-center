"use server";

import { revalidatePath } from "next/cache";

import { initialCaptureState, type CaptureFormState } from "./capture-state";

const API_URL = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

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
    const response = await fetch(`${API_URL}/api/v1/captures`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        source_type,
        title: title || null,
        content,
      }),
    });

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
