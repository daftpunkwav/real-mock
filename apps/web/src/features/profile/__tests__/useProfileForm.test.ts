// @vitest-environment jsdom
/**
 * @file useProfileForm.test.ts
 * @description Contract tests for useProfileForm load, save, and navigation guards.
 */

import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api/base";
import { DEFAULT_LOCALE } from "@/i18n/locales";
import { setCurrentLocale } from "@/i18n/resolve";
import type { UserProfileResponse } from "@/lib/api/contract";
import { profileHttp } from "@/lib/api/clients";

import { useProfileForm } from "../useProfileForm";

import { makeProfile } from "./helpers";

// Vitest globals are off; clean up so listeners and locale state do not leak across cases.
afterEach(() => {
  cleanup();
  setCurrentLocale(DEFAULT_LOCALE);
});

const pushMock = vi.hoisted(() => vi.fn());
const toastSuccess = vi.hoisted(() => vi.fn());
const toastError = vi.hoisted(() => vi.fn());
const toastClear = vi.hoisted(() => vi.fn());

vi.mock("@/lib/api/clients", () => ({
  profileHttp: {
    getProfile: vi.fn(),
    updateProfile: vi.fn(),
    clearProfile: vi.fn(),
  },
}));

vi.mock("@/components/Toast", () => ({
  toast: {
    success: toastSuccess,
    error: toastError,
    clear: toastClear,
  },
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock }),
}));

const getMock = vi.mocked(profileHttp.getProfile);
const saveMock = vi.mocked(profileHttp.updateProfile);
const clearMock = vi.mocked(profileHttp.clearProfile);

/** Required-complete baseline so save is not blocked by required validation */
const baseProfile = makeProfile({
  name: "Ada",
  identity: "employed",
  job_direction: "Backend development",
  experience_years: "3",
  target_role: "Backend engineer",
  self_intro: "Five years of backend experience",
  tech_domains: ["Python"],
});

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

/** Mount the hook and flush the initial load Promise chain */
async function renderLoaded() {
  const rendered = renderHook(() => useProfileForm());
  await act(async () => {});
  expect(rendered.result.current.loading).toBe(false);
  return rendered;
}

beforeEach(() => {
  vi.clearAllMocks();
  setCurrentLocale("zh-CN");
  pushMock.mockClear();
  getMock.mockResolvedValue(baseProfile);
});

describe("useProfileForm", () => {
  it("fills profile after load completes", async () => {
    const { result } = await renderLoaded();
    expect(result.current.profile).toEqual(baseProfile);
  });

  it("sets loadError from the Error message when the load fails", async () => {
    getMock.mockRejectedValueOnce(new Error("database unreachable"));
    const { result } = renderHook(() => useProfileForm());
    await act(async () => {});
    expect(result.current.loading).toBe(false);
    expect(result.current.profile).toBeNull();
    expect(result.current.loadError).toBe("database unreachable");
  });

  it("falls back to the localized load copy for non-Error rejections", async () => {
    getMock.mockRejectedValueOnce("boom");
    const { result } = renderHook(() => useProfileForm());
    await act(async () => {});
    expect(result.current.loadError).toBe("加载失败");
  });

  it("stays silent when the load request is aborted (NET0002)", async () => {
    getMock.mockRejectedValueOnce(new ApiError("aborted", 0, { code: "NET0002" }));
    const { result } = renderHook(() => useProfileForm());
    await act(async () => {});
    expect(result.current.loading).toBe(false);
    expect(result.current.loadError).toBe("");
  });

  it("ignores a stale load that resolves after a newer one", async () => {
    const stale = deferred<UserProfileResponse>();
    const fresh = deferred<UserProfileResponse>();
    getMock.mockReturnValueOnce(stale.promise).mockReturnValueOnce(fresh.promise);
    const { result } = renderHook(() => useProfileForm());
    await act(async () => {});
    expect(result.current.loading).toBe(true);
    await act(async () => {
      result.current.loadProfile();
    });
    await act(async () => {
      fresh.resolve({ ...baseProfile, name: "fresh" });
    });
    await act(async () => {
      stale.resolve({ ...baseProfile, name: "stale" });
    });
    expect(result.current.profile?.name).toBe("fresh");
    expect(result.current.loading).toBe(false);
  });

  it("aborts the in-flight load on unmount", async () => {
    const d = deferred<UserProfileResponse>();
    getMock.mockReturnValueOnce(d.promise);
    const { unmount } = renderHook(() => useProfileForm());
    const signal = getMock.mock.calls[0]?.[0]?.signal;
    expect(signal?.aborted).toBe(false);
    unmount();
    expect(signal?.aborted).toBe(true);
  });

  it("patch, addDomain, and removeDomain are no-ops before the profile is loaded", async () => {
    const d = deferred<UserProfileResponse>();
    getMock.mockReturnValueOnce(d.promise);
    const { result } = renderHook(() => useProfileForm());
    await act(async () => {});
    expect(result.current.profile).toBeNull();
    act(() => {
      result.current.patch("name", "too early");
      result.current.addDomain();
      result.current.removeDomain(0);
    });
    expect(result.current.profile).toBeNull();
  });

  it("removeDomain drops the entry and always keeps at least one slot", async () => {
    const { result } = await renderLoaded();
    act(() => {
      result.current.patch("tech_domains", ["Python", "Go"]);
    });
    act(() => {
      result.current.removeDomain(0);
    });
    expect(result.current.profile?.tech_domains).toEqual(["Go"]);
    act(() => {
      result.current.removeDomain(0);
    });
    expect(result.current.profile?.tech_domains).toEqual([""]);
  });

  it("addDomain appends an empty slot while under the cap", async () => {
    const { result } = await renderLoaded();
    expect(result.current.profile?.tech_domains).toEqual(["Python"]);
    act(() => {
      result.current.addDomain();
    });
    expect(result.current.profile?.tech_domains).toEqual(["Python", ""]);
  });

  it("save with missing required fields toasts an error and skips PUT", async () => {
    getMock.mockResolvedValue(makeProfile());
    const { result } = await renderLoaded();
    await act(async () => {
      await result.current.handleSave();
    });
    expect(saveMock).not.toHaveBeenCalled();
    expect(toastError).toHaveBeenCalledWith(
      "请先填写必填项:姓名、身份、求职方向、自我介绍、技术领域、目标岗位",
      { durationMs: 6000 },
    );
    expect(result.current.requiredError("name")).toBe(true);
    // Patching the failed key clears only its own flag; other sections stay flagged.
    act(() => {
      result.current.patch("name", "Alice");
    });
    expect(result.current.requiredError("name")).toBe(false);
    expect(result.current.requiredError("target_role")).toBe(true);
    act(() => {
      result.current.patch("city", "Shanghai");
    });
    expect(result.current.requiredError("target_role")).toBe(true);
  });

  it("save abort (NET0002) is silent and does not block the next save", async () => {
    const { result } = await renderLoaded();
    saveMock.mockRejectedValueOnce(new ApiError("aborted", 0, { code: "NET0002" }));
    await act(async () => {
      await result.current.handleSave();
    });
    expect(toastError).not.toHaveBeenCalled();
    expect(toastSuccess).not.toHaveBeenCalled();
    expect(result.current.saving).toBe(false);
    saveMock.mockResolvedValueOnce({ ...baseProfile });
    await act(async () => {
      await result.current.handleSave();
    });
    expect(saveMock).toHaveBeenCalledTimes(2);
    expect(toastSuccess).toHaveBeenCalledWith("已保存");
  });

  it("save rejection of a non-Error value falls back to the localized copy", async () => {
    const { result } = await renderLoaded();
    saveMock.mockRejectedValueOnce("boom");
    await act(async () => {
      await result.current.handleSave();
    });
    expect(toastError).toHaveBeenCalledWith("保存失败");
  });

  it("clear abort (NET0002) reports failure without a toast", async () => {
    const { result } = await renderLoaded();
    clearMock.mockRejectedValueOnce(new ApiError("aborted", 0, { code: "NET0002" }));
    let ok = true;
    await act(async () => {
      ok = await result.current.handleClear();
    });
    expect(ok).toBe(false);
    expect(toastError).not.toHaveBeenCalled();
    expect(result.current.profile).toEqual(baseProfile);
  });

  it("adopts the server snapshot when clear resolves after abort, without a success toast", async () => {
    const { result } = await renderLoaded();
    const d = deferred<UserProfileResponse>();
    clearMock.mockReturnValue(d.promise);
    let ok = false;
    act(() => {
      void result.current.handleClear().then((v) => {
        ok = v;
      });
    });
    act(() => {
      result.current.leavePage();
    });
    await act(async () => {
      d.resolve(makeProfile({ id: baseProfile.id }));
    });
    expect(ok).toBe(true);
    expect(result.current.dirty).toBe(false);
    expect(toastSuccess).not.toHaveBeenCalled();
  });

  it("clear rejection of a non-Error value falls back to the localized copy", async () => {
    const { result } = await renderLoaded();
    clearMock.mockRejectedValueOnce("boom");
    let ok = true;
    await act(async () => {
      ok = await result.current.handleClear();
    });
    expect(ok).toBe(false);
    expect(toastError).toHaveBeenCalledWith("清空失败");
  });

  it("rapid same-frame saves issue only one request", async () => {
    const { result } = await renderLoaded();
    const d = deferred<UserProfileResponse>();
    saveMock.mockReturnValue(d.promise);
    act(() => {
      void result.current.handleSave();
      void result.current.handleSave();
      void result.current.handleSave();
    });
    expect(saveMock).toHaveBeenCalledTimes(1);
    await act(async () => {
      d.resolve({ ...baseProfile });
    });
    expect(toastSuccess).toHaveBeenCalledWith("已保存");
    expect(result.current.saving).toBe(false);
  });

  it("in-flight edits are not rolled back by server response", async () => {
    const { result } = await renderLoaded();
    const d = deferred<UserProfileResponse>();
    saveMock.mockReturnValue(d.promise);
    act(() => {
      void result.current.handleSave();
    });
    act(() => {
      result.current.patch("name", "name being edited");
    });
    await act(async () => {
      d.resolve({ ...baseProfile, name: "Ada" });
    });
    expect(result.current.profile?.name).toBe("name being edited");
  });

  it("save failure shows error and can retry after reset", async () => {
    const { result } = await renderLoaded();
    saveMock.mockRejectedValueOnce(new Error("network interrupted"));
    await act(async () => {
      await result.current.handleSave();
    });
    expect(toastError).toHaveBeenCalledWith("network interrupted");
    expect(result.current.saving).toBe(false);
    saveMock.mockResolvedValue({ ...baseProfile });
    await act(async () => {
      await result.current.handleSave();
    });
    expect(saveMock).toHaveBeenCalledTimes(2);
    expect(toastSuccess).toHaveBeenCalledWith("已保存");
  });

  it("dirty is true after edit and clears after successful save", async () => {
    const { result } = await renderLoaded();
    expect(result.current.dirty).toBe(false);
    act(() => {
      result.current.patch("name", "edit");
    });
    expect(result.current.dirty).toBe(true);
    saveMock.mockResolvedValue({ ...baseProfile, name: "edit" });
    await act(async () => {
      await result.current.handleSave();
    });
    expect(result.current.dirty).toBe(false);
  });

  it("dirty is false after reverting edits to the saved snapshot", async () => {
    const { result } = await renderLoaded();
    act(() => {
      result.current.patch("name", "edit");
    });
    expect(result.current.dirty).toBe(true);
    act(() => {
      result.current.patch("name", baseProfile.name);
    });
    expect(result.current.dirty).toBe(false);
  });

  it("clears pendingNav when edits are reverted to the saved snapshot", async () => {
    const { result } = await renderLoaded();
    act(() => {
      result.current.patch("name", "unsaved edit");
    });
    const anchor = document.createElement("a");
    anchor.setAttribute("href", "/resume");
    document.body.appendChild(anchor);
    act(() => {
      anchor.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
    });
    expect(result.current.pendingNav).toBe("/resume");
    act(() => {
      result.current.patch("name", baseProfile.name);
    });
    expect(result.current.dirty).toBe(false);
    expect(result.current.pendingNav).toBeNull();
    anchor.remove();
  });

  it("ignores addDomain after the tech_domains count cap is reached", async () => {
    const { result } = await renderLoaded();
    const full = makeProfile({ tech_domains: Array.from({ length: 20 }, (_, i) => `t${i}`) });
    act(() => {
      result.current.patch("tech_domains", full.tech_domains);
    });
    expect(result.current.profile?.tech_domains).toHaveLength(20);
    act(() => {
      result.current.addDomain();
    });
    expect(result.current.profile?.tech_domains).toHaveLength(20);
    act(() => {
      result.current.addDomain();
    });
    expect(result.current.profile?.tech_domains).toHaveLength(20);
  });

  it("blocks in-app links when dirty and navigates after confirm", async () => {
    const { result } = await renderLoaded();
    act(() => {
      result.current.patch("name", "unsaved edit");
    });
    const anchor = document.createElement("a");
    anchor.setAttribute("href", "/resume");
    document.body.appendChild(anchor);
    const clickEvent = new MouseEvent("click", { bubbles: true, cancelable: true });
    act(() => {
      anchor.dispatchEvent(clickEvent);
    });
    expect(clickEvent.defaultPrevented).toBe(true);
    expect(result.current.pendingNav).toBe("/resume");

    act(() => {
      result.current.leavePage();
    });
    expect(pushMock).toHaveBeenCalledWith("/resume");
    expect(result.current.pendingNav).toBeNull();
    anchor.remove();
  });

  it("staying on page from confirm dialog does not navigate", async () => {
    const { result } = await renderLoaded();
    act(() => {
      result.current.patch("name", "unsaved edit");
    });
    const anchor = document.createElement("a");
    anchor.setAttribute("href", "/resume");
    document.body.appendChild(anchor);
    act(() => {
      anchor.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
    });
    expect(result.current.pendingNav).toBe("/resume");
    act(() => {
      result.current.stayOnPage();
    });
    expect(pushMock).not.toHaveBeenCalled();
    expect(result.current.pendingNav).toBeNull();
    anchor.remove();
  });

  it("does not intercept navigation when clean", async () => {
    await renderLoaded();
    const anchor = document.createElement("a");
    anchor.setAttribute("href", "/resume");
    document.body.appendChild(anchor);
    const clickEvent = new MouseEvent("click", { bubbles: true, cancelable: true });
    act(() => {
      anchor.dispatchEvent(clickEvent);
    });
    expect(clickEvent.defaultPrevented).toBe(false);
    expect(pushMock).not.toHaveBeenCalled();
    anchor.remove();
  });

  it("ignores external links while dirty", async () => {
    const { result } = await renderLoaded();
    act(() => {
      result.current.patch("name", "unsaved edit");
    });
    const anchor = document.createElement("a");
    anchor.setAttribute("href", "https://example.com");
    document.body.appendChild(anchor);
    const clickEvent = new MouseEvent("click", { bubbles: true, cancelable: true });
    act(() => {
      anchor.dispatchEvent(clickEvent);
    });
    expect(clickEvent.defaultPrevented).toBe(false);
    expect(result.current.pendingNav).toBeNull();
    anchor.remove();
  });

  it("leavePage without a pending navigation does not push", async () => {
    const { result } = await renderLoaded();
    act(() => {
      result.current.leavePage();
    });
    expect(pushMock).not.toHaveBeenCalled();
    expect(result.current.pendingNav).toBeNull();
  });

  it("canClear is true for a filled profile and false for a blank one", async () => {
    const { result } = await renderLoaded();
    expect(result.current.canClear).toBe(true);
    getMock.mockResolvedValue(makeProfile());
    await act(async () => {
      result.current.loadProfile();
    });
    await act(async () => {});
    expect(result.current.canClear).toBe(false);
  });

  it("canClear is true when a blank profile has unsaved edits", async () => {
    getMock.mockResolvedValue(makeProfile());
    const { result } = await renderLoaded();
    expect(result.current.canClear).toBe(false);
    act(() => {
      result.current.patch("name", "unsaved edit");
    });
    expect(result.current.dirty).toBe(true);
    expect(result.current.canClear).toBe(true);
  });

  it("warns on beforeunload only while dirty", async () => {
    const { result } = await renderLoaded();
    act(() => {
      result.current.patch("name", "unsaved edit");
    });
    const dirtyEvent = new Event("beforeunload", { cancelable: true });
    act(() => {
      window.dispatchEvent(dirtyEvent);
    });
    expect(dirtyEvent.defaultPrevented).toBe(true);
    act(() => {
      result.current.patch("name", baseProfile.name);
    });
    const cleanEvent = new Event("beforeunload", { cancelable: true });
    act(() => {
      window.dispatchEvent(cleanEvent);
    });
    expect(cleanEvent.defaultPrevented).toBe(false);
  });

  it("clear replaces local state and is not dirty afterward", async () => {
    const { result } = await renderLoaded();
    const blank = makeProfile({ id: baseProfile.id });
    clearMock.mockResolvedValue(blank);
    let ok = false;
    await act(async () => {
      ok = await result.current.handleClear();
    });
    expect(ok).toBe(true);
    expect(clearMock).toHaveBeenCalledTimes(1);
    expect(result.current.profile).toEqual(blank);
    expect(result.current.dirty).toBe(false);
    expect(result.current.canClear).toBe(false);
    expect(toastSuccess).toHaveBeenCalledWith("已清空");
  });

  it("rapid same-frame clears issue only one request", async () => {
    const { result } = await renderLoaded();
    const d = deferred<UserProfileResponse>();
    clearMock.mockReturnValue(d.promise);
    let first = false;
    let second = false;
    await act(async () => {
      const p1 = result.current.handleClear().then((v) => {
        first = v;
      });
      const p2 = result.current.handleClear().then((v) => {
        second = v;
      });
      d.resolve(makeProfile({ id: baseProfile.id }));
      await Promise.all([p1, p2]);
    });
    expect(clearMock).toHaveBeenCalledTimes(1);
    expect(first).toBe(true);
    expect(second).toBe(false);
  });

  it("clear failure keeps current profile and reports error", async () => {
    const { result } = await renderLoaded();
    clearMock.mockRejectedValueOnce(new Error("network interrupted"));
    let ok = true;
    await act(async () => {
      ok = await result.current.handleClear();
    });
    expect(ok).toBe(false);
    expect(result.current.profile).toEqual(baseProfile);
    expect(toastError).toHaveBeenCalledWith("network interrupted");
    expect(result.current.clearing).toBe(false);
  });

  it("adopts the server snapshot when save resolves after abort, without a success toast", async () => {
    const { result } = await renderLoaded();
    act(() => {
      result.current.patch("name", "unsaved edit");
    });
    const d = deferred<UserProfileResponse>();
    saveMock.mockReturnValue(d.promise);
    act(() => {
      void result.current.handleSave();
    });
    act(() => {
      result.current.leavePage();
    });
    await act(async () => {
      d.resolve({ ...baseProfile, name: "unsaved edit" });
    });
    expect(result.current.profile?.name).toBe("unsaved edit");
    expect(result.current.dirty).toBe(false);
    expect(toastSuccess).not.toHaveBeenCalled();
  });

  it("save and clear cannot run at the same time", async () => {
    const { result } = await renderLoaded();
    const d = deferred<UserProfileResponse>();
    saveMock.mockReturnValue(d.promise);
    act(() => {
      void result.current.handleSave();
    });
    let cleared = true;
    await act(async () => {
      cleared = await result.current.handleClear();
    });
    expect(cleared).toBe(false);
    expect(clearMock).not.toHaveBeenCalled();
    await act(async () => {
      d.resolve({ ...baseProfile });
    });
  });
});
