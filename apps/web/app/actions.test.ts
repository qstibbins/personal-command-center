import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/cache", () => ({ revalidatePath: vi.fn() }));

import { revalidatePath } from "next/cache";

import { createCapture } from "./actions";
import { initialCaptureState } from "./capture-state";

function makeForm(fields: Record<string, string>) {
  const formData = new FormData();
  for (const [key, value] of Object.entries(fields)) formData.set(key, value);
  return formData;
}

describe("createCapture", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    fetchMock.mockReset();
    vi.mocked(revalidatePath).mockReset();
  });

  it("returns success with cleared values and revalidates when saved", async () => {
    fetchMock.mockResolvedValue({ ok: true, status: 201 });

    const state = await createCapture(
      initialCaptureState,
      makeForm({ source_type: "text", title: " Idea ", content: " Hello " }),
    );

    expect(state.status).toBe("success");
    expect(state.values).toEqual(initialCaptureState.values);
    expect(revalidatePath).toHaveBeenCalledWith("/");
    const body = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(body).toEqual({ source_type: "text", title: "Idea", content: "Hello" });
  });

  it("preserves input and does not revalidate on HTTP failure", async () => {
    fetchMock.mockResolvedValue({ ok: false, status: 500 });

    const state = await createCapture(
      initialCaptureState,
      makeForm({ source_type: "url", title: "T", content: "https://x.dev" }),
    );

    expect(state.status).toBe("error");
    expect(state.message).toContain("HTTP 500");
    expect(state.values).toEqual({
      source_type: "url",
      title: "T",
      content: "https://x.dev",
    });
    expect(revalidatePath).not.toHaveBeenCalled();
  });

  it("preserves input when the API is unreachable", async () => {
    fetchMock.mockRejectedValue(new Error("ECONNREFUSED"));

    const state = await createCapture(
      initialCaptureState,
      makeForm({ source_type: "text", title: "", content: "keep me" }),
    );

    expect(state.status).toBe("error");
    expect(state.values.content).toBe("keep me");
    expect(revalidatePath).not.toHaveBeenCalled();
  });

  it("rejects blank content without calling the API", async () => {
    const state = await createCapture(
      initialCaptureState,
      makeForm({ source_type: "text", title: "T", content: "   " }),
    );

    expect(state.status).toBe("error");
    expect(state.values.title).toBe("T");
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
