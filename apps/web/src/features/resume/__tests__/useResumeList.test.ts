// @vitest-environment jsdom
/**
 * @file useResumeList.test.ts
 * @description Facade tests: initial load, mutations, silent reload, toast contract.
 *
 * Covers:
 * - First load sets preview to the active row; failure writes loadError
 * - Mutation reload uses silent load (page `loading` stays false once ready)
 * - Write success toasts only after the list refresh succeeds
 * - Refresh failure keeps the current list and toasts listRefreshFailed only
 * - Upload ApiError is formatted via formatApiError
 */

import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DEFAULT_LOCALE } from "@/i18n/locales";
import { resume as enResume } from "@/i18n/messages/en/resume";
import { setCurrentLocale } from "@/i18n/resolve";
import { ApiError } from "@/lib/api/base";
import { resumeHttp } from "@/lib/api/clients";

import { useResumeList } from "../useResumeList";
import { MAX_PARALLEL_ANALYZE } from "../resumeLimits";

import { makeResumeResponse } from "./helpers";

afterEach(() => {
  cleanup();
  setCurrentLocale(DEFAULT_LOCALE);
});

const toastSuccess = vi.hoisted(() => vi.fn());
const toastError = vi.hoisted(() => vi.fn());
const toastInfo = vi.hoisted(() => vi.fn());
const toastWarning = vi.hoisted(() => vi.fn());
const toastClear = vi.hoisted(() => vi.fn());

vi.mock("@/lib/api/clients", () => ({
  resumeHttp: {
    listResumes: vi.fn(),
    uploadResume: vi.fn(),
    uploadVersion: vi.fn(),
    retryResumeParse: vi.fn(),
    analyzeResume: vi.fn(),
    analyzeResumeStream: vi.fn(),
    activateResume: vi.fn(),
    deleteResume: vi.fn(),
  },
}));

vi.mock("@/components/Toast", () => ({
  toast: {
    success: toastSuccess,
    error: toastError,
    info: toastInfo,
    warning: toastWarning,
    clear: toastClear,
  },
}));

const listMock = vi.mocked(resumeHttp.listResumes);
const uploadMock = vi.mocked(resumeHttp.uploadResume);
const uploadVersionMock = vi.mocked(resumeHttp.uploadVersion);
const analyzeMock = vi.mocked(resumeHttp.analyzeResumeStream);
const activateMock = vi.mocked(resumeHttp.activateResume);
const deleteMock = vi.mocked(resumeHttp.deleteResume);

const row = makeResumeResponse({ id: 7, filename: "ada.pdf", is_active: true });
const pdf = () => new File(["x"], "cv.pdf", { type: "application/pdf" });

function asUploadEvent(file: File) {
  return { target: { files: [file] } } as unknown as Parameters<
    ReturnType<typeof useResumeList>["handleUpload"]
  >[0];
}

async function renderLoaded() {
  const rendered = renderHook(() => useResumeList());
  await act(async () => {});
  expect(rendered.result.current.loading).toBe(false);
  expect(listMock).toHaveBeenCalledTimes(1);
  return rendered;
}

beforeEach(() => {
  vi.clearAllMocks();
  setCurrentLocale("en");
  listMock.mockResolvedValue([row]);
});

describe("useResumeList", () => {
  it("loads the list and selects the active resume", async () => {
    const { result } = await renderLoaded();
    expect(result.current.resumes).toHaveLength(1);
    expect(result.current.previewId).toBe(7);
    expect(result.current.previewResume?.filename).toBe("ada.pdf");
  });

  it("toasts on upload success and reloads", async () => {
    uploadMock.mockResolvedValue(row);
    const { result } = await renderLoaded();
    await act(async () => {
      await result.current.handleUpload(asUploadEvent(pdf()));
    });
    expect(uploadMock).toHaveBeenCalled();
    expect(toastSuccess).toHaveBeenCalledWith(enResume["toast.uploadQueued"]);
    expect(toastError).not.toHaveBeenCalled();
    expect(listMock).toHaveBeenCalledTimes(2);
  });

  it("toasts parseFailed once the poller observes a failed row", async () => {
    uploadMock.mockResolvedValue(row);
    const failedRow = makeResumeResponse({ id: 9, parse_status: "failed", parse_error: "A1006" });
    const { result } = await renderLoaded();

    await act(async () => {
      await result.current.handleUpload(asUploadEvent(pdf()));
    });
    toastError.mockClear();

    // Simulate a poll reload returning a row that settled as failed.
    await act(async () => {
      listMock.mockResolvedValueOnce([row, failedRow]);
      await result.current.load({ silent: true });
    });
    expect(toastError).toHaveBeenCalledWith(enResume["toast.parseFailed"], { durationMs: 8_000 });

    // Reporting fires once per row, not once per reload.
    await act(async () => {
      await result.current.load({ silent: true });
    });
    expect(toastError).toHaveBeenCalledTimes(1);
  });

  it("blocks analyze beyond the catalog parallel cap", async () => {
    const { result } = await renderLoaded();
    analyzeMock.mockReturnValue(new Promise(() => undefined) as Promise<never>);
    act(() => {
      result.current.handleAnalyze(1);
      result.current.handleAnalyze(2);
      result.current.handleAnalyze(3);
      result.current.handleAnalyze(4);
    });
    expect(analyzeMock).toHaveBeenCalledTimes(MAX_PARALLEL_ANALYZE);
    expect(toastError).toHaveBeenCalled();
  });

  it("activates and deletes with success toasts after the list refresh", async () => {
    activateMock.mockResolvedValue(row);
    deleteMock.mockResolvedValue({ ok: true, id: 7 });
    const { result } = await renderLoaded();
    await act(async () => {
      await result.current.handleActivate(7);
      await result.current.handleDelete(7);
    });
    expect(activateMock).toHaveBeenCalledWith(7);
    expect(deleteMock).toHaveBeenCalledWith(7);
    expect(toastSuccess).toHaveBeenCalledWith(enResume["toast.activated"]);
    expect(toastSuccess).toHaveBeenCalledWith(enResume["toast.deleted"]);
    expect(listMock).toHaveBeenCalledTimes(3);
  });

  it("records loadError when list fails", async () => {
    listMock.mockRejectedValueOnce(new Error("boom"));
    const { result } = await renderLoaded();
    expect(result.current.loadError).toContain("boom");
  });

  it("does not flip page loading while a mutation reloads the list", async () => {
    uploadMock.mockResolvedValue(row);
    const { result } = await renderLoaded();

    let resolveReload: (value: typeof row[]) => void = () => undefined;
    listMock.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveReload = resolve;
        }),
    );

    let finished: Promise<void> = Promise.resolve();
    await act(async () => {
      finished = result.current.handleUpload(asUploadEvent(pdf()));
      await Promise.resolve();
    });
    expect(listMock).toHaveBeenCalledTimes(2);
    expect(result.current.loading).toBe(false);
    expect(result.current.resumes).toHaveLength(1);
    expect(toastSuccess).not.toHaveBeenCalled();

    await act(async () => {
      resolveReload([row]);
      await finished;
    });
    expect(result.current.loading).toBe(false);
    expect(toastSuccess).toHaveBeenCalledWith(enResume["toast.uploadQueued"]);
  });

  it("keeps the list and toasts listRefreshFailed when silent reload fails", async () => {
    uploadMock.mockResolvedValue(row);
    const { result } = await renderLoaded();
    listMock.mockRejectedValueOnce(new Error("reload-fail"));
    await act(async () => {
      await result.current.handleUpload(asUploadEvent(pdf()));
    });
    expect(result.current.loadError).toBe("");
    expect(result.current.loading).toBe(false);
    expect(result.current.resumes).toHaveLength(1);
    expect(toastSuccess).not.toHaveBeenCalled();
    expect(toastError).toHaveBeenCalledWith(enResume["toast.listRefreshFailed"]);
  });

  it("keeps the list when activate refresh fails", async () => {
    activateMock.mockResolvedValue(row);
    const { result } = await renderLoaded();
    listMock.mockRejectedValueOnce(new Error("reload-fail"));
    await act(async () => {
      await result.current.handleActivate(7);
    });
    expect(result.current.loadError).toBe("");
    expect(result.current.resumes).toHaveLength(1);
    expect(toastSuccess).not.toHaveBeenCalled();
    expect(toastError).toHaveBeenCalledWith(enResume["toast.listRefreshFailed"]);
  });

  it("toasts analyzeDone with the response score after a successful refresh", async () => {
    analyzeMock.mockResolvedValue({ score: 88 } as Awaited<ReturnType<typeof resumeHttp.analyzeResume>>);
    const { result } = await renderLoaded();
    act(() => {
      result.current.handleAnalyze(7);
    });
    await waitFor(() => expect(listMock).toHaveBeenCalledTimes(2));
    expect(toastSuccess).toHaveBeenCalledWith(enResume["toast.analyzeDone"].replace("{score}", "88"), {
      durationMs: 8000,
    });
  });

  it("toasts listRefreshFailed when analyze succeeds but list refresh fails", async () => {
    analyzeMock.mockResolvedValue({ score: 88 } as Awaited<ReturnType<typeof resumeHttp.analyzeResume>>);
    const { result } = await renderLoaded();
    listMock.mockRejectedValueOnce(new Error("reload-fail"));
    act(() => {
      result.current.handleAnalyze(7);
    });
    await waitFor(() =>
      expect(toastError).toHaveBeenCalledWith(enResume["toast.listRefreshFailed"]),
    );
    expect(toastSuccess).not.toHaveBeenCalled();
    expect(result.current.loadError).toBe("");
  });

  it("formats ApiError codes on upload failure", async () => {
    uploadMock.mockRejectedValue(new ApiError("Cannot reach the backend", 0, { code: "NET0000" }));
    const { result } = await renderLoaded();
    await act(async () => {
      await result.current.handleUpload(asUploadEvent(pdf()));
    });
    expect(result.current.uploadError).toContain("[NET0000]");
    expect(listMock).toHaveBeenCalledTimes(1);
  });

  it("ignores upload when the file input is empty", async () => {
    const { result } = await renderLoaded();
    await act(async () => {
      await result.current.handleUpload({ target: { files: [] } } as never);
    });
    expect(uploadMock).not.toHaveBeenCalled();
  });

  it("uploads a new version and toasts after refresh", async () => {
    const v2 = makeResumeResponse({ id: 8, filename: "ada-v2.pdf" });
    uploadVersionMock.mockResolvedValue(v2);
    const { result } = await renderLoaded();
    await act(async () => {
      await result.current.handleUploadVersion(7, pdf());
    });
    expect(uploadVersionMock).toHaveBeenCalled();
    expect(toastSuccess).toHaveBeenCalledWith(enResume["toast.uploadQueued"]);
    expect(listMock).toHaveBeenCalledTimes(2);
  });
});
