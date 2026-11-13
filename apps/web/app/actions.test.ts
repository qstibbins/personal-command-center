import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));
vi.mock("next/cache", () => ({ revalidatePath: vi.fn() }));

const getAllowlistedSessionMock = vi.fn();
vi.mock("../auth-session", () => ({
  getAllowlistedSession: (...args: unknown[]) => getAllowlistedSessionMock(...args),
}));

import { revalidatePath } from "next/cache";

import { createCapture } from "./actions";
import { initialCaptureState } from "./capture-state";

const TEST_SERVICE_CREDENTIAL = "test-web-service-credential-not-for-production";
const ALLOWLISTED_SESSION = {
  user: { email: "owner@example.com", name: "Owner" },
  expires: "2099-01-01T00:00:00.000Z",
};

function makeForm(fields: Record<string, string>) {
  const formData = new FormData();
  for (const [key, value] of Object.entries(fields)) formData.set(key, value);
  return formData;
}

function unprocessable(detail: unknown[]) {
  return { ok: false, status: 422, json: async () => ({ detail }) };
}

describe("createCapture", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    vi.stubGlobal("fetch", fetchMock);
    process.env.PCC_SERVICE_CREDENTIAL = TEST_SERVICE_CREDENTIAL;
    getAllowlistedSessionMock.mockResolvedValue(ALLOWLISTED_SESSION);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    fetchMock.mockReset();
    getAllowlistedSessionMock.mockReset();
    vi.mocked(revalidatePath).mockReset();
    delete process.env.PCC_SERVICE_CREDENTIAL;
    delete process.env.API_INTERNAL_HOSTPORT;
    delete process.env.API_INTERNAL_URL;
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
    const [, init] = fetchMock.mock.calls[0];
    const body = JSON.parse(init.body);
    expect(body).toEqual({ source_type: "text", title: "Idea", content: "Hello" });
    expect(init.headers.Authorization).toBe(`Bearer ${TEST_SERVICE_CREDENTIAL}`);
    expect(JSON.stringify(state)).not.toContain(TEST_SERVICE_CREDENTIAL);
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

  describe("URL captures", () => {
    it("sends the trimmed URL unchanged and resets the form on success", async () => {
      fetchMock.mockResolvedValue({ ok: true, status: 201 });
      const previous = {
        status: "error" as const,
        message: "Please fix the highlighted fields.",
        fieldErrors: { content: "URL must be an absolute http:// or https:// address" },
        values: { source_type: "url", title: "", content: "example.com" },
      };

      const state = await createCapture(
        previous,
        makeForm({ source_type: "url", title: "", content: " https://example.com/a " }),
      );

      expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
        source_type: "url",
        title: null,
        content: "https://example.com/a",
      });
      expect(state).toEqual({
        status: "success",
        message: "Capture saved.",
        values: initialCaptureState.values,
      });
      expect(state.fieldErrors).toBeUndefined();
      expect(revalidatePath).toHaveBeenCalledWith("/");
    });

    it("leaves URL validation to the API", async () => {
      fetchMock.mockResolvedValue(unprocessable([]));

      await createCapture(
        initialCaptureState,
        makeForm({ source_type: "url", title: "", content: "not a url" }),
      );

      expect(fetchMock).toHaveBeenCalledTimes(1);
      expect(JSON.parse(fetchMock.mock.calls[0][1].body).content).toBe("not a url");
    });
  });

  describe("text captures", () => {
    it("passes URL-like text through unchanged and saves it", async () => {
      fetchMock.mockResolvedValue({ ok: true, status: 201 });

      const state = await createCapture(
        initialCaptureState,
        makeForm({ source_type: "text", title: "", content: "ftp://not-checked\n  keep" }),
      );

      expect(state.status).toBe("success");
      expect(state.values).toEqual(initialCaptureState.values);
      expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
        source_type: "text",
        title: null,
        content: "ftp://not-checked\n  keep",
      });
    });
  });

  describe("422 validation errors", () => {
    const raw = {
      source_type: "url",
      title: " My title ",
      content: "  not-a-url  ",
    };

    it("maps a content error to the content field and keeps raw input", async () => {
      fetchMock.mockResolvedValue(
        unprocessable([
          {
            type: "value_error",
            loc: ["body", "content"],
            msg: "Value error, URL must be an absolute http:// or https:// address",
            input: "not-a-url",
          },
        ]),
      );

      const state = await createCapture(initialCaptureState, makeForm(raw));

      expect(state.status).toBe("error");
      expect(state.fieldErrors).toEqual({
        content: "URL must be an absolute http:// or https:// address",
      });
      expect(state.message).toBe("Please fix the highlighted fields.");
      expect(state.values).toEqual(raw);
      expect(revalidatePath).not.toHaveBeenCalled();
    });

    it("maps a title error and keeps the content", async () => {
      fetchMock.mockResolvedValue(
        unprocessable([
          {
            loc: ["body", "title"],
            msg: "String should have at most 300 characters",
          },
        ]),
      );

      const state = await createCapture(initialCaptureState, makeForm(raw));

      expect(state.fieldErrors).toEqual({
        title: "String should have at most 300 characters",
      });
      expect(state.values.content).toBe("  not-a-url  ");
    });

    it("maps multiple errors, keeping the first per field", async () => {
      fetchMock.mockResolvedValue(
        unprocessable([
          { loc: ["body", "title"], msg: "title problem" },
          { loc: ["body", "content"], msg: "Value error, first" },
          { loc: ["body", "content"], msg: "second" },
        ]),
      );

      const state = await createCapture(initialCaptureState, makeForm(raw));

      expect(state.fieldErrors).toEqual({ title: "title problem", content: "first" });
    });

    it("never surfaces echoed input or unknown fields", async () => {
      fetchMock.mockResolvedValue(
        unprocessable([
          { loc: ["body", "content"], msg: "bad", input: "secret", ctx: { a: 1 } },
          { loc: ["body", "other"], msg: "ignored" },
        ]),
      );

      const state = await createCapture(initialCaptureState, makeForm(raw));

      expect(state.fieldErrors).toEqual({ content: "bad" });
      expect(JSON.stringify(state)).not.toContain("secret");
      expect(JSON.stringify(state)).not.toContain("ignored");
    });

    it.each([
      ["a string detail", { detail: "Something internal broke" }],
      ["a body-level error with no field", { detail: [{ loc: ["body"], msg: "oops" }] }],
      ["a non-array detail object", { detail: { stack: "trace" } }],
      ["a missing detail", {}],
      ["a null body", null],
      ["an over-long message", { detail: [{ loc: ["body", "content"], msg: "x".repeat(500) }] }],
    ])("falls back to a generic message for %s", async (_label, body) => {
      fetchMock.mockResolvedValue({ ok: false, status: 422, json: async () => body });

      const state = await createCapture(initialCaptureState, makeForm(raw));

      expect(state.status).toBe("error");
      expect(state.fieldErrors).toBeUndefined();
      expect(state.message).toBe(
        "The capture was rejected. Check your input and try again.",
      );
      expect(state.message).not.toMatch(/internal|trace|oops/);
      expect(state.values).toEqual(raw);
    });

    it("falls back to a generic message when the body is not JSON", async () => {
      fetchMock.mockResolvedValue({
        ok: false,
        status: 422,
        json: async () => {
          throw new SyntaxError("Unexpected token <");
        },
      });

      const state = await createCapture(initialCaptureState, makeForm(raw));

      expect(state.status).toBe("error");
      expect(state.message).not.toContain("Unexpected token");
      expect(state.values).toEqual(raw);
      expect(revalidatePath).not.toHaveBeenCalled();
    });
  });

  it("does not read or leak the body of 5xx responses", async () => {
    const json = vi.fn().mockResolvedValue({ detail: "Traceback: db password" });
    fetchMock.mockResolvedValue({ ok: false, status: 503, json });

    const state = await createCapture(
      initialCaptureState,
      makeForm({ source_type: "text", title: "", content: "keep" }),
    );

    expect(json).not.toHaveBeenCalled();
    expect(state.message).not.toContain("Traceback");
    expect(state.fieldErrors).toBeUndefined();
    expect(state.values.content).toBe("keep");
  });

  it("does not leak the error message when the API is unreachable", async () => {
    fetchMock.mockRejectedValue(new Error("connect ECONNREFUSED 10.0.0.5:8000"));

    const state = await createCapture(
      initialCaptureState,
      makeForm({ source_type: "text", title: "", content: "keep" }),
    );

    expect(state.message).not.toContain("10.0.0.5");
  });

  it("sends the service credential on every API call and never returns it", async () => {
    fetchMock.mockResolvedValue({ ok: true, status: 201 });

    const state = await createCapture(
      initialCaptureState,
      makeForm({ source_type: "text", title: "", content: "secret-safe" }),
    );

    expect(fetchMock.mock.calls[0][1].headers.Authorization).toBe(
      `Bearer ${TEST_SERVICE_CREDENTIAL}`,
    );
    expect(JSON.stringify(state)).not.toContain(TEST_SERVICE_CREDENTIAL);
    expect(JSON.stringify(state)).not.toContain("Authorization");
  });

  it("posts captures through getApiBaseUrl (API_INTERNAL_HOSTPORT wiring)", async () => {
    process.env.API_INTERNAL_HOSTPORT = "pcc-api:10000";
    fetchMock.mockResolvedValue({ ok: true, status: 201 });

    await createCapture(
      initialCaptureState,
      makeForm({ source_type: "text", title: "", content: "hostport path" }),
    );

    expect(fetchMock.mock.calls[0][0]).toBe(
      "http://pcc-api:10000/api/v1/captures",
    );
    delete process.env.API_INTERNAL_HOSTPORT;
  });

  it("fails closed without calling fetch when the service credential is missing", async () => {
    delete process.env.PCC_SERVICE_CREDENTIAL;

    const state = await createCapture(
      initialCaptureState,
      makeForm({ source_type: "text", title: "", content: "keep" }),
    );

    expect(fetchMock).not.toHaveBeenCalled();
    expect(state.status).toBe("error");
    expect(state.values.content).toBe("keep");
    expect(state.message).not.toContain("PCC_SERVICE_CREDENTIAL");
    expect(JSON.stringify(state)).not.toContain(TEST_SERVICE_CREDENTIAL);
  });

  it("rejects unauthenticated Server Action calls without contacting FastAPI", async () => {
    getAllowlistedSessionMock.mockResolvedValue(null);

    const state = await createCapture(
      initialCaptureState,
      makeForm({ source_type: "text", title: "T", content: "secret idea" }),
    );

    expect(fetchMock).not.toHaveBeenCalled();
    expect(state.status).toBe("error");
    expect(state.message).toBe("You must sign in to save captures.");
    expect(state.values.content).toBe("secret idea");
    expect(revalidatePath).not.toHaveBeenCalled();
    expect(JSON.stringify(state)).not.toContain(TEST_SERVICE_CREDENTIAL);
  });

  it("rejects revoked or non-allowlisted sessions without contacting FastAPI", async () => {
    getAllowlistedSessionMock.mockResolvedValue(null);

    const state = await createCapture(
      initialCaptureState,
      makeForm({ source_type: "url", title: "", content: "https://example.com" }),
    );

    expect(fetchMock).not.toHaveBeenCalled();
    expect(state.status).toBe("error");
    expect(state.values.source_type).toBe("url");
  });

  // The form shows state.values.source_type after every action, so this is the
  // contract that keeps the Type select in sync with what was submitted.
  describe("source_type in the returned state", () => {
    const submit = () =>
      createCapture(
        initialCaptureState,
        makeForm({ source_type: "url", title: "T", content: "example.com" }),
      );

    it.each([
      ["a 422 response", () => unprocessable([{ loc: ["body", "content"], msg: "bad" }])],
      ["a generic 422 response", () => unprocessable([])],
      ["a 5xx response", () => ({ ok: false, status: 500 })],
    ])("keeps url after %s", async (_label, makeResponse) => {
      fetchMock.mockResolvedValue(makeResponse());

      expect((await submit()).values.source_type).toBe("url");
    });

    it("keeps url when the API is unreachable", async () => {
      fetchMock.mockRejectedValue(new Error("ECONNREFUSED"));

      expect((await submit()).values.source_type).toBe("url");
    });

    it("keeps url when client-side blank validation fails", async () => {
      const state = await createCapture(
        initialCaptureState,
        makeForm({ source_type: "url", title: "", content: "  " }),
      );

      expect(state.values.source_type).toBe("url");
    });

    it("resets to text only after a successful save", async () => {
      fetchMock.mockResolvedValue({ ok: true, status: 201 });

      const state = await submit();

      expect(state.status).toBe("success");
      expect(state.values.source_type).toBe("text");
    });

    it("submits exactly the selected type", async () => {
      fetchMock.mockResolvedValue({ ok: true, status: 201 });

      await createCapture(
        initialCaptureState,
        makeForm({ source_type: "url", title: "", content: "https://example.com" }),
      );

      expect(JSON.parse(fetchMock.mock.calls[0][1].body).source_type).toBe("url");
    });
  });
});
