/**
 * @file resumeHttpNetwork.test.ts
 * @description resumeHttp network paths against the real base layer (the
 * sibling resumeHttp.test.ts mocks `request()`; this file exercises the
 * multipart upload, raw-file text, and the analyze SSE stream for real):
 * timeout / connection failure mapping, envelope errors, and the
 * done/error/no-done stream outcomes.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import { resumeHttp } from "../api/resumeHttp";

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

describe("multipart uploads", () => {
  it("uploads a resume as multipart form-data and parses the response", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ id: 1, filename: "a.pdf" })));
    vi.stubGlobal("fetch", fetchMock);

    const file = new File(["pdf-bytes"], "a.pdf", { type: "application/pdf" });
    const result = await resumeHttp.uploadResume(file);

    expect(result).toEqual({ id: 1, filename: "a.pdf" });
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`${BACKEND}/api/v1/resume/upload`);
    expect(init.method).toBe("POST");
    expect(init.credentials).toBe("include");
    expect(init.body).toBeInstanceOf(FormData);
    expect((init.body as FormData).get("file")).toBe(file);
  });

  it("uploads versions to the resume-scoped path", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ id: 2, filename: "b.pdf" })));
    vi.stubGlobal("fetch", fetchMock);

    await resumeHttp.uploadVersion(2, new File(["x"], "b.pdf"));
    const [url] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`${BACKEND}/api/v1/resume/2/versions`);
  });

  it("surfaces structured errors from a rejected upload", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ error: { code: "A1002", message: "too large" } }), {
          status: 413,
        }),
      ),
    );
    await expect(resumeHttp.uploadResume(new File(["x"], "a.pdf"))).rejects.toMatchObject({
      status: 413,
      code: "A1002",
      message: "too large",
    });
  });

  it("maps a failed upload connection to NET0000", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("down")));
    await expect(resumeHttp.uploadResume(new File(["x"], "a.pdf"))).rejects.toMatchObject({
      code: "NET0000",
    });
  });

  it("maps a stalled upload to the upload-timeout copy (NET0001)", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("fetch", hangingFetch());
    const pending = resumeHttp.uploadResume(new File(["x"], "a.pdf"));
    const pendingAssert = expect(pending).rejects.toMatchObject({
      code: "NET0001",
      message: expect.stringContaining("The upload is slow"),
    });
    await vi.advanceTimersByTimeAsync(180_100);
    await pendingAssert;
  });
});

describe("resumeFileText", () => {
  it("returns the raw file text", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response("resume body text")),
    );
    await expect(resumeHttp.resumeFileText(4)).resolves.toBe("resume body text");
    const [url] = vi.mocked(fetch).mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`${BACKEND}/api/v1/resume/4/file`);
  });

  it("propagates envelope errors and connection failures", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "gone" }), { status: 404 }),
      ),
    );
    await expect(resumeHttp.resumeFileText(4)).rejects.toMatchObject({ status: 404 });

    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("down")));
    await expect(resumeHttp.resumeFileText(4)).rejects.toMatchObject({ code: "NET0000" });
  });
});

describe("analyzeResumeStream", () => {
  const analysis = { score: 62, verdict: { summary: "ok" } };

  it("resolves with the analysis from the done event and forwards events", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        sseResponse([
          { type: "plan", steps: [{ id: "s1", title: "read" }] },
          { type: "done", analysis },
        ]),
      ),
    );
    const events: unknown[] = [];
    await expect(
      resumeHttp.analyzeResumeStream(9, (e) => events.push(e)),
    ).resolves.toEqual(analysis);
    expect(events).toHaveLength(2);
  });

  it("throws with the event code when the stream reports an error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        sseResponse([{ type: "error", message: "model exploded", code: "B0002", retryable: true }]),
      ),
    );
    await expect(resumeHttp.analyzeResumeStream(9)).rejects.toMatchObject({
      code: "B0002",
      message: "model exploded",
      retryable: true,
    });
  });

  it("throws NET0003 when the stream ends without a done event", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(sseResponse([{ type: "plan", steps: [] }])),
    );
    await expect(resumeHttp.analyzeResumeStream(9)).rejects.toMatchObject({ code: "NET0003" });
  });

  it("propagates non-2xx envelope errors and connection failures", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ error: { code: "A1005", message: "missing" } }), {
          status: 404,
        }),
      ),
    );
    await expect(resumeHttp.analyzeResumeStream(9)).rejects.toMatchObject({
      status: 404,
      code: "A1005",
    });

    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("down")));
    await expect(resumeHttp.analyzeResumeStream(9)).rejects.toMatchObject({ code: "NET0000" });
  });
});

describe("path-only helpers", () => {
  it("builds hydration-safe paths without a host", () => {
    expect(resumeHttp.resumeFilePath(3, true)).toBe("/api/v1/resume/3/file?download=1");
    expect(resumeHttp.resumePageImagePath(3, 2)).toBe("/api/v1/resume/3/pages/2");
  });
});
