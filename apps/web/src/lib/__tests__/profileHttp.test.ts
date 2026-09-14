/**
 * @file profileHttp.test.ts
 * @description Guards profileHttp request shapes and empty 200 response bodies.
 */

import { describe, expect, it, vi } from "vitest";

import { profileHttp } from "../api/profileHttp";

const requestMock = vi.hoisted(() => vi.fn());

// Mirrors the real ApiError signature so callers can assert the NET0003 code.
vi.mock("../api/base", () => ({
  ApiError: class ApiError extends Error {
    status: number;
    code: string;
    constructor(message: string, status: number, options: { code?: string } = {}) {
      super(message);
      this.status = status;
      this.code = options.code ?? (status === 0 ? "NET0000" : `http_${status}`);
    }
  },
  request: requestMock,
}));

describe("profileHttp empty-body guards", () => {
  it("getProfile throws on an undefined response body", async () => {
    requestMock.mockResolvedValueOnce(undefined);
    await expect(profileHttp.getProfile()).rejects.toThrow("empty response");
  });

  it("updateProfile throws on an empty response body", async () => {
    requestMock.mockResolvedValueOnce(undefined);
    await expect(
      profileHttp.updateProfile({
        name: "x",
        identity: "employed",
        job_direction: "backend",
        target_role: "engineer",
        self_intro: "intro",
        tech_domains: ["Python"],
      } as Parameters<typeof profileHttp.updateProfile>[0]),
    ).rejects.toThrow("empty response");
  });

  it("clearProfile throws on an empty response body", async () => {
    requestMock.mockResolvedValueOnce(undefined);
    await expect(profileHttp.clearProfile()).rejects.toThrow("empty response");
  });

  it("rejects a null body with the NET0003 code", async () => {
    requestMock.mockResolvedValueOnce(null);
    await expect(profileHttp.getProfile()).rejects.toMatchObject({ code: "NET0003" });
  });

  it("passes through a normal response body", async () => {
    const body = { id: 1, name: "Alice" };
    requestMock.mockResolvedValueOnce(body);
    await expect(profileHttp.getProfile()).resolves.toBe(body);
  });
});

describe("profileHttp request shapes", () => {
  it("getProfile hits /v1/profile and forwards the AbortSignal", async () => {
    requestMock.mockResolvedValueOnce({ id: 1 });
    const signal = new AbortController().signal;
    await profileHttp.getProfile({ signal });
    expect(requestMock).toHaveBeenCalledWith("/v1/profile", { signal });
  });

  it("updateProfile PUTs the JSON-serialized body to /v1/profile", async () => {
    requestMock.mockResolvedValueOnce({ id: 1 });
    const body = {
      name: "x",
      tech_domains: ["Python"],
    } as Parameters<typeof profileHttp.updateProfile>[0];
    await profileHttp.updateProfile(body, { signal: undefined });
    expect(requestMock).toHaveBeenCalledWith("/v1/profile", {
      method: "PUT",
      body: JSON.stringify(body),
      signal: undefined,
    });
  });

  it("clearProfile POSTs to /v1/profile/clear", async () => {
    requestMock.mockResolvedValueOnce({ id: 1 });
    await profileHttp.clearProfile({ signal: undefined });
    expect(requestMock).toHaveBeenCalledWith("/v1/profile/clear", {
      method: "POST",
      signal: undefined,
    });
  });

  it("every call forwards the same AbortSignal instance", async () => {
    requestMock.mockClear();
    requestMock.mockResolvedValue({ id: 1 });
    const signal = new AbortController().signal;
    await profileHttp.getProfile({ signal });
    await profileHttp.clearProfile({ signal });
    const forwarded = requestMock.mock.calls.map(
      (call) => (call[1] as { signal?: AbortSignal }).signal,
    );
    expect(forwarded).toEqual([signal, signal]);
  });
});
