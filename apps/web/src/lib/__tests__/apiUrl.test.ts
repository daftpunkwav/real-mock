/**
 * @vitest-environment jsdom
 * @file apiUrl.test.ts
 * @description resolveServerBackendUrl determinism + useAlignedBackendUrl SSR parity.
 *
 * Regression test for the resume-preview hydration mismatch: SSR emits the
 * unaligned base, while the client aligned localhost ↔ 127.0.0.1. Rendered
 * href/src attributes must start from the server URL so the first client
 * render matches SSR HTML.
 */

import { afterEach, describe, expect, it, vi } from "vitest";
import { renderHook } from "@testing-library/react";

import { resolveBackendUrl, resolveServerBackendUrl } from "../api/apiUrl";
import { useAlignedBackendUrl } from "../api/useAlignedBackendUrl";

describe("resolveServerBackendUrl", () => {
  it("ignores window alignment and prefixes the configured base", () => {
    expect(resolveServerBackendUrl("/api/v1/resume/2/file?download=1")).toBe(
      "http://localhost:8081/api/v1/resume/2/file?download=1",
    );
  });

  it("normalizes a missing leading slash", () => {
    expect(resolveServerBackendUrl("api/v1/resume/2/file")).toBe(
      "http://localhost:8081/api/v1/resume/2/file",
    );
  });
});

describe("resolveBackendWsUrl loopback alignment", () => {
  const WS_ENV = {
    NEXT_PUBLIC_STREAM_API_BASE: "http://localhost:8081",
    NEXT_PUBLIC_WS_URL: "ws://localhost:8081",
  };
  let restoreLocation: (() => void) | null = null;

  async function withEnv(
    env: Record<string, string>,
    fn: (mod: typeof import("../api/apiUrl")) => void,
  ) {
    const saved: Record<string, string | undefined> = {};
    for (const [k, v] of Object.entries(env)) {
      saved[k] = process.env[k];
      process.env[k] = v;
    }
    vi.resetModules();
    try {
      const mod = await import("../api/apiUrl");
      fn(mod);
    } finally {
      for (const [k, v] of Object.entries(saved)) {
        if (v === undefined) delete process.env[k];
        else process.env[k] = v;
      }
      vi.resetModules();
    }
  }

  function gotoPage(pageUrl: string) {
    const fakeLocation = new URL(pageUrl) as unknown as Location;
    const desc = Object.getOwnPropertyDescriptor(window, "location");
    Object.defineProperty(window, "location", {
      configurable: true,
      value: fakeLocation,
    });
    restoreLocation = () => {
      if (desc) Object.defineProperty(window, "location", desc);
    };
  }

  it("aligns the ws host to a 127.0.0.1 page so the session cookie rides along", async () => {
    gotoPage("http://127.0.0.1:8080/room");
    await withEnv(WS_ENV, (mod) => {
      expect(mod.resolveBackendWsUrl("/api/v1/ws/interview/37")).toBe(
        "ws://127.0.0.1:8081/api/v1/ws/interview/37",
      );
    });
  });

  it("aligns the ws host to a localhost page from a 127.0.0.1 base", async () => {
    gotoPage("http://localhost:8080/room");
    await withEnv(
      {
        NEXT_PUBLIC_STREAM_API_BASE: "http://127.0.0.1:8081",
        NEXT_PUBLIC_WS_URL: "ws://127.0.0.1:8081",
      },
      (mod) => {
        expect(mod.resolveBackendWsUrl("/api/v1/ws/interview/37")).toBe(
          "ws://localhost:8081/api/v1/ws/interview/37",
        );
      },
    );
  });

  it("keeps non-loopback ws hosts untouched", async () => {
    gotoPage("http://127.0.0.1:8080/room");
    await withEnv(
      {
        NEXT_PUBLIC_STREAM_API_BASE: "http://localhost:8081",
        NEXT_PUBLIC_WS_URL: "ws://interview.example.com:8081",
      },
      (mod) => {
        expect(mod.resolveBackendWsUrl("/api/v1/ws/interview/37")).toBe(
          "ws://interview.example.com:8081/api/v1/ws/interview/37",
        );
      },
    );
  });

  afterEach(() => {
    restoreLocation?.();
    restoreLocation = null;
  });
});

describe("useAlignedBackendUrl", () => {
  it("first render equals the SSR URL (hydration parity)", () => {
    const path = "/api/v1/resume/2/file?download=1";
    const { result } = renderHook(() => useAlignedBackendUrl(path));
    expect(result.current).toBe(resolveServerBackendUrl(path));
  });

  it("settles on the aligned URL after mount", () => {
    const path = "/api/v1/resume/2/pages/1";
    const { result } = renderHook(() => useAlignedBackendUrl(path));
    expect(result.current).toBe(resolveBackendUrl(path));
  });
});
