/**
 * @file apiErrorParse.test.ts
 * @description `parseStructuredErrorResponse` branch coverage: unified error
 * envelope, FastAPI `detail` shapes (string / array / object), plain `message`,
 * empty bodies, and the raw-text fallback with truncation.
 */

import { describe, expect, it } from "vitest";

import { ApiError, isRequestAborted, parseStructuredErrorResponse } from "../api/apiError";

function jsonResponse(body: string, status = 400): Response {
  return new Response(body, { status });
}

describe("parseStructuredErrorResponse", () => {
  it("parses the unified error envelope including all optional fields", async () => {
    const parsed = await parseStructuredErrorResponse(
      jsonResponse(
        JSON.stringify({
          error: {
            code: "C0001",
            message: "LLM unavailable",
            hint: "check key",
            trace_id: "req-9",
            retryable: true,
            params: { seconds: 30 },
          },
        }),
        502,
      ),
    );
    expect(parsed).toEqual({
      message: "LLM unavailable",
      code: "C0001",
      hint: "check key",
      traceId: "req-9",
      retryable: true,
      params: { seconds: 30 },
    });
  });

  it("keeps envelope fields absent when the server omits them", async () => {
    const parsed = await parseStructuredErrorResponse(
      jsonResponse(JSON.stringify({ error: { message: "boom" } })),
    );
    expect(parsed).toEqual({ message: "boom" });
  });

  it("uses a string detail as the message", async () => {
    const parsed = await parseStructuredErrorResponse(
      jsonResponse(JSON.stringify({ detail: "Not authenticated" })),
    );
    expect(parsed).toEqual({ message: "Not authenticated" });
  });

  it("joins a FastAPI validation array (objects with msg, then scalars)", async () => {
    const parsed = await parseStructuredErrorResponse(
      jsonResponse(
        JSON.stringify({
          detail: [{ msg: "field required" }, { msg: "invalid email" }, "plain"],
        }),
      ),
    );
    expect(parsed.message).toBe("field required; invalid email; plain");
  });

  it("stringifies a non-string non-array detail", async () => {
    const parsed = await parseStructuredErrorResponse(
      jsonResponse(JSON.stringify({ detail: { reason: "weird" } })),
    );
    expect(parsed.message).toBe(JSON.stringify({ reason: "weird" }));
  });

  it("falls back to the message field", async () => {
    const parsed = await parseStructuredErrorResponse(
      jsonResponse(JSON.stringify({ message: "plain message" })),
    );
    expect(parsed).toEqual({ message: "plain message" });
  });

  it("localizes an empty body with the status", async () => {
    const parsed = await parseStructuredErrorResponse(jsonResponse("", 404));
    expect(parsed.message).toBe("Request failed: 404");
  });

  it("falls back to raw text for non-JSON bodies", async () => {
    const parsed = await parseStructuredErrorResponse(jsonResponse("<html>boom</html>", 500));
    expect(parsed).toEqual({ message: "<html>boom</html>" });
  });

  it("truncates raw text beyond 300 chars with an ellipsis", async () => {
    const long = "x".repeat(400);
    const parsed = await parseStructuredErrorResponse(jsonResponse(long, 500));
    expect(parsed.message).toBe(`${"x".repeat(300)}…`);
  });
});

describe("isRequestAborted", () => {
  it("is true only for ApiError with the NET0002 code", () => {
    expect(isRequestAborted(new ApiError("cancelled", 0, { code: "NET0002" }))).toBe(true);
    expect(isRequestAborted(new ApiError("network", 0, { code: "NET0000" }))).toBe(false);
    expect(isRequestAborted(new Error("nope"))).toBe(false);
    expect(isRequestAborted(Object.assign(new Error("x"), { code: "NET0002" }))).toBe(false);
  });
});
