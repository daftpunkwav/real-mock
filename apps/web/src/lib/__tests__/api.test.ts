/**
 * ApiError unit tests: structured fields (code/hint/traceId/retryable) + fallback codes.
 *
 * Covers the frontend side of the E6 error-code contract:
 * - network failure / timeout with status=0 -> NET0000
 * - backend envelope error.code passthrough
 * - missing code falls back to http_{status}
 */

import { afterEach, describe, expect, it } from "vitest";

import { setCurrentLocale } from "@/i18n/resolve";
import { ApiError, consumeSSE, formatApiError } from "../api/base";

describe("ApiError", () => {
  it("falls back to http_{status} code when fields are omitted", () => {
    const e = new ApiError("not found", 404);
    expect(e.status).toBe(404);
    expect(e.code).toBe("http_404");
    expect(e.message).toBe("not found");
    expect(e.hint).toBe("");
    expect(e.traceId).toBe("");
    expect(e.retryable).toBe(false);
  });

  it("defaults status=0 network failures to NET0000", () => {
    const e = new ApiError("unreachable", 0);
    expect(e.code).toBe("NET0000");
  });

  it("passes through code/hint/traceId/retryable from fields", () => {
    const e = new ApiError("LLM unavailable", 502, {
      code: "C0001",
      hint: "Check Key and network",
      traceId: "req-abc123",
      retryable: true,
    });
    expect(e.code).toBe("C0001");
    expect(e.hint).toBe("Check Key and network");
    expect(e.traceId).toBe("req-abc123");
    expect(e.retryable).toBe(true);
  });

  it("fills omitted field defaults", () => {
    const e = new ApiError("rate limit", 429, { code: "A0002" });
    expect(e.code).toBe("A0002");
    expect(e.retryable).toBe(false);
    expect(e.hint).toBe("");
    expect(e.traceId).toBe("");
  });

  it("prefers an explicit code even when status=0", () => {
    // Design: caller-supplied code wins (even with status=0)
    const e = new ApiError("custom network err", 0, { code: "B0001" });
    expect(e.code).toBe("B0001");
  });

  it("sets name to ApiError for type guards", () => {
    const e = new ApiError("x", 500);
    expect(e.name).toBe("ApiError");
    expect(e instanceof Error).toBe(true);
    expect(e instanceof ApiError).toBe(true);
  });

  it("can be thrown and caught normally", () => {
    expect(() => {
      throw new ApiError("boom", 500, { code: "B0001" });
    }).toThrowError(ApiError);
  });
});

describe("formatApiError", () => {
  afterEach(() => {
    setCurrentLocale("en");
  });

  it("localizes when code hits the catalog (catalog wins over server message)", () => {
    setCurrentLocale("en");
    const e = new ApiError("LLM unavailable", 502, {
      code: "C0001",
      hint: "Check Key",
    });
    expect(formatApiError(e)).toBe(
      "[C0001] AI service temporarily unavailable, please try again later\nCheck the API Key quota and network; if it persists, test connectivity in Settings",
    );
  });

  it("localizes http_{status} fallback codes", () => {
    setCurrentLocale("en");
    const e = new ApiError("not found", 404);
    expect(formatApiError(e)).toBe(
      "[http_404] The requested resource does not exist\nCheck the address or return to the list page and refresh",
    );
  });

  it("falls back to Error.message for non-ApiError", () => {
    expect(formatApiError(new Error("boom"))).toBe("boom");
    expect(formatApiError("string err")).toBe("string err");
  });

  it("falls back to server message/hint for unregistered codes", () => {
    const e = new ApiError("custom message", 400, {
      code: "X9999",
      hint: "custom hint",
    });
    expect(formatApiError(e)).toBe("[X9999] custom message\ncustom hint");
  });

  it("emits Chinese copy when locale is zh-CN", () => {
    setCurrentLocale("zh-CN");
    const e = new ApiError("any", 404, { code: "A1005" });
    expect(formatApiError(e)).toBe(
      "[A1005] 简历不存在\n简历可能已被删除，请刷新列表",
    );
  });

  it("falls back to server message when catalog has placeholders but no params", () => {
    setCurrentLocale("en");
    const e = new ApiError("Text too long: 5000", 400, { code: "A0003" });
    expect(formatApiError(e)).toBe(
      "[A0003] Text too long: 5000\nSplit the text into parts or shorten it",
    );
  });
});

function sseResponse(chunks: string[]): Response {
  const encoder = new TextEncoder();
  let i = 0;
  const stream = new ReadableStream<Uint8Array>({
    pull(controller) {
      if (i < chunks.length) {
        controller.enqueue(encoder.encode(chunks[i]));
        i += 1;
      } else {
        controller.close();
      }
    },
  });
  return new Response(stream);
}

describe("consumeSSE", () => {
  it("flushes a final data line without a trailing newline", async () => {
    const events: { type: string; content?: string }[] = [];
    const res = sseResponse([
      'data: {"type":"token","content":"hello"}\n',
      'data: {"type":"done","content":"ok"}',
    ]);
    await consumeSSE(res, (event) => {
      events.push(event);
    });
    expect(events).toEqual([
      { type: "token", content: "hello" },
      { type: "done", content: "ok" },
    ]);
  });

  it("skips malformed JSON lines and continues", async () => {
    const events: { type: string }[] = [];
    const res = sseResponse(['data: not-json\ndata: {"type":"token"}\n']);
    await consumeSSE(res, (event) => {
      events.push(event);
    });
    expect(events).toEqual([{ type: "token" }]);
  });

  it("reports heartbeat comments and data reads as keepalive", async () => {
    const events: { type: string }[] = [];
    let keepAlive = 0;
    const res = sseResponse([
      ': ping\n\ndata: {"type":"token"}\n',
      ': ping\n',
    ]);
    await consumeSSE(
      res,
      (event) => {
        events.push(event);
      },
      () => {
        keepAlive += 1;
      },
    );
    expect(events).toEqual([{ type: "token" }]);
    expect(keepAlive).toBe(2);
  });
});
