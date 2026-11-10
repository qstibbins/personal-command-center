"use server";

import { revalidatePath } from "next/cache";

const API_URL = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

export async function createCapture(formData: FormData) {
  const source_type = String(formData.get("source_type") ?? "");
  const title = String(formData.get("title") ?? "").trim();
  const content = String(formData.get("content") ?? "").trim();

  if (!content) {
    throw new Error("Capture content cannot be empty.");
  }

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
    throw new Error(`Capture failed: HTTP ${response.status}`);
  }

  revalidatePath("/");
}
