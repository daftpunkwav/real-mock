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

describe("env production validation", () => {
  afterEach(() => {
    vi.resetModules();
  });

  /** loadEnv variant that runs readEnv() with NODE_ENV=production. */
  async function loadProdEnv(env: Partial<Record<(typeof ENV_KEYS)[number], string>>) {
    vi.resetModules();
    const procEnv = process.env as Record<string, string | undefined>;
    const saved: Record<string, string | undefined> = { NODE_ENV: procEnv.NODE_ENV };
    procEnv.NODE_ENV = "production";
    for (const key of ENV_KEYS) {
      saved[key] = procEnv[key];
      if (env[key] === undefined) delete procEnv[key];
      else procEnv[key] = env[key]!;
    }
    try {
      const mod = await import("@/lib/env");
      return mod.getEnv();
    } finally {
      for (const key of ENV_KEYS) {
        if (saved[key] === undefined) delete procEnv[key];
        else procEnv[key] = saved[key]!;
      }
      procEnv.NODE_ENV = saved.NODE_ENV;
    }
  }

  const fullValid = {
    NEXT_PUBLIC_API_BASE: "https://api.example.com",
    NEXT_PUBLIC_STREAM_API_BASE: "https://api.example.com",
    NEXT_PUBLIC_WS_URL: "wss://api.example.com",
  };

  it("accepts a complete protocol-consistent production config and strips trailing slashes", async () => {
    const env = await loadProdEnv({
      ...fullValid,
      NEXT_PUBLIC_API_BASE: "https://api.example.com/",
    });
    expect(env.API_BASE).toBe("https://api.example.com");
    expect(env.STREAM_API_BASE).toBe("https://api.example.com");
  });

  it("throws when production is missing required vars, naming all of them", async () => {
    await expect(loadProdEnv({})).rejects.toThrow(
      /NEXT_PUBLIC_API_BASE, NEXT_PUBLIC_WS_URL, NEXT_PUBLIC_STREAM_API_BASE/,
    );
  });

  it("throws on an https API_BASE with a ws:// WS_URL", async () => {
    await expect(
      loadProdEnv({
        ...fullValid,
        NEXT_PUBLIC_WS_URL: "ws://api.example.com",
      }),
    ).rejects.toThrow(/API_BASE and WS_URL protocol mismatch/);
  });

  it("throws on an https API_BASE with an http:// STREAM_API_BASE", async () => {
    await expect(
      loadProdEnv({
        ...fullValid,
        NEXT_PUBLIC_STREAM_API_BASE: "http://api.example.com",
      }),
    ).rejects.toThrow(/API_BASE and STREAM_API_BASE protocol mismatch/);
  });

  it("throws when WS_URL hosts differ from STREAM_API_BASE (host-scoped cookies)", async () => {
    await expect(
      loadProdEnv({
        NEXT_PUBLIC_API_BASE: "http://api.example.com",
        NEXT_PUBLIC_STREAM_API_BASE: "http://api.example.com",
        NEXT_PUBLIC_WS_URL: "ws://other.example.com",
      }),
    ).rejects.toThrow(/host must equal STREAM_API_BASE host/);
  });
});
