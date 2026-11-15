import { describe, expect, it, vi } from "vitest";

import { consumeSseStream, createSseParser, parseSseBlock } from "./chat-sse";

describe("parseSseBlock", () => {
  it("parses message_start / content_delta / message_end", () => {
    expect(
      parseSseBlock(
        'event: message_start\ndata: {"run_id":"r1","message_id":"m1","role":"assistant"}',
      ),
    ).toEqual({
      event: "message_start",
      data: { run_id: "r1", message_id: "m1", role: "assistant" },
    });

    expect(
      parseSseBlock('event: content_delta\ndata: {"message_id":"m1","delta":"Hi"}'),
    ).toEqual({
      event: "content_delta",
      data: { message_id: "m1", delta: "Hi" },
    });

    expect(
      parseSseBlock(
        'event: message_end\ndata: {"message_id":"m1","status":"complete","finish_reason":"stop"}',
      ),
    ).toEqual({
      event: "message_end",
      data: { message_id: "m1", status: "complete", finish_reason: "stop" },
    });
  });

  it("parses error events with partial flag", () => {
    expect(
      parseSseBlock(
        'event: error\ndata: {"message_id":"m1","code":"cancelled","message":"Stopped","partial":true}',
      ),
    ).toEqual({
      event: "error",
      data: {
        message_id: "m1",
        code: "cancelled",
        message: "Stopped",
        partial: true,
      },
    });
  });
});

describe("createSseParser", () => {
  it("yields events incrementally across chunk boundaries", () => {
    const parser = createSseParser();
    expect(parser.push("event: content_delta\ndata: {\"message_id\":\"m1\",\"del")).toEqual(
      [],
    );
    const events = parser.push("ta\":\"Hel\"}\n\nevent: content_delta\ndata: {\"message_id\":\"m1\",\"delta\":\"lo\"}\n\n");
    expect(events).toHaveLength(2);
    expect(events[0]).toMatchObject({
      event: "content_delta",
      data: { delta: "Hel" },
    });
    expect(events[1]).toMatchObject({
      event: "content_delta",
      data: { delta: "lo" },
    });
  });
});

describe("consumeSseStream", () => {
  it("invokes onEvent for each SSE event in the body", async () => {
    const text =
      'event: message_start\ndata: {"run_id":"r1","message_id":"m1"}\n\n' +
      'event: content_delta\ndata: {"message_id":"m1","delta":"A"}\n\n' +
      'event: message_end\ndata: {"message_id":"m1","status":"complete"}\n\n';
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new TextEncoder().encode(text));
        controller.close();
      },
    });
    const onEvent = vi.fn();
    const outcome = await consumeSseStream(stream, onEvent);
    expect(outcome).toBe("completed");
    expect(onEvent).toHaveBeenCalledTimes(3);
    expect(onEvent.mock.calls[1]?.[0]).toMatchObject({
      event: "content_delta",
      data: { delta: "A" },
    });
  });
});
