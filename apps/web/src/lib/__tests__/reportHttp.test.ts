/**
 * @file reportHttp.test.ts
 * @description reportHttp: report GET path, the live SSE generation stream
 * (event pass-through, resolve at stream end), and its failure mapping
 * (non-2xx → NET0005, connection failure → NET0000).
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import { reportHttp } from "../api/reportHttp";

const BACKEND = "http://localhost:8081";

function sseResponse(events: unknown[]): Response {
  const encoder = new TextEncoder();
  const payload = events.map((e) => `data: ${JSON.stringify(e)}\n\n`).join("");
  return new Response(
    new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(encoder.encode(payload));
        controller.close();
      },
    }),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("reportHttp.getReport", () => {
  it("requests the session report through request()", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ status: "ready" })));
    vi.stubGlobal("fetch", fetchMock);
    await expect(reportHttp.getReport(5)).resolves.toEqual({ status: "ready" });
    const [url] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`${BACKEND}/api/v1/reports/5`);
  });
});

describe("reportHttp.streamReport", () => {
  it("emits SSE events and resolves when the stream ends", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      sseResponse([
        { type: "stage", stage: "reading" },
        { type: "token", content: "verdict text" },
        { type: "done", report: { overall: { score: 62 } } },
      ]),
    );
    vi.stubGlobal("fetch", fetchMock);

    const events: unknown[] = [];
    await expect(
      reportHttp.streamReport(7, (e) => events.push(e)),
    ).resolves.toBeUndefined();

    expect(events).toEqual([
      { type: "stage", stage: "reading" },
      { type: "token", content: "verdict text" },
      { type: "done", report: { overall: { score: 62 } } },
    ]);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`${BACKEND}/api/v1/reports/7/stream`);
    expect(init.method).toBe("GET");
    expect(init.credentials).toBe("include");
  });

  it("throws NET0005 when the stream endpoint answers non-2xx", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response("nope", { status: 500 })),
    );
    await expect(reportHttp.streamReport(7, () => {})).rejects.toMatchObject({
      code: "NET0005",
      status: 500,
    });
  });

  it("throws NET0000 when the connection cannot be established", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("down")));
    await expect(reportHttp.streamReport(7, () => {})).rejects.toMatchObject({
      code: "NET0000",
    });
  });
});
