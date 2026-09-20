/**
 * @file apiRequest.test.ts
 * @description `request()` against the real base layer (only `fetch` is stubbed):
 * URL resolution, header/body pass-through, timeout vs cancel vs network failure,
 * and error-envelope / empty-body / invalid-JSON handling.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, request } from "../api/base";

const BACKEND = "http://localhost:8081";

/** fetch stub that hangs until its AbortSignal fires (for timeout / cancel paths). */
function hangingFetch(): ReturnType<typeof vi.fn> {
  return vi.fn(
    (_url: string, init?: RequestInit) =>
      new Promise<Response>((_resolve, reject) => {
        init?.signal?.addEventListener("abort", () =>
          reject(new DOMException("The operation was aborted.", "AbortError")),
        );
      }),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("request success paths", () => {
  it("posts JSON to STREAM_API_BASE + /api prefix with credentials and parses the body", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ ok: 1 })));
    vi.stubGlobal("fetch", fetchMock);

    const data = await request<{ ok: number }>("/v1/things", {
      method: "POST",
      body: JSON.stringify({ a: 1 }),
      headers: { "X-Custom": "yes" },
    });

    expect(data).toEqual({ ok: 1 });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`${BACKEND}/api/v1/things`);
    expect(init.method).toBe("POST");
    expect(init.credentials).toBe("include");
    expect(init.body).toBe(JSON.stringify({ a: 1 }));
    expect(init.headers).toEqual({ "Content-Type": "application/json", "X-Custom": "yes" });
  });

  it("returns undefined for an empty 200 body", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("")));
    await expect(request("/v1/empty")).resolves.toBeUndefined();
  });
});

describe("request error paths", () => {
  it("throws ApiError from the structured error envelope on non-2xx", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            error: { code: "A1005", message: "resume missing", hint: "refresh", trace_id: "t-1" },
          }),
          { status: 404 },
        ),
      ),
    );
    const err = (await request("/v1/nope").catch((e: unknown) => e)) as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(404);
    expect(err.code).toBe("A1005");
    expect(err.message).toBe("resume missing");
    expect(err.hint).toBe("refresh");
    expect(err.traceId).toBe("t-1");
  });

  it("throws NET0004 on invalid JSON in a 200 body", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("not-json")));
    const err = (await request("/v1/bad").catch((e: unknown) => e)) as ApiError;
    expect(err.code).toBe("NET0004");
  });

  it("maps a rejected fetch to NET0000 with the target URL", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("network down")));
    const err = (await request("/v1/x").catch((e: unknown) => e)) as ApiError;
    expect(err.code).toBe("NET0000");
    expect(err.message).toContain(`${BACKEND}/api/v1/x`);
  });

  it("throws NET0002 synchronously when the external signal is already aborted", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const controller = new AbortController();
    controller.abort();
    const err = (await request("/v1/x", { signal: controller.signal }).catch(
      (e: unknown) => e,
    )) as ApiError;
    expect(err.code).toBe("NET0002");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("maps an external abort mid-flight to NET0002", async () => {
    const fetchMock = hangingFetch();
    vi.stubGlobal("fetch", fetchMock);
    const controller = new AbortController();
    const pending = request("/v1/x", { signal: controller.signal });
    const pendingAssert = expect(pending).rejects.toMatchObject({ code: "NET0002" });
    controller.abort();
    await pendingAssert;
  });
});

describe("request timeout", () => {
  it("maps a timeout to NET0001 with the short-timeout copy", async () => {
    vi.stubGlobal("fetch", hangingFetch());
    vi.useFakeTimers();
    const pending = request("/v1/x", { timeoutMs: 1500 });
    const pendingAssert = expect(pending).rejects.toMatchObject({
      code: "NET0001",
      message: expect.stringContaining("Confirm the backend is running"),
    });
    await vi.advanceTimersByTimeAsync(1600);
    await pendingAssert;
  });

  it("uses the LLM-heavy copy for long budgets", async () => {
    vi.stubGlobal("fetch", hangingFetch());
    vi.useFakeTimers();
    const pending = request("/v1/x", { timeoutMs: 60_000 });
    const pendingAssert = expect(pending).rejects.toMatchObject({
      code: "NET0001",
      message: expect.stringContaining("Deep review and other LLM tasks"),
    });
    await vi.advanceTimersByTimeAsync(60_100);
    await pendingAssert;
  });

  it("keeps the timeout armed through the body read (budget covers the whole request)", async () => {
    // Headers resolve fast, the body stream hangs until abort: the timeout
    // must still fire and surface as NET0001, not as a raw abort.
    vi.useFakeTimers();
    const fetchMock = vi.fn().mockImplementation(
      (_url: string, init?: RequestInit) =>
        new Promise<Response>((resolve) => {
          const stream = new ReadableStream<Uint8Array>({
            start(controller) {
              init?.signal?.addEventListener("abort", () =>
                controller.error(new DOMException("The operation was aborted.", "AbortError")),
              );
            },
          });
          resolve(new Response(stream, { status: 200 }));
        }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const pending = request("/v1/x", { timeoutMs: 1000 });
    const pendingAssert = expect(pending).rejects.toMatchObject({ code: "NET0001" });
    await vi.advanceTimersByTimeAsync(1100);
    await pendingAssert;
  });
});
