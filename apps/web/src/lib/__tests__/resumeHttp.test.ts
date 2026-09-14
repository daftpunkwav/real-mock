/**
 * @file resumeHttp.test.ts
 * @description resumeHttp: empty-body guards, `/v1` JSON paths, file URL helpers.
 *
 * `request()` prefixes `/api` itself, so JSON methods must pass `/v1/...`.
 * Multipart / `<img>` helpers pass `/api/v1/...` to `resolveBackendUrl`.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import { resumeHttp } from "../api/resumeHttp";

const requestMock = vi.hoisted(() => vi.fn());
const getLocaleMock = vi.hoisted(() => vi.fn(() => "en"));

vi.mock("../api/base", () => ({
  ANALYZE_TIMEOUT_MS: 480_000,
  ApiError: class ApiError extends Error {
    status: number;
    code?: string;
    constructor(message: string, status: number, extra?: { code?: string }) {
      super(message);
      this.status = status;
      this.code = extra?.code;
    }
  },
  consumeSSE: vi.fn(),
  request: requestMock,
  resolveBackendUrl: (path: string) => `http://backend${path}`,
}));

vi.mock("@/i18n/resolve", () => ({
  getLocale: getLocaleMock,
}));

afterEach(() => {
  requestMock.mockReset();
});

describe("resumeHttp empty-body guards", () => {
  it("listResumes throws on empty response body", async () => {
    requestMock.mockResolvedValueOnce(undefined);
    await expect(resumeHttp.listResumes()).rejects.toThrow("empty response");
  });

  it("activateResume throws on empty response body", async () => {
    requestMock.mockResolvedValueOnce(undefined);
    await expect(resumeHttp.activateResume(1)).rejects.toThrow("empty response");
  });

  it("getLimits / analyzeResume / deleteResume / resumePagesMeta throw on null body", async () => {
    requestMock.mockResolvedValue(null);
    await expect(resumeHttp.getLimits()).rejects.toThrow("empty response");
    await expect(resumeHttp.analyzeResume(1)).rejects.toThrow("empty response");
    await expect(resumeHttp.deleteResume(1)).rejects.toThrow("empty response");
    await expect(resumeHttp.resumePagesMeta(1)).rejects.toThrow("empty response");
  });

  it("passes through a normal list body", async () => {
    const body = [{ id: 1, filename: "a.pdf" }];
    requestMock.mockResolvedValueOnce(body);
    await expect(resumeHttp.listResumes()).resolves.toBe(body);
  });

  it("passes through activate / delete / pages / limits bodies", async () => {
    const row = { id: 2, filename: "b.pdf" };
    requestMock.mockResolvedValueOnce(row);
    await expect(resumeHttp.activateResume(2)).resolves.toBe(row);

    const deleted = { ok: true, id: 2 };
    requestMock.mockResolvedValueOnce(deleted);
    await expect(resumeHttp.deleteResume(2)).resolves.toBe(deleted);

    const pages = { pages: 3 };
    requestMock.mockResolvedValueOnce(pages);
    await expect(resumeHttp.resumePagesMeta(2)).resolves.toBe(pages);

    const limits = { max_parallel_analyze: 3 };
    requestMock.mockResolvedValueOnce(limits);
    await expect(resumeHttp.getLimits()).resolves.toBe(limits);
  });

  it("resumeFileUrl toggles the download query", () => {
    expect(resumeHttp.resumeFileUrl(3)).toBe("http://backend/api/v1/resume/3/file");
    expect(resumeHttp.resumeFileUrl(3, true)).toBe("http://backend/api/v1/resume/3/file?download=1");
  });

  it("resumePageImageUrl uses the full /api/v1 path", () => {
    expect(resumeHttp.resumePageImageUrl(3, 2)).toBe("http://backend/api/v1/resume/3/pages/2");
  });

  it("getLimits throws on empty response body", async () => {
    requestMock.mockResolvedValueOnce(undefined);
    await expect(resumeHttp.getLimits()).rejects.toThrow("empty response");
  });

  it("JSON methods call request() with /v1 paths, not /api/v1", async () => {
    requestMock.mockResolvedValue({});
    await resumeHttp.listResumes();
    await resumeHttp.getLimits();
    await resumeHttp.activateResume(1);
    await resumeHttp.deleteResume(1);
    await resumeHttp.resumePagesMeta(1);
    expect(requestMock.mock.calls.map((call) => call[0])).toEqual([
      "/v1/resume/list",
      "/v1/resume/limits",
      "/v1/resume/1/activate",
      "/v1/resume/1",
      "/v1/resume/1/pages",
    ]);
  });

  it("analyzeResume posts the current locale", async () => {
    getLocaleMock.mockReturnValueOnce("zh-CN");
    requestMock.mockResolvedValueOnce({ score: 1 });
    await resumeHttp.analyzeResume(9);
    expect(requestMock).toHaveBeenCalledWith(
      "/v1/resume/9/analyze",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ locale: "zh-CN" }),
      }),
    );
  });

  it("analyzeResume throws on empty response body", async () => {
    requestMock.mockResolvedValueOnce(undefined);
    await expect(resumeHttp.analyzeResume(1)).rejects.toThrow("empty response");
  });

  it("deleteResume throws on empty response body", async () => {
    requestMock.mockResolvedValueOnce(undefined);
    await expect(resumeHttp.deleteResume(1)).rejects.toThrow("empty response");
  });

  it("resumePagesMeta throws on empty response body", async () => {
    requestMock.mockResolvedValueOnce(undefined);
    await expect(resumeHttp.resumePagesMeta(1)).rejects.toThrow("empty response");
  });
});
