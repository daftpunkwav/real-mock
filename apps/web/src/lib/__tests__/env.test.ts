/**
 * @file env.test.ts
 * @description WS_BASE derivation from STREAM_API_BASE: the WS base must share
 * the REST host, otherwise host-scoped auth cookies never reach the handshake.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

const ENV_KEYS = ["NEXT_PUBLIC_API_BASE", "NEXT_PUBLIC_STREAM_API_BASE", "NEXT_PUBLIC_WS_URL"] as const;

async function loadEnv(env: Partial<Record<(typeof ENV_KEYS)[number], string>>) {
  vi.resetModules();
  const saved: Record<string, string | undefined> = {};
  for (const key of ENV_KEYS) {
    saved[key] = process.env[key];
    if (env[key] === undefined) delete process.env[key];
    else process.env[key] = env[key]!;
  }
  try {
    const mod = await import("@/lib/env");
    return mod.getEnv();
  } finally {
    for (const key of ENV_KEYS) {
      if (saved[key] === undefined) delete process.env[key];
      else process.env[key] = saved[key]!;
    }
  }
}

describe("env WS base derivation", () => {
  afterEach(() => {
    vi.resetModules();
  });

  it("derives ws:// from an explicit 127.0.0.1 stream base (cookie host match)", async () => {
    const env = await loadEnv({
      NEXT_PUBLIC_STREAM_API_BASE: "http://127.0.0.1:8081",
    });
    expect(env.WS_BASE).toBe("ws://127.0.0.1:8081");
    expect(env.STREAM_API_BASE).toBe("http://127.0.0.1:8081");
  });

  it("derives wss:// from an https stream base", async () => {
    const env = await loadEnv({
      NEXT_PUBLIC_STREAM_API_BASE: "https://api.example.com",
    });
    expect(env.WS_BASE).toBe("wss://api.example.com");
  });

  it("keeps an explicit WS_URL when provided", async () => {
    const env = await loadEnv({
      NEXT_PUBLIC_STREAM_API_BASE: "http://127.0.0.1:8081",
      NEXT_PUBLIC_WS_URL: "ws://192.168.1.5:8081",
    });
    expect(env.WS_BASE).toBe("ws://192.168.1.5:8081");
  });

  it("falls back to localhost on both bases when nothing is set (dev)", async () => {
    const env = await loadEnv({});
    expect(env.WS_BASE).toBe("ws://localhost:8081");
    expect(env.STREAM_API_BASE).toBe("http://localhost:8081");
  });
});
