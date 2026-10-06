// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { recordsHttp, resumeHttp, settingsHttp } from "@/lib/api/clients";
import { DataManagementPanel } from "../DataManagementPanel";

vi.mock("@/i18n", () => ({ useT: () => (key: string) => key }));
vi.mock("@/lib/api/clients", () => ({
  recordsHttp: { listSessions: vi.fn() },
  resumeHttp: { listResumes: vi.fn() },
  settingsHttp: { clearAllData: vi.fn() },
}));
vi.mock("@/components/Toast", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("@/components/ConfirmDialog", () => ({
  ConfirmDialog: ({ open, onConfirm }: { open: boolean; onConfirm: () => void }) =>
    open ? <button onClick={onConfirm}>confirm wipe</button> : null,
}));

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: Error) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}
const sessions = vi.mocked(recordsHttp.listSessions);
const resumes = vi.mocked(resumeHttp.listResumes);
const wipe = vi.mocked(settingsHttp.clearAllData);
beforeEach(() => vi.resetAllMocks());
afterEach(cleanup);

async function confirmWipe() {
  fireEvent.click(screen.getByRole("button", { name: "data.wipe.action" }));
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "confirm wipe" }));
  });
}

it.each([false, true])(
  "ignores earlier picker requests after a wipe reload (reject=%s)",
  async (reject) => {
    const oldSessions = deferred<Awaited<ReturnType<typeof recordsHttp.listSessions>>>();
    const oldResumes = deferred<Awaited<ReturnType<typeof resumeHttp.listResumes>>>();
    sessions.mockReturnValueOnce(oldSessions.promise).mockResolvedValueOnce([{ id: 2 } as never]);
    resumes
      .mockReturnValueOnce(oldResumes.promise)
      .mockResolvedValueOnce([{ id: 2, filename: "current.pdf" } as never]);
    wipe.mockResolvedValue({} as never);
    render(<DataManagementPanel />);
    await confirmWipe();
    await act(async () => {
      if (reject) {
        oldSessions.reject(new Error("old failure"));
        oldResumes.reject(new Error("old failure"));
      } else {
        oldSessions.resolve([{ id: 1 } as never]);
        oldResumes.resolve([{ id: 1, filename: "stale.pdf" } as never]);
      }
    });
    expect((screen.getAllByRole("combobox")[1] as HTMLSelectElement).value).toBe("2");
    fireEvent.change(screen.getAllByRole("combobox")[0]!, { target: { value: "analysis" } });
    expect((screen.getAllByRole("combobox")[1] as HTMLSelectElement).value).toBe("2");
    expect(screen.queryByText("stale.pdf")).toBeNull();
    expect(screen.getByRole("button", { name: "data.export.formatMd" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "data.export.formatJson" })).toBeTruthy();
  },
);

it("does not start another picker load when a wipe finishes after unmount", async () => {
  sessions.mockResolvedValue([]);
  resumes.mockResolvedValue([]);
  const pendingWipe = deferred<Awaited<ReturnType<typeof settingsHttp.clearAllData>>>();
  wipe.mockReturnValue(pendingWipe.promise);
  const { unmount } = render(<DataManagementPanel />);
  await confirmWipe();
  unmount();
  await act(async () => {
    pendingWipe.resolve({} as never);
  });
  expect(sessions).toHaveBeenCalledTimes(1);
  expect(resumes).toHaveBeenCalledTimes(1);
});

it("cancels the post-wipe picker requests on unmount", async () => {
  const pendingSessions = deferred<Awaited<ReturnType<typeof recordsHttp.listSessions>>>();
  const pendingResumes = deferred<Awaited<ReturnType<typeof resumeHttp.listResumes>>>();
  sessions.mockResolvedValueOnce([]).mockReturnValueOnce(pendingSessions.promise);
  resumes.mockResolvedValueOnce([]).mockReturnValueOnce(pendingResumes.promise);
  wipe.mockResolvedValue({} as never);
  const { unmount } = render(<DataManagementPanel />);
  await confirmWipe();
  unmount();
  const readSession = vi.fn(() => ({ id: 2 }));
  const readResume = vi.fn(() => ({ id: 2, filename: "late.pdf" }));
  const sessionRows: Awaited<ReturnType<typeof recordsHttp.listSessions>> = [];
  const resumeRows: Awaited<ReturnType<typeof resumeHttp.listResumes>> = [];
  Object.defineProperty(sessionRows, "0", { get: readSession });
  Object.defineProperty(resumeRows, "0", { get: readResume });
  await act(async () => {
    pendingSessions.resolve(sessionRows);
    pendingResumes.resolve(resumeRows);
  });
  expect(readSession).not.toHaveBeenCalled();
  expect(readResume).not.toHaveBeenCalled();
});
