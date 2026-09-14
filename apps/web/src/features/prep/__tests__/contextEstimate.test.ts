/** contextEstimate: script-aware buckets, localOnly exclusion, remainder attribution. */

import { describe, expect, it } from "vitest";

import { assistantMetaChars, estimatePrepContext, estimateTextTokens } from "../contextEstimate";
import type { PrepChatMessage } from "../types";

function user(content: string, extra?: Partial<PrepChatMessage>): PrepChatMessage {
  return { id: "u-1", role: "user", content, ...extra };
}

function assistant(content: string, extra?: Partial<PrepChatMessage>): PrepChatMessage {
  return { id: "a-1", role: "assistant", content, ...extra };
}

describe("estimateTextTokens", () => {
  it("uses script-aware ratios (backend parity)", () => {
    expect(estimateTextTokens("")).toBe(0);
    expect(estimateTextTokens("abc")).toBe(1);
    expect(estimateTextTokens("Hello")).toBe(1);
    expect(estimateTextTokens("你好世界")).toBe(2);
    expect(estimateTextTokens("Hello你好")).toBe(2);
  });
});

describe("estimatePrepContext", () => {
  it("splits bodies into messages/replies with overhead in system", () => {
    const est = estimatePrepContext([user("x".repeat(150)), assistant("y".repeat(150))], 0);
    // 150 latin chars -> 37 tokens each; 4 framing overhead per message joins system.
    expect(est.userEst).toBe(37);
    expect(est.assistantEst).toBe(37);
    expect(est.systemEst).toBe(8);
    expect(est.used).toBe(82);
  });

  it("measures thinking/trace/steps/search into the system bucket", () => {
    const msg = assistant("z".repeat(150), {
      thinking: "t".repeat(150),
      trace: [{ kind: "tool", name: "web_search", query: "q".repeat(150) }],
      searchGroups: [{ query: "s", results: [{ title: "ti", url: "u", snippet: "sn" }] }],
    });
    const est = estimatePrepContext([msg], 0);
    expect(est.assistantEst).toBe(37);
    expect(est.systemEst).toBeGreaterThan(37);
    expect(assistantMetaChars(msg)).toBeGreaterThan(0);
  });

  it("counts compaction cards into the system bucket", () => {
    const card: PrepChatMessage = {
      id: "c-1",
      role: "compaction",
      content: "Session objectives: ship it",
      compaction: { summary: "x", version: 1, forkPoint: 8, backupSessionId: 2, before: null, after: null },
      backendIndex: 3,
    };
    const est = estimatePrepContext([card], 0);
    expect(est.userEst).toBe(0);
    expect(est.assistantEst).toBe(0);
    expect(est.systemEst).toBeGreaterThan(0);
  });

  it("skips localOnly messages (welcome banner, failed-turn errors)", () => {
    const est = estimatePrepContext(
      [assistant("w".repeat(1500), { localOnly: true }), user("x".repeat(150))],
      0,
    );
    expect(est.assistantEst).toBe(0);
    expect(est.userEst).toBe(37);
    expect(est.used).toBe(41);
  });

  it("attributes the backend remainder to system instead of hiding it", () => {
    const est = estimatePrepContext([user("x".repeat(150)), assistant("y".repeat(150))], 1000);
    expect(est.used).toBe(1000);
    // Measured 82; the unattributed 918 joins the system bucket.
    expect(est.systemEst).toBeCloseTo(926, 6);
    expect(est.userEst + est.assistantEst + est.systemEst).toBeCloseTo(1000, 6);
  });

  it("prefers the backend report but never goes below the measurement", () => {
    const est = estimatePrepContext([user("x".repeat(150))], 10);
    expect(est.used).toBe(41);
  });
});
